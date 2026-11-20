# -*- coding: utf-8 -*-
"""grammar.py -- Lexical layer: quotes, segments, tokens, brackets, and display-token children."""

from __future__ import annotations

import re
from typing import Iterable, Optional

try:
    from .field_types import Field, TOKEN_RE, WS
except ImportError:
    from field_types import Field, TOKEN_RE, WS


def _quote_end(s: str, start: int) -> int:
    i = start + 1
    while i < len(s):
        if s[i] == "\\":
            i += 2
        elif s[i] == '"':
            return i + 1
        else:
            i += 1
    return len(s)


def _segments(s: str) -> list[tuple[int, int]]:
    """Split ` | ` only outside quoted strings, retaining exact source spans."""
    out = []
    start = 0
    i = 0
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == '"':
            i = _quote_end(s, i)
            continue
        if s.startswith(" | ", i):
            out.append((start, i))
            i += 3
            start = i
            continue
        i += 1
    out.append((start, len(s)))
    return out


def _line_body_end(line: str) -> int:
    if line.endswith("\r\n"):
        return len(line) - 2
    if line.endswith(("\r", "\n")):
        return len(line) - 1
    return len(line)


def _tokens(s: str, start: int, end: int) -> list[tuple[int, int, bool]]:
    """Whitespace-delimited argument spans; quoted arguments include quotes."""
    out = []
    i = start
    while i < end:
        while i < end and s[i] in WS:
            i += 1
        if i >= end:
            break
        a = i
        if s[i] == '"':
            i = min(_quote_end(s, i), end)
            out.append((a, i, True))
        else:
            while i < end and s[i] not in WS:
                if s[i] == "\\":
                    # Keep a trailing backslash inside the current token.
                    i = min(i + 2, end)
                else:
                    i += 1
            out.append((a, i, False))
    return out


def _display_children(raw: str, absolute_start: int, quoted: bool) -> list[Field]:
    left = 1 if quoted and raw.startswith('"') else 0
    right = 1 if quoted and len(raw) > left and raw.endswith('"') else 0
    content_start = left
    content_end = len(raw) - right
    children = []
    cursor = content_start
    for match in TOKEN_RE.finditer(raw, content_start, content_end):
        if match.start() > cursor:
            value = raw[cursor:match.start()]
            children.append(Field("DISPLAY_TEXT", absolute_start + cursor, absolute_start + match.start(), value, value, True))
        token = match.group(0)
        if token.startswith("{{"):
            role = "VARIABLE_REF"
        elif token.startswith("<"):
            role = "MARKUP"
        else:
            role = "CONTROL_TOKEN"
        children.append(Field(role, absolute_start + match.start(), absolute_start + match.end(), token, token))
        cursor = match.end()
    if cursor < content_end:
        value = raw[cursor:content_end]
        children.append(Field("DISPLAY_TEXT", absolute_start + cursor, absolute_start + content_end, value, value, True))
    return children


def _is_bare_wait_marker(raw: str) -> bool:
    body = raw[:_line_body_end(raw)].strip()
    return bool(re.fullmatch(r"\\+w[。．.!！?？…]*", body))
