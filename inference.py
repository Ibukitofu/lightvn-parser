# -*- coding: utf-8 -*-
"""inference.py -- Corpus inference: decide which values are display text and which are logic keys."""

from __future__ import annotations

import os
import re
from typing import Iterable, Optional

try:
    from .field_types import FILE_RE, Field, ParsedLine
except ImportError:
    from field_types import FILE_RE, Field, ParsedLine
try:
    from .grammar import _display_children
except ImportError:
    from grammar import _display_children
try:
    from .schema import ASSIGN_COMMANDS, CALL_COMMANDS, SCRIPT_DISPLAY_CALL_ARGS, TEXT_ASSIGN_COMMANDS, _COMPARISON_LITERALS
except ImportError:
    from schema import ASSIGN_COMMANDS, CALL_COMMANDS, SCRIPT_DISPLAY_CALL_ARGS, TEXT_ASSIGN_COMMANDS, _COMPARISON_LITERALS
try:
    from .line_parser import parse_line
except ImportError:
    from line_parser import parse_line
try:
    from .documents import classify_source_content, parse_document
except ImportError:
    from documents import classify_source_content, parse_document


def _variable_refs(fields: Iterable[Field]) -> set[str]:
    refs = set()
    for item in fields:
        if item.role == "VARIABLE_REF" and item.value.startswith("{{") and item.value.endswith("}}"):
            refs.add(item.value[2:-2])
        refs.update(_variable_refs(item.children))
    return refs


def infer_display_parameter_indices(path: str) -> dict[str, list[int]]:
    """Infer positional script parameters that flow into known display fields.

    A label is used only when it has exactly one definition in the audited
    corpus. This avoids guessing across duplicate labels in unrelated scripts.
    Parameters referenced outside display fields remain protected, including
    aliases, conditions, resource paths and opaque callback code.
    """
    definitions = []
    for filename in sorted(os.listdir(path)):
        if not filename.lower().endswith(".txt"):
            continue
        full = os.path.join(path, filename)
        with open(full, "r", encoding="utf-8", errors="surrogateescape", newline="") as stream:
            content = stream.read()
        if classify_source_content(content) != "script_candidate":
            continue
        rows = content.split("\n")
        parsed_rows = [parse_line(row) for row in rows]
        refs_by_line = [
            _variable_refs([f for f in parsed.fields if f.role in {"DISPLAY", "SPEAKER_NAME"}])
            for parsed in parsed_rows
        ]
        for window in parse_document(rows, parsed_rows):
            for fragment in window["fragments"]:
                refs_by_line[fragment["line"] - 1].update(_variable_refs([fragment["field"]]))

        active = None
        for line_index, parsed in enumerate(parsed_rows):
            command_fields = [f for f in parsed.fields if f.role == "COMMAND"]
            if len(command_fields) == 1 and command_fields[0].value == "栞":
                if active is not None:
                    definitions.append(active)
                args = [f for f in parsed.fields if f.role not in {
                    "COMMAND", "PREFIX", "CONDITIONAL_COMMAND", "CONDITION", "LINE_ENDING"
                }]
                label = args[0].value if args else ""
                params = [f.value for f in args[1:]]
                active = {"label": label, "params": params, "display_refs": set(),
                          "code_refs": set()}
            elif active is not None:
                active["display_refs"].update(refs_by_line[line_index])
                for item in parsed.fields:
                    if item.role in {"DISPLAY", "SPEAKER_NAME", "COMMENT", "LINE_ENDING"}:
                        continue
                    for name in active["params"]:
                        if name and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", item.value):
                            active["code_refs"].add(name)
        if active is not None:
            definitions.append(active)

    grouped = {}
    for definition in definitions:
        grouped.setdefault(definition["label"], []).append(definition)
    return {
        label: [index for index, name in enumerate(defs[0]["params"])
                if name in defs[0]["display_refs"] and name not in defs[0]["code_refs"]]
        for label, defs in grouped.items()
        if label and len(defs) == 1
    }


def promote_inferred_display_arguments(parsed: ParsedLine, display_params: dict[str, list[int]]) -> int:
    """Promote quoted call arguments backed by a reviewed or unique callee schema."""
    commands = [f for f in parsed.fields if f.role == "COMMAND"]
    if len(commands) != 1 or commands[0].value not in CALL_COMMANDS:
        return 0
    args = [f for f in parsed.fields if f.role not in {
        "COMMAND", "PREFIX", "CONDITIONAL_COMMAND", "CONDITION", "PIPE_SEPARATOR", "LINE_ENDING"
    }]
    if len(args) < 3:
        return 0
    target = args[0].value.replace("\\", "/").casefold()
    label = args[1].value
    parameter_positions = SCRIPT_DISPLAY_CALL_ARGS.get((target, label))
    if parameter_positions is None:
        parameter_positions = display_params.get(label)
    if parameter_positions is None:
        return 0
    promoted = 0
    for position in parameter_positions:
        arg_index = position + 2
        if arg_index >= len(args) or args[arg_index].role != "UNKNOWN_QUOTED":
            continue
        arg = args[arg_index]
        arg.role = "DISPLAY"
        arg.translatable = True
        arg.children = _display_children(arg.raw, arg.start, True)
        promoted += 1
    return promoted


LOGIC_STRING_VALUES = {"on", "off", "true", "false", "なし", "無", "-", "null", "none"}


def infer_display_only_variables(path: str) -> set[str]:
    """Find variables interpolated into display text but never used as logic/path keys.

    This intentionally remains the conservative, backwards-compatible set API.
    Call :func:`infer_display_variable_roles` when the caller also needs to
    preserve display values that are visible but unsafe to translate directly.
    """
    return infer_display_variable_roles(path)["safe"]


def _assignment_aliases(parsed: ParsedLine) -> dict[str, set[str]]:
    """Return simple variable-to-variable assignment edges from one parsed row."""
    aliases = {}
    for group in _pipe_groups(parsed.fields):
        commands = [f for f in group if f.role == "COMMAND"]
        if len(commands) != 1 or commands[0].value not in ASSIGN_COMMANDS:
            continue
        args = [f for f in group if f.role not in {
            "COMMAND", "PREFIX", "CONDITIONAL_COMMAND", "CONDITION",
            "PIPE_SEPARATOR", "LINE_ENDING"
        }]
        if not args or not args[0].value:
            continue
        refs = set()
        for arg in args[1:]:
            refs.update(re.findall(r"\{\{(.*?)\}\}", arg.value))
        if refs:
            aliases.setdefault(args[0].value, set()).update(refs)
    return aliases


def _pipe_groups(fields: list[Field]) -> list[list[Field]]:
    """Split parsed fields into command groups without losing condition prefixes."""
    groups = [[]]
    for item in fields:
        if item.role == "PIPE_SEPARATOR":
            groups.append([])
        else:
            groups[-1].append(item)
    return [group for group in groups if group]


def _numeric_dynamic_assignment_links(
        assigned_names: set[str], observed_names: set[str],
) -> dict[str, set[str]]:
    """Find possible indexed writes backed by concrete names in this corpus.

    ``enemy{{index}}skill1`` may write ``enemy1skill1``.  Only numeric
    substitutions with identical literal prefix/suffix are linked here;
    arbitrary text or nested interpolation still needs separate analysis.
    A link is evidence for review, never permission to translate in place.
    """
    links = {}
    placeholder = re.compile(r"\{\{[^{}]+\}\}")
    concrete = {name for name in observed_names if "{" not in name and "}" not in name}
    for name in assigned_names:
        parts = placeholder.split(name)
        if len(parts) < 2 or not any(parts) or any("{" in p or "}" in p for p in parts):
            continue
        pattern = re.compile(r"[0-9]+".join(re.escape(p) for p in parts))
        matches = {candidate for candidate in concrete if pattern.fullmatch(candidate)}
        if matches:
            links[name] = matches
    return links


def collect_comparison_literals(path: str) -> set[str]:
    """Return every quoted literal used as a comparison operand anywhere in the corpus.

    A value that appears as ``== "X"`` / ``!= "X"`` is a logic key: translating the
    displayed copy of ``X`` elsewhere desynchronises the two and silently breaks the
    branch.  Callers must treat these values as non-translatable wherever they appear.
    """
    literals: set[str] = set()
    newline = chr(10)
    compare = re.compile('[=!]=' + r'\s*' + '"([^"' + newline + ']{1,80})"')
    for filename in sorted(os.listdir(path)):
        if not filename.lower().endswith('.txt'):
            continue
        try:
            with open(os.path.join(path, filename), encoding='utf-8',
                      errors='surrogateescape', newline='') as stream:
                content = stream.read()
        except OSError:
            continue
        literals.update(compare.findall(content))
    return literals


def infer_display_variable_roles(path: str) -> dict[str, set[str]]:
    global _COMPARISON_LITERALS
    _COMPARISON_LITERALS = collect_comparison_literals(path)
    """Infer safe and visible-but-unsafe variable roles.

    A variable can be visible and still be unsafe to translate in place when
    the same value is used as a condition key, resource/path component, or
    jump label.  Those variables are returned as ``unsafe`` so their literal
    assignments can be audited without exposing them to translation.

    The analysis also follows simple assignment aliases backwards.  This is
    enough for the project's ``ev_* -> 目的内容 -> 文字窓`` pattern while
    avoiding speculative data-flow through arbitrary expressions.
    """
    display_vars = set()
    compared_vars = set()
    path_vars = set()
    assigned_names = set()
    aliases: dict[str, set[str]] = {}
    compare_re = re.compile(
        r"([^\s()=!<>]+)\s*(?:==|!=|<=|>=|<|>)\s*([^\s()=!<>]+)"
    )
    var_re = re.compile(r"\{\{(.*?)\}\}")

    def comparison_ref(token: str) -> Optional[str]:
        token = token.strip("()")
        if token.startswith('"') and token.endswith('"'):
            token = token[1:-1]
        if token.startswith("{{") and token.endswith("}}"):
            return token[2:-2]
        # Bare identifiers on the left/right side are variable-like; quoted
        # constants and numeric literals are intentionally ignored.
        if re.fullmatch(r"[A-Za-z_\u3040-\u30ff\u3400-\u9fff][^\s()=!<>]*", token):
            return token
        return None
    for filename in sorted(os.listdir(path)):
        if not filename.lower().endswith(".txt"):
            continue
        full = os.path.join(path, filename)
        with open(full, "r", encoding="utf-8", errors="surrogateescape", newline="") as stream:
            content = stream.read()
        if classify_source_content(content) != "script_candidate":
            continue
        rows = content.split("\n")
        parsed_rows = [parse_line(row) for row in rows]
        for parsed in parsed_rows:
            for lhs, refs in _assignment_aliases(parsed).items():
                aliases.setdefault(lhs, set()).update(refs)
            for field in parsed.fields:
                if field.role == "VARIABLE_NAME":
                    assigned_names.add(field.value)
                if field.role == "CONDITION":
                    for match in compare_re.finditer(field.value):
                        for operand in match.groups():
                            key = comparison_ref(operand)
                            if key:
                                compared_vars.add(key)
                if field.role in {"VARIABLE_NAME", "LABEL", "FILENAME_OR_LABEL"}:
                    # Dynamic variable names and jump labels are code keys,
                    # even when their syntax is otherwise opaque.
                    path_vars.update(var_re.findall(field.value))
                if field.role in {"RESOURCE_PATH", "FILENAME"} or (
                        field.role == "RESOURCE_OR_OPTION" and ("/" in field.value or FILE_RE.search(field.value))):
                    path_vars.update(var_re.findall(field.value))
                if field.role in {"DISPLAY", "SPEAKER_NAME"}:
                    display_vars.update(_variable_refs([field]))
        for window in parse_document(rows, parsed_rows):
            for fragment in window["fragments"]:
                display_vars.update(_variable_refs([fragment["field"]]))

    observed_names = assigned_names | display_vars | compared_vars | path_vars
    for refs in aliases.values():
        observed_names.update(refs)
    dynamic_links = _numeric_dynamic_assignment_links(assigned_names, observed_names)
    for dynamic_name, concrete_names in dynamic_links.items():
        # Protect the whole family when a runtime index cannot be resolved.
        path_vars.add(dynamic_name)
        aliases.setdefault(dynamic_name, set()).update(concrete_names)
        for concrete_name in concrete_names:
            aliases.setdefault(concrete_name, set()).add(dynamic_name)

    # Propagate display and path risks through aliases.
    changed = True
    while changed:
        changed = False
        for lhs, refs in aliases.items():
            for uses in (display_vars, compared_vars, path_vars):
                if lhs in uses:
                    before = len(uses)
                    uses.update(refs)
                    changed = changed or len(uses) != before

    unsafe = display_vars & (compared_vars | path_vars)
    return {
        "safe": display_vars - unsafe,
        "unsafe": unsafe,
        "display": display_vars,
        "compared": compared_vars,
        "path": path_vars,
    }


def promote_inferred_display_assignments(
        parsed: ParsedLine,
        display_vars: set[str],
        unsafe_display_vars: Optional[set[str]] = None,
) -> tuple[int, int] | int:
    """Classify string assignments for inferred display variables.

    ``unsafe_display_vars`` are visible values that also participate in logic,
    paths, or labels.  They are exposed as ``DISPLAY_UNSAFE`` for auditability
    but remain non-translatable.  The integer return value is preserved when
    the optional argument is omitted for compatibility with existing callers.
    """
    include_protected_count = unsafe_display_vars is not None
    promoted = 0
    protected = 0
    unsafe_display_vars = unsafe_display_vars or set()
    candidate_vars = set(display_vars) | unsafe_display_vars
    for group in _pipe_groups(parsed.fields):
        commands = [f for f in group if f.role == "COMMAND"]
        if len(commands) != 1 or commands[0].value not in TEXT_ASSIGN_COMMANDS:
            continue
        args = [f for f in group if f.role not in {
            "COMMAND", "PREFIX", "CONDITIONAL_COMMAND", "CONDITION",
            "PIPE_SEPARATOR", "LINE_ENDING"
        }]
        if not args or args[0].value not in candidate_vars:
            continue
        variable_name = args[0].value
        for arg in args[1:]:
            if arg.role != "UNKNOWN_VALUE" or not (arg.raw.startswith('"') and arg.raw.endswith('"')):
                continue
            value = arg.value.strip()
            if value.casefold() in LOGIC_STRING_VALUES or FILE_RE.search(value):
                continue
            if variable_name in unsafe_display_vars or value in _COMPARISON_LITERALS:
                arg.role = "DISPLAY_UNSAFE"
                arg.translatable = False
                arg.children = _display_children(arg.raw, arg.start, True)
                protected += 1
                continue
            arg.role = "DISPLAY"
            arg.translatable = True
            arg.children = _display_children(arg.raw, arg.start, True)
            promoted += 1
    return (promoted, protected) if include_protected_count else promoted
