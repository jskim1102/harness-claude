from __future__ import annotations

import re
import unicodedata


def normalize(value: object | None) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().lower()


def tokens(value: object | None) -> set[str]:
    return set(re.findall(r"[0-9A-Za-z가-힣]+", normalize(value)))
