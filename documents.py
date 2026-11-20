# -*- coding: utf-8 -*-
"""documents.py -- Document layer: file classification, dialogue windows, continuation fragments."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Iterable, Optional
try:
    from . import lvparse as P
except ImportError:
    import lvparse as P

try:
    from .field_types import Field, MEMO_LINE_RE, NON_DISPLAY_MARKERS, PLUGIN_DOC_HEADING_RE, ParsedLine, SECTION_HEADER_RE, URL_RE, WAIT_END_RE, WS
except ImportError:
    from field_types import Field, MEMO_LINE_RE, NON_DISPLAY_MARKERS, PLUGIN_DOC_HEADING_RE, ParsedLine, SECTION_HEADER_RE, URL_RE, WAIT_END_RE, WS
try:
    from .grammar import _display_children, _is_bare_wait_marker, _line_body_end
except ImportError:
    from grammar import _display_children, _is_bare_wait_marker, _line_body_end
try:
    from .schema import KNOWN_SCHEMA_COMMANDS, _project_macro_names, _starts_with_command
except ImportError:
    from schema import KNOWN_SCHEMA_COMMANDS, _project_macro_names, _starts_with_command
try:
    from .line_parser import parse_line
except ImportError:
    from line_parser import parse_line


def classify_document_role(rows: Iterable[str]) -> str:
    """Classify one extracted .txt by shape.

    Extracted source directories mix real scripts with credits pages, gameplay
    notes, voice manifests and the author's own patch notes.  They are all .txt
    and none of them contains a command, so a command-only classifier reports
    them as unknown prose.  This separates the ones a player can read from the
    ones that are only build metadata.
    """
    body = [row[:_line_body_end(row)] for row in rows]
    body = [line for line in body if line.strip()]
    if not body:
        return "empty"
    total = len(body)
    tabbed = sum(1 for line in body if "\t" in line)
    ideographic_columns = sum(
        1 for line in body
        if len([part for part in line.split("\u3000") if part.strip()]) >= 2
    )
    commands = sum(1 for line in body if _starts_with_command(line))
    memo = sum(1 for line in body
               if MEMO_LINE_RE.search(line.strip())
               or "※新規追加" in line or "元名：" in line)
    plugin_headings = sum(1 for line in body
                          if PLUGIN_DOC_HEADING_RE.match(line.strip()))
    prose = sum(1 for line in body
                if re.search(r"[。．！？…]$", line.strip()) and len(line.strip()) >= 8)
    identifiers = sum(
        1 for line in body
        if re.fullmatch(r"[A-Za-z0-9_./@:+-]+", line.strip())
    )
    # Command-heavy files remain scripts, even when they contain notes.
    # Check tabular payloads after the script threshold.
    if commands / total >= 0.25:
        return "script_with_notes" if memo / total >= 0.10 else "script"
    if max(tabbed, ideographic_columns) / total >= 0.25:
        return "data_table"
    if identifiers / total >= 0.45:
        return "asset_manifest"
    if plugin_headings >= 2:
        return "plugin_document"
    has_dialogue_shape = any(
        re.match(r'^\s*[~.]?\s*(?:"|「|『)', line) for line in body
    )
    if commands >= 2 or (commands >= 1 and has_dialogue_shape):
        return "mixed_script"
    if prose / total >= 0.25:
        return "doc_text"
    if memo / total >= 0.10:
        return "author_note"
    return "unknown_document"


def triage_unresolved_line(raw: str, document_role: str = "script") -> str:
    """Give an unresolved row an actionable category without making it translatable.

    This is deliberately separate from :func:`parse_line`: a line may remain
    structurally unknown while the document context proves that it is a note,
    table row, asset identifier, or section header.  Triage improves review
    coverage reporting without weakening the conservative edit gate.
    """
    body = raw[:_line_body_end(raw)].strip()
    if not body:
        return "EMPTY"
    if SECTION_HEADER_RE.match(body):
        return "SECTION_HEADER"
    if MEMO_LINE_RE.match(body) or body.startswith(("※", "//", "/*", "*/")):
        return "MEMO_LINE"
    # Engine/plugin manuals occasionally embed executable-looking snippets
    # inside Japanese corner quotes and annotate them with arrows.  They are
    # documentation examples, not scenario instructions.
    if (body.startswith(("「", "『")) and
            any(marker in body for marker in ("←", "→", "⇒"))):
        return "DOCUMENT_EXAMPLE"
    if document_role == "data_table":
        return "DATA_ROW"
    if document_role in {"author_note", "doc_text", "script_with_notes", "plugin_document"}:
        return "DOCUMENT_TEXT"
    if document_role == "mixed_script":
        return "UNKNOWN_SCRIPT"
    if document_role == "asset_manifest":
        return "IDENTIFIER_DATA"
    if URL_RE.fullmatch(body):
        return "EXTERNAL_REFERENCE"
    if re.fullmatch(r"[A-Za-z0-9_./@:+-]+", body):
        return "IDENTIFIER_DATA"
    if not any(mark in body for mark in ('"', "\\w", "\\W", "|")):
        return "UNCLASSIFIED_PROSE"
    return "UNKNOWN_SCRIPT"


def _ends_text_window(parsed: ParsedLine, raw: str) -> bool:
    if parsed.kind != "dialogue":
        return False
    for item in parsed.fields:
        if item.role == "DISPLAY" and WAIT_END_RE.search(item.value):
            return True
    return False


def _continued_bare_dialogue_end(rows: list[str], parsed: list[ParsedLine], start: int) -> Optional[tuple[int, bool]]:
    """Find a bare prose continuation after a quoted row's wait marker.

    Some scripts use ``"first page\\w`` followed by unquoted
    physical rows and a final ``\\w``.  The rows are one visible text block,
    but the first wait marker must not close the extraction window early.
    Only accept a contiguous prose run with an explicit later terminator.
    """
    j = start
    found_prose = False
    last_prose = None
    leading_blanks = 0
    while j < len(rows):
        body = rows[j][:_line_body_end(rows[j])]
        if not body.strip():
            if not found_prose:
                leading_blanks += 1
                if leading_blanks > 2:
                    return None
                j += 1
                continue
            return (last_prose, False) if last_prose is not None else None
        if body.strip() in NON_DISPLAY_MARKERS:
            j += 1
            continue
        if j > start and (body.lstrip().startswith(('"', '-"', '~'))
                           or parsed[j].kind in {"command", "command_chain", "comment", "speaker", "code"}):
            return (last_prose, False) if last_prose is not None else None
        if _is_bare_wait_marker(body):
            return (j, True) if found_prose else None
        prose_body = WAIT_END_RE.sub("", body).rstrip() if WAIT_END_RE.search(body) else body
        if not _bare_dialogue_candidate(prose_body):
            return (last_prose, False) if last_prose is not None else None
        found_prose = True
        last_prose = j
        if WAIT_END_RE.search(body):
            return (j, True)
        j += 1
    return (last_prose, False) if last_prose is not None else None


def _bare_dialogue_candidate(raw: str) -> bool:
    """Return whether an unquoted row is plausible visible prose.

    This is intentionally stricter than merely checking for Japanese text:
    runtime files also contain author notes, JSON-ish payloads, and labels.
    The candidate is only promoted at document level when a nearby `\\w`
    terminator closes the run.
    """
    body = raw[:_line_body_end(raw)]
    stripped = body.strip()
    # Renai uses a leading dot as the physical-row marker for prose that is
    # continued outside the opening quote.  A known dot-prefixed command must
    # remain code; only the unknown, prose-shaped form is a candidate here.
    if stripped.startswith("."):
        dot_text = stripped[1:].lstrip(WS)
        if not dot_text:
            return False
        dot_end = 0
        while dot_end < len(dot_text) and dot_text[dot_end] not in WS:
            dot_end += 1
        dot_command = dot_text[:dot_end]
        if (dot_command in KNOWN_SCHEMA_COMMANDS
                or dot_command in {"もし", "違ってももし", "違ったら"}
                or dot_command in _project_macro_names()
                or P.is_known_command(dot_command)):
            return False
        stripped = dot_text
    starts_with_variable = bool(re.match(r"^\{\{[^{}\r\n]+\}\}", stripped))
    if (not stripped or re.fullmatch(r"\\+w", stripped)
            or re.fullmatch(r"[-=]{3,}[^\r\n]*[-=]{3,}", stripped)
            or '"' in stripped
            or stripped.startswith(("//", "#", "■", "栞 ", "栞\t", "栞\u3000",
                                    "}", "/*", "*/", "s/", "~"))
            or (stripped.startswith("{") and not starts_with_variable)):
        return False
    if WAIT_END_RE.search(stripped):
        return False
    probe = 0
    while probe < len(body) and body[probe] in WS:
        probe += 1
    if probe < len(body) and body[probe] == ".":
        probe += 1
        while probe < len(body) and body[probe] in WS:
            probe += 1
    end = probe
    while end < len(body) and body[end] not in WS:
        end += 1
    candidate = body[probe:end]
    return bool(candidate and candidate not in KNOWN_SCHEMA_COMMANDS
                and candidate not in {"もし", "違ってももし", "違ったら"}
                and candidate not in _project_macro_names()
                and not P.is_known_command(candidate))


def _display_body_span(raw: str) -> tuple[int, int]:
    """Return the translatable span for a bare display row.

    A leading dot in Renai is a syntax marker, not visible prose.  Keep it
    outside the display field so replacement cannot delete the marker.
    """
    body_end = _line_body_end(raw)
    body = raw[:body_end]
    start = 0
    while start < body_end and body[start] in WS:
        start += 1
    if start < body_end and body[start] == ".":
        start += 1
    return start, body_end


def _infer_bare_dialogue_end(rows: list[str], parsed: list[ParsedLine], start: int) -> Optional[int]:
    """Find a short unquoted prose run terminated by a bare `\\w` row."""
    start_body = rows[start][:_line_body_end(rows[start])]
    start_probe = (WAIT_END_RE.sub("", start_body).rstrip()
                   if WAIT_END_RE.search(start_body) else start_body)
    if not _bare_dialogue_candidate(start_probe):
        return None
    j = start
    while j < len(rows):
        current = rows[j]
        body = current[:_line_body_end(current)]
        if not body.strip():
            return None
        if j > start and _is_bare_wait_marker(body):
            return j
        if j > start and parsed[j].kind in {"command", "command_chain", "comment", "speaker", "code"}:
            return None
        if j > start and body.lstrip().startswith(('"', '-"', '~')):
            return None
        if j > start and not _bare_dialogue_candidate(body) and not WAIT_END_RE.search(body):
            return None
        if WAIT_END_RE.search(body):
            prose_body = WAIT_END_RE.sub("", body).rstrip()
            if re.fullmatch(r"\\+w", body.strip()) or _bare_dialogue_candidate(prose_body):
                return j
            return None
        j += 1
    return None


def group_dialogue_windows(lines: Iterable[str], parsed_rows: Optional[list[ParsedLine]] = None) -> list[dict]:
    """Group bare dialogue and physical continuation rows up to a `\\w` marker.

    Ambiguous boundaries are not silently glued together: the preceding record
    is returned with complete=False so callers can require review.
    """
    rows = list(lines)
    parsed = parsed_rows if parsed_rows is not None else [parse_line(row) for row in rows]
    if len(parsed) != len(rows):
        raise ValueError("parsed row count does not match source lines")
    windows = []
    i = 0
    while i < len(rows):
        if parsed[i].kind != "dialogue":
            inferred_end = _infer_bare_dialogue_end(rows, parsed, i)
            if inferred_end is not None:
                windows.append({"start": i, "end": inferred_end, "complete": True,
                                "inferred": True,
                                "end_reason": "inferred_wait",
                                "raw_lines": rows[i:inferred_end + 1]})
                i = inferred_end + 1
                continue
            i += 1
            continue
        start = i
        end = i
        if _ends_text_window(parsed[i], rows[i][:_line_body_end(rows[i])]):
            continuation = _continued_bare_dialogue_end(rows, parsed, i + 1)
            if continuation is not None:
                continued_end, continued_complete = continuation
                windows.append({"start": start, "end": continued_end, "complete": continued_complete,
                                "inferred": False,
                                "end_reason": "ambiguous_after_wait" if not continued_complete else "wait",
                                "raw_lines": rows[start:continued_end + 1]})
                i = continued_end + 1
            else:
                windows.append({"start": start, "end": end, "complete": True,
                                "inferred": False,
                                "end_reason": "wait",
                                "raw_lines": rows[start:end + 1]})
                i += 1
            continue
        j = i + 1
        complete = False
        end_reason = "eof"
        while j < len(rows):
            current = rows[j][:_line_body_end(rows[j])]
            p = parsed[j]
            # A few in-game memo blocks put a physical blank line between
            # the last display row and a standalone wait marker.  Treat that
            # exact pattern as the terminator, while keeping other blank-line
            # boundaries hard so unrelated blocks are never merged.
            if (not current.strip() and j + 1 < len(rows)
                    and _is_bare_wait_marker(rows[j + 1])):
                end = j + 1
                complete = True
                end_reason = "blank_before_wait"
                j += 2
                break
            if _is_bare_wait_marker(current):
                end = j
                complete = True
                end_reason = "wait"
                j += 1
                break
            if current.strip() in NON_DISPLAY_MARKERS:
                end = j
                j += 1
                continue
            # These are hard boundaries. Do not absorb the next construct.
            if not current.strip() or p.kind in {"command", "command_chain", "comment", "speaker", "code"}:
                complete = True
                end_reason = "boundary"
                break
            # A fresh quoted dialogue starts a new window.  The engine's
            # explicit `-"...` continuation form is the one exception used by
            # the corpus and by the adjacent-row syntax.
            if p.kind == "dialogue":
                continuation_marker = (
                    current.lstrip().startswith('-"')
                    or re.search(r"\)\s*-\s*", current) is not None
                    # Bare dialogue rows are also used as physical
                    # continuations.  They are safe to absorb here because
                    # this branch is reached only while the preceding
                    # dialogue window is still open.
                    or not current.lstrip().startswith(('"', '-"',
                                                         '~もし', '~違ってももし'))
                )
                if not continuation_marker:
                    complete = True
                    end_reason = "next_dialogue"
                    break
            if current.lstrip().startswith(("#", "■", "栞 ", "栞\t", "栞\u3000")):
                complete = True
                end_reason = "next_label"
                break
            end = j
            if _ends_text_window(p, current) or WAIT_END_RE.search(current):
                complete = True
                j += 1
                break
            j += 1
        if j >= len(rows):
            complete = True
            end_reason = "eof"
        windows.append({"start": start, "end": end, "complete": complete,
                        "inferred": False,
                        "end_reason": end_reason,
                        "raw_lines": rows[start:end + 1]})
        i = end + 1 if end >= start else start + 1
    return windows


def parse_document(lines: Iterable[str], parsed_rows: Optional[list[ParsedLine]] = None) -> list[dict]:
    """Extract dialogue text windows across physical continuation rows.

    Line parsing alone cannot know whether an unquoted prose row continues a
    dialogue. This document-level pass uses the window boundaries and exposes
    every physical-row fragment.  ``complete`` describes whether the
    structural boundary is known; it does not mean that the final row has a
    ``\\w`` wait marker.  See ``end_reason`` for the distinction.
    """
    rows = list(lines)
    parsed = parsed_rows if parsed_rows is not None else [parse_line(row) for row in rows]
    if len(parsed) != len(rows):
        raise ValueError("parsed row count does not match source lines")
    windows = group_dialogue_windows(rows, parsed)
    for window in windows:
        fragments = []
        for line_index in range(window["start"], window["end"] + 1):
            row = rows[line_index]
            body = row[:_line_body_end(row)]
            row_parsed = parsed[line_index]
            if (not body.strip() or _is_bare_wait_marker(body)
                    or body.strip() in NON_DISPLAY_MARKERS):
                continue
            display_fields = [field for field in row_parsed.fields if field.role == "DISPLAY"]
            bare_continuation = (
                line_index > window["start"]
                and not body.lstrip().startswith(('"', '-"', '~もし', '~違ってももし'))
            )
            if display_fields and not bare_continuation:
                fragments.extend({"line": line_index + 1, "field": field} for field in display_fields)
            elif line_index == window["start"] and window.get("inferred"):
                display_start, display_end = _display_body_span(body)
                display_raw = body[display_start:display_end]
                frag = Field("DISPLAY_INFERRED", display_start, display_end,
                             display_raw, display_raw, True,
                             _display_children(display_raw, display_start, False))
                fragments.append({"line": line_index + 1, "field": frag})
            elif line_index > window["start"]:
                # A row inside an open dialogue window is visible continuation
                # text, even when it has no leading quote marker.
                display_start, display_end = _display_body_span(body)
                display_raw = body[display_start:display_end]
                frag = Field("DISPLAY_CONTINUATION", display_start, display_end,
                             display_raw, display_raw, True,
                             _display_children(display_raw, display_start, False))
                fragments.append({"line": line_index + 1, "field": frag})
        window["fragments"] = fragments
        window["review_required"] = not window["complete"]
    return windows


def classify_source_content(content: str) -> str:
    """Classify obvious non-script payloads without silently dropping ambiguity.

    Extracted source directories can contain assets with a `.txt` suffix.  Only
    positively identified data formats are excluded from script parsing;
    everything else remains a script candidate and is still audited.
    """
    first = next((line.strip().lstrip("\ufeff") for line in content.splitlines() if line.strip()), "")
    if re.match(r"#version\s+\d+", first):
        return "shader"
    if first.startswith("<"):
        try:
            ET.fromstring(content)
        except ET.ParseError:
            pass
        else:
            return "xml_data"
    # Tiled exports sometimes have a trailing comma or other non-strict JSON,
    # so use their distinctive root keys before attempting strict decoding.
    if first.startswith("{") and '"compressionlevel"' in content[:8192] and '"layers"' in content[:8192]:
        return "tiled_map_json"
    if first.startswith(("{", "[")):
        try:
            value = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            pass
        else:
            if isinstance(value, dict) and {"width", "height", "layers"}.issubset(value):
                return "tiled_map_json"
            return "json_data"
    return "script_candidate"
