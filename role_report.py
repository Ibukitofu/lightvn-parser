# -*- coding: utf-8 -*-
"""Read-only structural and variable-role report for Light.vn scripts.

This module deliberately does not edit source, build output, or translation
records.  It turns the parser's field stream into two auditable products:

* a per-file/per-role structural summary, and
* a per-variable evidence report which distinguishes visible values from
  logic keys, resource fragments, labels, and mixed unsafe variables.

The report is evidence-first: every inferred role carries file:line evidence,
and a variable is never made translatable merely because it appears in a
display field.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from typing import Iterable

try:
    from . import field_parser as FP
except ImportError:
    import field_parser as FP


VAR_RE = re.compile(r"\{\{([^{}]+)\}\}")
COMPARE_RE = re.compile(
    r"([^\s()=!<>]+)\s*(?:==|!=|<=|>=|<|>)\s*([^\s()=!<>]+)"
)
IDENT_RE = re.compile(r"^[A-Za-z_\u3040-\u30ff\u3400-\u9fff][^\s()=!<>]*$")

PROTECTED_FIELD_ROLES = {
    "CONDITION", "VARIABLE_NAME", "LABEL", "FILENAME_OR_LABEL",
    "RESOURCE_PATH", "FILENAME", "RESOURCE_OR_OPTION", "COMMAND",
    "OPAQUE_NESTED_CODE", "DISPLAY_UNSAFE",
}


def _loc(filename: str, line: int) -> str:
    return f"{filename}:{line}"


def _add(refs: dict[str, list[str]], name: str, location: str, limit: int = 100) -> None:
    name = name.strip()
    if not name or name.startswith('"') or name.startswith("'"):
        return
    bucket = refs.setdefault(name, [])
    if location not in bucket and len(bucket) < limit:
        bucket.append(location)


def _var_refs(text: str) -> list[str]:
    return [m.group(1).strip() for m in VAR_RE.finditer(text)]


def _comparison_names(text: str) -> list[str]:
    result = []
    for match in COMPARE_RE.finditer(text):
        for operand in match.groups():
            operand = operand.strip("()")
            if operand.startswith("{{") and operand.endswith("}}"):
                result.append(operand[2:-2].strip())
            elif IDENT_RE.fullmatch(operand):
                result.append(operand)
    return result


def _iter_fields(parsed: FP.ParsedLine):
    for field in parsed.fields:
        yield field
        stack = list(field.children)
        while stack:
            child = stack.pop()
            yield child
            stack.extend(child.children)


def _evidence_bucket() -> dict[str, dict[str, list[str]]]:
    return {
        "assigned": {},
        "assigned_values": {},
        "display_refs": {},
        "comparison_refs": {},
        "resource_refs": {},
        "label_refs": {},
        "dynamic_name_refs": {},
        "alias_refs": {},
    }


def _ensure(evidence: dict[str, dict[str, list[str]]], name: str) -> None:
    # Keep the data shape explicit even when a variable is only seen once.
    for bucket in evidence.values():
        bucket.setdefault(name, [])


def _record_assignment(parsed: FP.ParsedLine, filename: str, line: int,
                       evidence: dict[str, dict[str, list[str]]]) -> None:
    for group in FP._pipe_groups(parsed.fields):
        commands = [f for f in group if f.role == "COMMAND"]
        if len(commands) != 1 or commands[0].value not in FP.ASSIGN_COMMANDS:
            continue
        args = [f for f in group if f.role not in {
            "COMMAND", "PREFIX", "CONDITIONAL_COMMAND", "CONDITION",
            "PIPE_SEPARATOR", "LINE_ENDING",
        }]
        if not args or args[0].role != "VARIABLE_NAME":
            continue
        name = args[0].value
        location = _loc(filename, line)
        _ensure(evidence, name)
        _add(evidence["assigned"], name, location)
        # The lhs is a variable key.  Dynamic interpolation in it is a
        # variable-name construction, never a display value.
        for ref in _var_refs(name):
            _ensure(evidence, ref)
            _add(evidence["dynamic_name_refs"], ref, location)
        for arg in args[1:]:
            if arg.role != "ASSIGN_OPERATOR":
                _add(evidence["assigned_values"], name,
                     f"{location} = {arg.raw}")
            for ref in _var_refs(arg.value):
                _ensure(evidence, ref)
                _add(evidence["alias_refs"], ref, location)


def _record_field(field: FP.Field, filename: str, line: int,
                  evidence: dict[str, dict[str, list[str]]]) -> None:
    location = _loc(filename, line)
    role = field.role
    refs = _var_refs(field.value)
    if role in {"DISPLAY", "DISPLAY_CONTINUATION", "DISPLAY_INFERRED",
                "SPEAKER_NAME"}:
        for ref in refs:
            _ensure(evidence, ref)
            _add(evidence["display_refs"], ref, location)
    if role == "CONDITION":
        for ref in _var_refs(field.value) + _comparison_names(field.value):
            _ensure(evidence, ref)
            _add(evidence["comparison_refs"], ref, location)
    if role in {"RESOURCE_PATH", "FILENAME", "RESOURCE_OR_OPTION"}:
        for ref in refs:
            _ensure(evidence, ref)
            _add(evidence["resource_refs"], ref, location)
    if role in {"LABEL", "FILENAME_OR_LABEL"}:
        for ref in refs:
            _ensure(evidence, ref)
            _add(evidence["label_refs"], ref, location)
    if role == "VARIABLE_NAME":
        for ref in refs:
            _ensure(evidence, ref)
            _add(evidence["dynamic_name_refs"], ref, location)


def _classification(name: str, evidence: dict[str, dict[str, list[str]]],
                    unsafe_vars=None, safe_vars=None) -> tuple[str, str]:
    visible = bool(evidence["display_refs"])
    compared = bool(evidence["comparison_refs"])
    resource = bool(evidence["resource_refs"])
    label = bool(evidence["label_refs"])
    dynamic = bool(evidence["dynamic_name_refs"])
    assigned = bool(evidence["assigned"])
    protected = compared or resource or label or dynamic
    # The corpus-wide inference follows assignment aliases and {{name}} use, so it
    # can prove a hazard that this variable's own local evidence does not show.
    # Defer to it: a value proven unsafe anywhere is unsafe everywhere.
    if unsafe_vars and name in unsafe_vars:
        return ("MIXED_UNSAFE",
                "语料级推断证明该值同时参与显示与逻辑/资源用途，禁止原地翻译")
    if visible and protected:
        return "MIXED_UNSAFE", "显示与逻辑/资源/键用途重叠，禁止原地翻译"
    if visible:
        return "DISPLAY_ONLY", "仅在显示字段中出现，可进入显示翻译审核"
    if resource:
        return "RESOURCE_FRAGMENT", "参与资源路径或资源片段，必须保持原值"
    if label or dynamic:
        return "LABEL_OR_VARIABLE_KEY", "参与标签或动态变量名，必须保持原值"
    if compared:
        return "LOGIC_KEY", "参与条件比较，必须保持原值"
    if assigned:
        return "UNKNOWN_ROLE", "目前只有赋值证据，需结合运行时或调用点复核"
    return "UNKNOWN_ROLE", "只有弱引用或无法确定用途，保守保护"


def _file_report(path: str, filename: str, display_parameters: dict[str, list[int]],
                 display_vars: set[str], unsafe_vars: set[str]) -> dict:
    full = os.path.join(path, filename)
    with open(full, "r", encoding="utf-8", errors="surrogateescape", newline="") as stream:
        content = stream.read()
    file_type = FP.classify_source_content(content)
    if file_type != "script_candidate":
        return {
            "file": filename,
            "file_type": file_type,
            "document_role": "non_script",
            "lines": 0,
            "role_counts": {},
            "fields": 0,
            "translatable_fields": 0,
            "unresolved": {},
        }
    rows = content.split("\n")
    document_role = FP.classify_document_role(rows)
    parsed_rows = []
    role_counts = Counter()
    kind_counts = Counter()
    unresolved = Counter()
    fields_total = 0
    translatable = 0
    inferred_display_arguments = 0
    inferred_display_assignments = 0
    protected_display_assignments = 0
    evidence = _evidence_bucket()
    for line_no, raw in enumerate(rows, 1):
        parsed = FP.parse_line(raw)
        inferred_display_arguments += FP.promote_inferred_display_arguments(
            parsed, display_parameters)
        promoted, protected = FP.promote_inferred_display_assignments(
            parsed, display_vars, unsafe_vars)
        inferred_display_assignments += promoted
        protected_display_assignments += protected
        parsed_rows.append(parsed)
        kind_counts[parsed.kind] += 1
        _record_assignment(parsed, filename, line_no, evidence)
        for field in _iter_fields(parsed):
            role_counts[field.role] += 1
            fields_total += 1
            translatable += bool(field.translatable)
            _record_field(field, filename, line_no, evidence)
        if parsed.kind == "unknown":
            category = FP.triage_unresolved_line(raw, document_role)
            unresolved[category] += 1
    # Dialogue continuation fragments are fields on the document window and
    # must be included in variable evidence even if their physical row was
    # initially a bare continuation.
    windows = FP.parse_document(rows, parsed_rows)
    continuation_lines = {
        fragment["line"] - 1
        for window in windows
        for fragment in window["fragments"]
        if fragment["field"].role in {"DISPLAY_CONTINUATION", "DISPLAY_INFERRED"}
    }
    # Bare physical rows inside a recognized dialogue window are not parser
    # gaps.  Exclude them before producing the unresolved inventory.
    unresolved = Counter()
    for index, (raw, parsed) in enumerate(zip(rows, parsed_rows)):
        if parsed.kind == "unknown" and index not in continuation_lines:
            unresolved[FP.triage_unresolved_line(raw, document_role)] += 1
    for window in windows:
        for fragment in window["fragments"]:
            field = fragment["field"]
            line_no = fragment["line"]
            _record_field(field, filename, line_no, evidence)
    return {
        "file": filename,
        "file_type": file_type,
        "document_role": document_role,
        "lines": len(rows),
        "kind_counts": dict(sorted(kind_counts.items())),
        "role_counts": dict(sorted(role_counts.items())),
        "fields": fields_total,
        "translatable_fields": translatable,
        "inferred_display_arguments": inferred_display_arguments,
        "inferred_display_assignments": inferred_display_assignments,
        "protected_display_assignments": protected_display_assignments,
        "unresolved": dict(sorted(unresolved.items())),
        "evidence": evidence,
    }


def build_report(path: str) -> dict:
    """Build a complete read-only report for a directory of extracted scripts."""
    display_parameters = FP.infer_display_parameter_indices(path)
    variable_roles = FP.infer_display_variable_roles(path)
    safe_vars = variable_roles["safe"]
    unsafe_vars = variable_roles["unsafe"]
    files = []
    global_evidence = _evidence_bucket()
    totals = Counter()
    for filename in sorted(os.listdir(path)):
        if not filename.lower().endswith(".txt"):
            continue
        report = _file_report(path, filename, display_parameters, safe_vars, unsafe_vars)
        file_evidence = report.pop("evidence", {})
        files.append(report)
        for key in ("lines", "fields", "translatable_fields",
                    "inferred_display_arguments", "inferred_display_assignments",
                    "protected_display_assignments"):
            totals[key] += report.get(key, 0)
        for key, value in report.get("role_counts", {}).items():
            totals[f"role:{key}"] += value
        for key, value in report.get("kind_counts", {}).items():
            totals[f"kind:{key}"] += value
        for key, value in report.get("unresolved", {}).items():
            totals[f"unresolved:{key}"] += value
        for bucket, mapping in file_evidence.items():
            for name, locations in mapping.items():
                for location in locations:
                    _add(global_evidence[bucket], name, location)
    names = set()
    for mapping in global_evidence.values():
        names.update(mapping)
    variables = []
    for name in sorted(names):
        evidence = {bucket: mapping.get(name, []) for bucket, mapping in global_evidence.items()}
        classification, policy = _classification(name, evidence, unsafe_vars, safe_vars)
        variables.append({
            "name": name,
            "classification": classification,
            "translation_policy": policy,
            "roles": [
                role for role, present in (
                    ("DISPLAY", bool(evidence["display_refs"])),
                    ("LOGIC_KEY", bool(evidence["comparison_refs"])),
                    ("RESOURCE_FRAGMENT", bool(evidence["resource_refs"])),
                    ("LABEL_OR_VARIABLE_KEY", bool(evidence["label_refs"] or evidence["dynamic_name_refs"])),
                    ("ASSIGNED", bool(evidence["assigned"])),
                ) if present
            ],
            "evidence": evidence,
        })
    classification_counts = Counter(item["classification"] for item in variables)
    return {
        "schema_version": 1,
        "path": os.path.abspath(path),
        "analysis_scope": "all script-candidate files in this directory",
        "policy": "结构化不等于可翻译；只有 DISPLAY_ONLY 允许进入翻译审核",
        "totals": dict(sorted(totals.items())),
        "classification_counts": dict(sorted(classification_counts.items())),
        "files": files,
        "variables": variables,
        "inferred_variable_sets": {
            "display_safe": sorted(safe_vars),
            "display_unsafe": sorted(unsafe_vars),
            "display_all": sorted(variable_roles["display"]),
            "compared": sorted(variable_roles["compared"]),
            "path": sorted(variable_roles["path"]),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="directory containing extracted .txt scripts")
    parser.add_argument("-o", "--output", help="JSON output path; stdout when omitted")
    args = parser.parse_args()
    report = build_report(args.path)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.write("\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
