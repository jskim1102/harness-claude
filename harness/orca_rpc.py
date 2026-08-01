#!/usr/bin/env python3
"""Orca 런타임 RPC 최소 클라이언트 — CLI 가 노출하지 않는 메서드를 부른다.

왜 필요한가 (2026-07-23): `orca` CLI 에는 프로젝트를 **완전히** 제거하는 명령이
없다. `project setup-delete` 는 repo 행만 지우고 `worktreeMeta` 항목을 남겨,
Orca UI 에 이름 없는 "Unknown" 프로젝트가 영구히 쌓인다 (repo 가 사라져서
`worktree rm` 은 `repo_not_found`, main 워크트리라 `--force` 도 거부, 앱이 떠
있으면 상태파일 직접 편집도 런타임이 덮어씀 → 어느 경로로도 못 지운다).

런타임에는 `repo.rm` 이 있고 그건 `removeProject()` → `pruneWorktreeStateForRepo()`
까지 타서 worktreeMeta·lineage 를 같이 정리한다. UI 의 설정 화면 삭제가 쓰는 경로가
이것이다. CLI 만 이 메서드를 안 감쌌을 뿐이라, 같은 유닉스 소켓 프로토콜로 직접 부른다.

프로토콜 (orca `src/cli/runtime/transport.ts`): 소켓에 JSON 한 줄
`{id, authToken, method, params}\n` 을 쓰고, 줄 단위 JSON 프레임을 읽는다.
`{"_keepalive":true}` 프레임은 무시하고 id 가 일치하는 종단 프레임을 취한다.

    python3 harness/orca_rpc.py repo.rm '{"repo": "id:<repo-uuid>"}'
    python3 harness/orca_rpc.py repo.list '{}'
"""
from __future__ import annotations

import json
import socket
import sys
import uuid
from pathlib import Path

META = Path.home() / ".config/orca/orca-runtime.json"
TIMEOUT_S = 20.0


class OrcaRpcError(RuntimeError):
    pass


def _endpoint(meta: dict) -> str:
    for t in meta.get("transports", []):
        if t.get("kind") in ("unix", "named-pipe") and t.get("endpoint"):
            return t["endpoint"]
    raise OrcaRpcError("런타임 메타데이터에 unix 트랜스포트가 없다")


def call(method: str, params: dict | None = None, timeout: float = TIMEOUT_S) -> dict:
    """런타임 RPC 1회 호출. 성공하면 result 를, 실패하면 OrcaRpcError."""
    if not META.exists():
        raise OrcaRpcError(f"런타임 메타데이터 없음: {META} (Orca 미실행?)")
    meta = json.loads(META.read_text())
    req_id = str(uuid.uuid4())
    payload = {
        "id": req_id,
        "authToken": meta.get("authToken"),
        "method": method,
        "params": params or {},
    }

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(_endpoint(meta))
        sock.sendall((json.dumps(payload) + "\n").encode())
        buf = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                raise OrcaRpcError("런타임이 응답 전에 연결을 닫았다")
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                frame = json.loads(line)
                if frame.get("_keepalive"):
                    continue  # 롱폴 유지 프레임 — 무시하고 계속 읽는다
                if frame.get("id") != req_id:
                    raise OrcaRpcError(f"응답 id 불일치: {frame.get('id')}")
                if not frame.get("ok"):
                    err = frame.get("error") or {}
                    raise OrcaRpcError(
                        f"{err.get('code', 'error')}: {err.get('message', frame)}"
                    )
                return frame.get("result") or {}
    finally:
        sock.close()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[-3].strip(), file=sys.stderr)
        return 2
    method = argv[1]
    params = json.loads(argv[2]) if len(argv) > 2 else {}
    try:
        print(json.dumps(call(method, params), ensure_ascii=False, indent=2))
    except OrcaRpcError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
