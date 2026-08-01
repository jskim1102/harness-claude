"""Keep Codex hook definitions in one config source.

Orca writes its Codex integration hooks to ``$CODEX_HOME/hooks.json`` while
creating a terminal.  Codex also records hook trust state in ``config.toml``;
loading both representations from that user layer produces a warning.  This
helper runs after Orca has created the terminal, merges Orca's hooks with the
harness safety hooks into TOML hook tables, and removes ``hooks.json`` before
Codex starts.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any


BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
LEGACY_MARKERS = {
    "# >>> harness-codex-hooks v1 >>>",
    "# <<< harness-codex-hooks v1 <<<",
    "# Auto-generated after Orca terminal creation. Do not edit this block.",
}


class HookConfigError(ValueError):
    """A hook source cannot be migrated without risking data loss."""


def _snapshot(path: Path) -> tuple[bytes, int] | None:
    try:
        raw = path.read_bytes()
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        return None
    return raw, mode


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HookConfigError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _load_hooks(path: Path, raw: bytes) -> dict[str, list[dict[str, Any]]]:
    try:
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (UnicodeError, ValueError) as exc:
        raise HookConfigError(f"malformed hooks JSON {path}: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != {"hooks"}:
        raise HookConfigError(
            f"unexpected hooks JSON root in {path}: expected only a hooks object"
        )
    events = payload["hooks"]
    if not isinstance(events, dict):
        raise HookConfigError(f"unexpected hooks JSON in {path}: hooks must be an object")
    for event, groups in events.items():
        if not isinstance(event, str) or not isinstance(groups, list):
            raise HookConfigError(
                f"unexpected hooks JSON in {path}: event values must be arrays"
            )
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise HookConfigError(
                    f"unexpected hooks JSON in {path}: hook groups need a hooks array"
                )
            if not all(isinstance(hook, dict) for hook in group["hooks"]):
                raise HookConfigError(
                    f"unexpected hooks JSON in {path}: hooks must be objects"
                )
    return events


def _harness_commands(repo: Path) -> dict[str, str]:
    return {
        "git": f"python3 {repo}/hooks/git_guard.py",
        "guard": f"python3 {repo}/hooks/inbox_isolation_guard.py",
        "clear": f"python3 {repo}/hooks/inbox_isolation_clear.py",
    }


def _merged_hooks(
    events: dict[str, list[dict[str, Any]]], repo: Path
) -> dict[str, list[dict[str, Any]]]:
    merged = copy.deepcopy(events)
    commands = _harness_commands(repo)
    owned = set(commands.values())

    # Orca can copy the previous global hooks file before rewriting its own
    # entries.  Remove all old harness occurrences before adding canonical ones.
    for event, groups in list(merged.items()):
        kept_groups = []
        for group in groups:
            kept_hooks = [
                hook for hook in group["hooks"] if hook.get("command") not in owned
            ]
            if kept_hooks:
                group["hooks"] = kept_hooks
                kept_groups.append(group)
            elif not group["hooks"]:
                kept_groups.append(group)
        merged[event] = kept_groups

    merged.setdefault("PreToolUse", []).extend(
        [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": commands["git"],
                        "timeout": 30,
                    }
                ],
            },
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": commands["guard"],
                        "timeout": 30,
                    }
                ],
            },
        ]
    )
    merged.setdefault("UserPromptSubmit", []).append(
        {
            "hooks": [
                {
                    "type": "command",
                    "command": commands["clear"],
                    "timeout": 30,
                }
            ]
        }
    )
    return merged


def _toml_key(value: str) -> str:
    return value if BARE_KEY.fullmatch(value) else json.dumps(value, ensure_ascii=False)


def _toml_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        fields = ", ".join(
            f"{_toml_key(key)} = {_toml_value(item)}" for key, item in value.items()
        )
        return "{ " + fields + " }"
    raise HookConfigError(f"hook value has no safe TOML representation: {value!r}")


def _render_hooks(events: dict[str, list[dict[str, Any]]]) -> str:
    lines: list[str] = []
    for event, groups in events.items():
        event_key = _toml_key(event)
        for group in groups:
            lines.extend(["", f"[[hooks.{event_key}]]"])
            for key, value in group.items():
                if key == "hooks" or value is None:
                    continue
                lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
            for hook in group["hooks"]:
                lines.extend(["", f"[[hooks.{event_key}.hooks]]"])
                for key, value in hook.items():
                    if value is not None:
                        lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    return "\n".join(lines).lstrip("\n") + "\n"


def _top_level_lines(lines: list[str], config_path: Path) -> list[bool]:
    """Mark lines that do not begin inside a TOML multiline string."""
    state: str | None = None
    result: list[bool] = []
    for line in lines:
        result.append(state is None)
        cursor = 0
        while cursor < len(line):
            if state == "basic":
                if line[cursor] == "\\":
                    cursor += 2
                elif line.startswith('"""', cursor):
                    state = None
                    cursor += 3
                else:
                    cursor += 1
                continue
            if state == "literal":
                if line.startswith("'''", cursor):
                    state = None
                    cursor += 3
                else:
                    cursor += 1
                continue
            if line[cursor] == "#":
                break
            if line.startswith('"""', cursor):
                state = "basic"
                cursor += 3
            elif line.startswith("'''", cursor):
                state = "literal"
                cursor += 3
            elif line[cursor] == '"':
                cursor += 1
                while cursor < len(line):
                    if line[cursor] == "\\":
                        cursor += 2
                    elif line[cursor] == '"':
                        cursor += 1
                        break
                    else:
                        cursor += 1
            elif line[cursor] == "'":
                closing = line.find("'", cursor + 1)
                cursor = len(line) if closing < 0 else closing + 1
            else:
                cursor += 1
    if state is not None:
        raise HookConfigError(f"unterminated multiline string in {config_path}")
    return result


def _dotted_key(value: str) -> tuple[str, ...] | None:
    parts: list[str] = []
    cursor = 0
    while cursor < len(value):
        while cursor < len(value) and value[cursor].isspace():
            cursor += 1
        if cursor >= len(value):
            return None
        if value[cursor] == '"':
            start = cursor
            cursor += 1
            escaped = False
            while cursor < len(value):
                char = value[cursor]
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    cursor += 1
                    break
                cursor += 1
            else:
                return None
            try:
                part = json.loads(value[start:cursor])
            except ValueError:
                return None
        elif value[cursor] == "'":
            end = value.find("'", cursor + 1)
            if end < 0:
                return None
            part = value[cursor + 1 : end]
            cursor = end + 1
        else:
            start = cursor
            while (
                cursor < len(value)
                and not value[cursor].isspace()
                and value[cursor] != "."
            ):
                cursor += 1
            part = value[start:cursor]
            if not BARE_KEY.fullmatch(part):
                return None
        parts.append(part)
        while cursor < len(value) and value[cursor].isspace():
            cursor += 1
        if cursor == len(value):
            break
        if value[cursor] != ".":
            return None
        cursor += 1
    return tuple(parts)


def _table_header(line: str) -> tuple[bool, tuple[str, ...]] | None:
    stripped = line.lstrip()
    if not stripped.startswith("["):
        return None
    array = stripped.startswith("[[")
    opening = 2 if array else 1
    closing = "]]" if array else "]"
    cursor = opening
    quote: str | None = None
    escaped = False
    while cursor < len(stripped):
        char = stripped[cursor]
        if quote == '"':
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = None
            cursor += 1
            continue
        if quote == "'":
            if char == "'":
                quote = None
            cursor += 1
            continue
        if char in ('"', "'"):
            quote = char
            cursor += 1
            continue
        if stripped.startswith(closing, cursor):
            remainder = stripped[cursor + len(closing) :].strip()
            if remainder and not remainder.startswith("#"):
                return None
            path = _dotted_key(stripped[opening:cursor].strip())
            return (array, path) if path else None
        cursor += 1
    return None


COMMAND_RE = re.compile(
    r'^\s*command\s*=\s*("(?:[^"\\]|\\.)*")\s*(?:#.*)?(?:\r?\n)?$'
)


def _strip_owned_hook_tables(
    text: str, owned_commands: set[str], config_path: Path
) -> tuple[str, set[str]]:
    """Remove only hook table entries whose command is owned by this launch."""
    lines = text.splitlines(keepends=True)
    top_level = _top_level_lines(lines, config_path)
    headers: list[tuple[int, bool, tuple[str, ...]]] = []
    for index, line in enumerate(lines):
        if not top_level[index]:
            continue
        header = _table_header(line)
        if header is not None:
            headers.append((index, header[0], header[1]))

    remove = {
        index
        for index, line in enumerate(lines)
        if top_level[index] and line.rstrip("\r\n") in LEGACY_MARKERS
    }
    seen: set[str] = set()
    for position, (start, array, path) in enumerate(headers):
        if not array or len(path) != 2 or path[0] != "hooks":
            continue
        child_path = ("hooks", path[1], "hooks")
        following = position + 1
        children: list[tuple[int, int, str | None]] = []
        while following < len(headers):
            child_start, child_array, child = headers[following]
            if not child_array or child != child_path:
                break
            child_end = (
                headers[following + 1][0]
                if following + 1 < len(headers)
                else len(lines)
            )
            commands = []
            for line_index in range(child_start + 1, child_end):
                if not top_level[line_index]:
                    continue
                match = COMMAND_RE.match(lines[line_index])
                if match:
                    try:
                        commands.append(json.loads(match.group(1)))
                    except ValueError:
                        # TOML basic strings support a few escapes JSON does
                        # not. Unknown/user hook strings stay untouched.
                        continue
            if len(commands) > 1:
                raise HookConfigError(
                    f"duplicate command keys in hook table at {config_path}:{child_start + 1}"
                )
            command = commands[0] if commands else None
            if command is not None:
                seen.add(command)
            children.append((child_start, child_end, command))
            following += 1
        targets = [child for child in children if child[2] in owned_commands]
        if not targets:
            continue

        def mark_table(table_start: int, table_end: int) -> None:
            while table_end > table_start + 1:
                tail = lines[table_end - 1]
                if tail.strip() and not tail.lstrip().startswith("#"):
                    break
                table_end -= 1
            remove.update(range(table_start, table_end))

        if len(targets) == len(children):
            prefix_end = children[0][0]
            mark_table(start, prefix_end)
        for child_start, child_end, _ in targets:
            mark_table(child_start, child_end)

    return "".join(line for index, line in enumerate(lines) if index not in remove), seen


def _append_hook_tables(text: str, block: str) -> str:
    if not text:
        return block
    separator = (
        "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    )
    return text + separator + block


def _atomic_replace(path: Path, expected: tuple[bytes, int] | None, text: str) -> bool:
    mode = expected[1] if expected is not None else 0o600
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        if _snapshot(path) != expected:
            return False
        os.replace(temporary, path)
        return True
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def preflight(codex_home: Path) -> None:
    config_path = codex_home / "config.toml"
    config = _snapshot(config_path)
    if config is not None:
        try:
            text = config[0].decode("utf-8")
        except UnicodeError as exc:
            raise HookConfigError(f"invalid UTF-8 in {config_path}: {exc}") from exc
        _strip_owned_hook_tables(text, set(), config_path)
    hooks_path = codex_home / "hooks.json"
    hooks = _snapshot(hooks_path)
    if hooks is not None:
        _load_hooks(hooks_path, hooks[0])


def activate(codex_home: Path, repo: Path) -> None:
    codex_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    hooks_path = codex_home / "hooks.json"
    config_path = codex_home / "config.toml"
    lock_path = codex_home / ".harness-codex-hooks.lock"

    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for _ in range(5):
            hooks = _snapshot(hooks_path)
            config = _snapshot(config_path)
            if hooks is None:
                if config is not None:
                    try:
                        text = config[0].decode("utf-8")
                    except UnicodeError as exc:
                        raise HookConfigError(
                            f"invalid UTF-8 in {config_path}: {exc}"
                        ) from exc
                    _, existing = _strip_owned_hook_tables(text, set(), config_path)
                    if set(_harness_commands(repo).values()) <= existing:
                        return
                raise HookConfigError(
                    f"{hooks_path} is missing after Orca terminal creation"
                )

            events = _load_hooks(hooks_path, hooks[0])
            if config is None:
                config_text = ""
            else:
                try:
                    config_text = config[0].decode("utf-8")
                except UnicodeError as exc:
                    raise HookConfigError(
                        f"invalid UTF-8 in {config_path}: {exc}"
                    ) from exc
            source_commands = {
                hook.get("command")
                for groups in events.values()
                for group in groups
                for hook in group["hooks"]
                if isinstance(hook.get("command"), str)
            }
            owned = source_commands | set(_harness_commands(repo).values())
            cleaned, _ = _strip_owned_hook_tables(config_text, owned, config_path)
            rendered = _render_hooks(_merged_hooks(events, repo))
            updated = _append_hook_tables(cleaned, rendered)
            if not _atomic_replace(config_path, config, updated):
                continue
            if _snapshot(hooks_path) != hooks:
                continue
            hooks_path.unlink()
            return
    raise HookConfigError("concurrent Codex hook updates did not settle")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preflight", "activate"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
    )
    args = parser.parse_args(argv)
    try:
        if args.action == "preflight":
            preflight(args.codex_home)
        else:
            activate(args.codex_home, args.repo.resolve())
    except (HookConfigError, OSError) as exc:
        print(f"error: cannot prepare Codex hooks: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
