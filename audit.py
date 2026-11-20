# -*- coding: utf-8 -*-
"""audit.py -- Corpus scan and CLI."""

from __future__ import annotations

import argparse
import json
import os
from typing import Optional

try:
    from .field_types import NON_DISPLAY_MARKERS
except ImportError:
    from field_types import NON_DISPLAY_MARKERS
try:
    from .grammar import _is_bare_wait_marker, _line_body_end
except ImportError:
    from grammar import _is_bare_wait_marker, _line_body_end
try:
    from .line_parser import parse_line
except ImportError:
    from line_parser import parse_line
try:
    from .documents import classify_document_role, classify_source_content, parse_document, triage_unresolved_line
except ImportError:
    from documents import classify_document_role, classify_source_content, parse_document, triage_unresolved_line
try:
    from .inference import infer_display_parameter_indices, infer_display_variable_roles, promote_inferred_display_arguments, promote_inferred_display_assignments
except ImportError:
    from inference import infer_display_parameter_indices, infer_display_variable_roles, promote_inferred_display_arguments, promote_inferred_display_assignments


def scan_directory(path: str) -> dict:
    """Read-only script-candidate scan; obvious non-script .txt assets are counted separately."""
    stats = {"files": 0, "files_total": 0, "non_script_files": 0, "lines": 0,
             "roundtrip_mismatches": 0, "commands": 0,
             "dialogue_lines": 0, "display_fields": 0, "speaker_fields": 0,
             "dialogue_continuation_fields": 0, "unknown_lines": 0,
             "unknown_continuation_lines": 0, "unresolved_unknown_lines": 0,
             "inferred_display_fields": 0,
             "comments": 0, "dialogue_windows": 0, "complete_windows": 0,
             "incomplete_windows": 0, "unknown_quoted_fields": 0,
             "raw_unknown_quoted_fields": 0,
             "opaque_nested_fields": 0, "unclassified_spans": 0,
             "window_uncovered_rows": 0, "incomplete_windows_without_display": 0,
             "inferred_display_arguments": 0, "inferred_display_assignments": 0,
             "protected_display_assignments": 0,
             "role_counts": {}, "file_types": {}, "document_roles": {},
             "unknown_command_counts": {}, "unresolved_unknown_by_file": {},
             "incomplete_windows_by_file": {},
             "unresolved_unknown_categories": {},
             "actionable_unknown_lines": 0}
    examples = {"roundtrip": [], "display": [], "unknown_commands": [],
                "unknown_quoted": [], "raw_unknown_quoted": [],
                "unresolved_unknown": [],
                "incomplete_windows": [], "window_uncovered": [],
                "non_script_files": []}
    display_parameters = infer_display_parameter_indices(path)
    display_variable_roles = infer_display_variable_roles(path)
    display_variables = display_variable_roles["safe"]
    unsafe_display_variables = display_variable_roles["unsafe"]
    for filename in sorted(os.listdir(path)):
        if not filename.lower().endswith(".txt"):
            continue
        full = os.path.join(path, filename)
        with open(full, "r", encoding="utf-8", errors="surrogateescape", newline="") as stream:
            content = stream.read()
        file_type = classify_source_content(content)
        stats["files_total"] += 1
        stats["file_types"][file_type] = stats["file_types"].get(file_type, 0) + 1
        if file_type != "script_candidate":
            stats["non_script_files"] += 1
            if len(examples["non_script_files"]) < 50:
                examples["non_script_files"].append([filename, file_type])
            continue
        stats["files"] += 1
        # Keep CR as part of raw line; split only on LF, matching byte-preserving text format.
        rows = content.split("\n")
        document_role = classify_document_role(rows)
        stats["document_roles"][document_role] = (
            stats["document_roles"].get(document_role, 0) + 1)
        parsed_rows = []
        file_unknown_quoted = []
        for line_no, raw in enumerate(rows, 1):
            stats["lines"] += 1
            parsed = parse_line(raw)
            parsed_rows.append(parsed)
            stats["inferred_display_arguments"] += promote_inferred_display_arguments(
                parsed, display_parameters)
            promoted, protected = promote_inferred_display_assignments(
                parsed, display_variables, unsafe_display_variables)
            stats["inferred_display_assignments"] += promoted
            stats["protected_display_assignments"] += protected
            if parsed.serialize() != raw:
                stats["roundtrip_mismatches"] += 1
                if len(examples["roundtrip"]) < 10:
                    examples["roundtrip"].append([filename, line_no, raw, parsed.serialize()])
            uncovered = parsed.unclassified_spans()
            stats["unclassified_spans"] += len(uncovered)
            if uncovered and len(examples["roundtrip"]) < 10:
                examples["roundtrip"].append([filename, line_no, raw, "unclassified", uncovered])
            if parsed.kind == "command":
                stats["commands"] += sum(1 for f in parsed.fields if f.role == "COMMAND")
            elif parsed.kind in {"command_chain", "mixed"}:
                stats["commands"] += sum(1 for f in parsed.fields if f.role == "COMMAND")
            elif parsed.kind == "dialogue":
                stats["dialogue_lines"] += 1
            elif parsed.kind == "unknown":
                stats["unknown_lines"] += 1
            elif parsed.kind == "comment":
                stats["comments"] += 1
            for f in parsed.fields:
                stats["role_counts"][f.role] = stats["role_counts"].get(f.role, 0) + 1
                if f.role == "UNKNOWN_COMMAND":
                    counts = stats["unknown_command_counts"]
                    counts[f.value] = counts.get(f.value, 0) + 1
                    if len(examples["unknown_commands"]) < 50:
                        examples["unknown_commands"].append([filename, line_no, f.value, raw[:300]])
                if f.role == "DISPLAY":
                    stats["display_fields"] += 1
                    if len(examples["display"]) < 10:
                        examples["display"].append([filename, line_no, f.raw, f.value])
                elif f.role == "UNKNOWN_QUOTED":
                    stats["raw_unknown_quoted_fields"] += 1
                    file_unknown_quoted.append([filename, line_no, raw[:300], f.value])
                elif f.role == "OPAQUE_NESTED_CODE":
                    stats["opaque_nested_fields"] += 1
        windows = parse_document(rows, parsed_rows)
        continuation_lines = {
            fragment["line"] - 1
            for window in windows
            for fragment in window["fragments"]
            if fragment["field"].role in {"DISPLAY_CONTINUATION", "DISPLAY_INFERRED"}
        }
        unresolved_quotes = [item for item in file_unknown_quoted
                             if item[1] - 1 not in continuation_lines]
        stats["unknown_quoted_fields"] += len(unresolved_quotes)
        examples["unknown_quoted"].extend(unresolved_quotes[:max(
            0, 100 - len(examples["unknown_quoted"]))])
        examples["raw_unknown_quoted"].extend(file_unknown_quoted[:max(
            0, 200 - len(examples["raw_unknown_quoted"]))])
        unknown_indexes = {
            line_no - 1 for line_no, parsed_row in enumerate(parsed_rows, 1)
            if parsed_row.kind == "unknown"
        }
        continuation_unknown = unknown_indexes & continuation_lines
        stats["unknown_continuation_lines"] += len(continuation_unknown)
        unresolved_unknown = unknown_indexes - continuation_lines
        stats["unresolved_unknown_lines"] += len(unresolved_unknown)
        if unresolved_unknown:
            by_file = stats["unresolved_unknown_by_file"]
            by_file[filename] = len(unresolved_unknown)
        for row_index in sorted(unresolved_unknown):
            category = triage_unresolved_line(rows[row_index], document_role)
            cats = stats["unresolved_unknown_categories"]
            cats[category] = cats.get(category, 0) + 1
            if category == "UNKNOWN_SCRIPT":
                stats["actionable_unknown_lines"] += 1
        for row_index in sorted(unresolved_unknown):
            if len(examples["unresolved_unknown"]) >= 1000:
                break
            examples["unresolved_unknown"].append([
                filename, row_index + 1, rows[row_index][:300],
                [[field.role, field.value] for field in parsed_rows[row_index].fields]
            ])
        stats["dialogue_windows"] += len(windows)
        stats["complete_windows"] += sum(1 for w in windows if w["complete"])
        stats["incomplete_windows"] += sum(1 for w in windows if not w["complete"])
        incomplete_for_file = sum(1 for w in windows if not w["complete"])
        if incomplete_for_file:
            stats["incomplete_windows_by_file"][filename] = incomplete_for_file
        for window in windows:
            covered_lines = {fragment["line"] - 1 for fragment in window["fragments"]}
            if (not window["complete"]
                    and not any(fragment["field"].role in {
                        "DISPLAY", "DISPLAY_CONTINUATION", "DISPLAY_INFERRED"
                    } for fragment in window["fragments"])):
                stats["incomplete_windows_without_display"] += 1
            for row_index in range(window["start"], window["end"] + 1):
                body = rows[row_index][:_line_body_end(rows[row_index])]
                if (not body.strip() or _is_bare_wait_marker(body)
                        or body.strip() in NON_DISPLAY_MARKERS):
                    continue
                if row_index not in covered_lines:
                    stats["window_uncovered_rows"] += 1
                    if len(examples["window_uncovered"]) < 100:
                        examples["window_uncovered"].append(
                            [filename, row_index + 1, rows[row_index][:300]])
            stats["dialogue_continuation_fields"] += sum(
                fragment["field"].role == "DISPLAY_CONTINUATION" for fragment in window["fragments"])
            stats["inferred_display_fields"] += sum(
                fragment["field"].role == "DISPLAY_INFERRED" for fragment in window["fragments"])
            if not window["complete"] and len(examples["incomplete_windows"]) < 200:
                examples["incomplete_windows"].append(
                    [filename, window["start"] + 1, window["end"] + 1,
                     len(window["raw_lines"]), [row[:240] for row in window["raw_lines"][:2]]])
        stats["speaker_fields"] += sum(
            field.role == "SPEAKER_NAME" and field.translatable
            for parsed in parsed_rows for field in parsed.fields)
    stats["unknown_command_counts"] = dict(sorted(
        stats["unknown_command_counts"].items(), key=lambda item: (-item[1], item[0]))[:100])
    stats["unresolved_unknown_by_file"] = dict(sorted(
        stats["unresolved_unknown_by_file"].items(),
        key=lambda item: (-item[1], item[0])))
    stats["incomplete_windows_by_file"] = dict(sorted(
        stats["incomplete_windows_by_file"].items(),
        key=lambda item: (-item[1], item[0])))
    return {"stats": stats, "examples": examples}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("line", nargs="?", help="parse one source line")
    ap.add_argument("--scan-dir", help="read-only scan of a directory of plain .txt scripts")
    args = ap.parse_args(argv)
    if args.scan_dir:
        print(json.dumps(scan_directory(args.scan_dir), ensure_ascii=False, indent=2))
        return 0
    if args.line is not None:
        print(json.dumps(parse_line(args.line).to_dict(), ensure_ascii=False, indent=2))
        return 0
    ap.error("provide a line or --scan-dir")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
