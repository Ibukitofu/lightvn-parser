# -*- coding: utf-8 -*-
"""line_parser.py -- Single-line parser: text -> Field list. Public entry point parse_line()."""

from __future__ import annotations

import re
from typing import Iterable, Optional
try:
    from . import lvparse as P
except ImportError:
    import lvparse as P

try:
    from .field_types import CONDITIONALS, FILE_RE, Field, NON_DISPLAY_MARKERS, NUMBER_RE, ParsedLine, URL_RE, WAIT_END_RE, WS
except ImportError:
    from field_types import CONDITIONALS, FILE_RE, Field, NON_DISPLAY_MARKERS, NUMBER_RE, ParsedLine, URL_RE, WAIT_END_RE, WS
try:
    from .grammar import _display_children, _is_bare_wait_marker, _line_body_end, _segments, _tokens
except ImportError:
    from grammar import _display_children, _is_bare_wait_marker, _line_body_end, _segments, _tokens
try:
    from .schema import ASSIGN_COMMANDS, CALL_COMMANDS, DISPLAY_COMMANDS, EXTRA_COMMANDS, JUMP_COMMANDS, KNOWN_SCHEMA_COMMANDS, PROTECTED_QUOTED_COMMANDS, RESOURCE_COMMANDS, SCRIPT_CODE_CALL_ARGS, _project_macro_names, _starts_with_command, classify_bare_token, positional_role
except ImportError:
    from schema import ASSIGN_COMMANDS, CALL_COMMANDS, DISPLAY_COMMANDS, EXTRA_COMMANDS, JUMP_COMMANDS, KNOWN_SCHEMA_COMMANDS, PROTECTED_QUOTED_COMMANDS, RESOURCE_COMMANDS, SCRIPT_CODE_CALL_ARGS, _project_macro_names, _starts_with_command, classify_bare_token, positional_role


def _skip_condition(s: str, start: int, base: int) -> tuple[int, Optional[Field], bool]:
    i = start
    while i < len(s) and s[i] in WS:
        i += 1
    for keyword in CONDITIONALS:
        if not s.startswith(keyword, i):
            continue
        k = i + len(keyword)
        while k < len(s) and s[k] in WS:
            k += 1
        if k >= len(s) or s[k] != "(":
            continue
        group_start = k
        group_end = k
        while True:
            depth = 0
            j = group_start
            in_quote = False
            while j < len(s):
                c = s[j]
                if c == "\\":
                    j += 2
                    continue
                if c == '"':
                    in_quote = not in_quote
                elif not in_quote:
                    if c == "(":
                        depth += 1
                    elif c == ")":
                        depth -= 1
                        if depth == 0:
                            group_end = j + 1
                            break
                j += 1
            if depth != 0:
                return start, None, False

            probe = group_end
            while probe < len(s) and s[probe] in WS:
                probe += 1
            if s.startswith(("&&", "||"), probe):
                next_group = probe + 2
                while next_group < len(s) and s[next_group] in WS:
                    next_group += 1
                if next_group < len(s) and s[next_group] == "(":
                    group_start = next_group
                    continue

            # Some shipped scripts have an extra ")" after a condition.
            # Recover only when the following token is a known command.
            # Keep the punctuation in CONDITION so spans remain lossless.
            recovered_end = group_end
            while recovered_end < len(s) and s[recovered_end] in WS:
                recovered_end += 1
            paren_start = recovered_end
            while recovered_end < len(s) and s[recovered_end] == ")":
                recovered_end += 1
                while recovered_end < len(s) and s[recovered_end] in WS:
                    recovered_end += 1
            recovered = recovered_end > paren_start
            if recovered:
                command_end = recovered_end
                while command_end < len(s) and s[command_end] not in WS + '"|':
                    command_end += 1
                candidate = s[recovered_end:command_end]
                known_suffix = (candidate in KNOWN_SCHEMA_COMMANDS
                                or candidate in EXTRA_COMMANDS
                                or candidate in _project_macro_names()
                                or P.is_known_command(candidate))
                if not known_suffix:
                    recovered = False
                    recovered_end = group_end

            raw = s[k:group_end]
            if recovered:
                raw = s[k:recovered_end]
                return (recovered_end,
                        Field("CONDITION", base + k, base + recovered_end, raw, raw),
                        False)
            return group_end, Field("CONDITION", base + k, base + group_end, raw, raw), True
    return start, None, True


def _nested_callback_span(line: str, start: int, end: int) -> Optional[tuple[int, int, bool]]:
    """Span of a trailing unescaped-quote callback argument, if this row has one.

    The callback is only recognized when the row ends with a quote and the text
    inside the first quote begins like a command; that is the same evidence the
    engine's own editor uses to decide the parameter is a Light.vn コマンド
    rather than display text.
    """
    # Physical rows keep their CRLF; the callback ends before the line break.
    body_end = min(end, _line_body_end(line)) if end >= _line_body_end(line) else end
    while body_end > start and line[body_end - 1] in WS:
        body_end -= 1
    if body_end - start < 2 or line[body_end - 1] != '"':
        return None
    probe = start
    while probe < body_end:
        current = line[probe]
        if current == "\\":
            probe += 2
            continue
        if current == '"':
            break
        probe += 1
    if probe >= body_end - 1:
        return None
    if not _starts_with_command(line[probe + 1:body_end - 1]):
        return None
    return (probe, body_end, True)


def _classify_arg(raw: str, quoted: bool, command: str, index: int, arg_count: int) -> tuple[str, bool]:
    value = raw[1:-1] if quoted and raw.endswith('"') else raw[1:] if quoted else raw
    if quoted:
        # Quoting does not make an asset path or URL translatable.  The engine
        # accepts quoted paths in several UI/resource commands.
        if command in ASSIGN_COMMANDS:
            return "UNKNOWN_VALUE", False
        if URL_RE.fullmatch(value):
            return "EXTERNAL_URL", False
        if FILE_RE.match(value) and not NUMBER_RE.fullmatch(value):
            return ("RESOURCE_PATH" if command in RESOURCE_COMMANDS else "FILENAME"), False
        if value.startswith("(") and re.search(r"(?:\.\*|\(\?[:=!<])", value):
            return "REGEX_LITERAL", False
        if command in PROTECTED_QUOTED_COMMANDS:
            return "CODE_LITERAL", False
        # Optional flags may legally follow the quoted display argument.
        # A dialog's first string is the prompt; later quoted arguments are
        # callback code/values, not additional UI copy.
        if command == "ダイアログ" and index > 0:
            return "OPAQUE_NESTED_CODE", False
        if command in DISPLAY_COMMANDS:
            return "DISPLAY", True
        if P.needs_nested_parse(command):
            return "OPAQUE_NESTED_CODE", False
        return "UNKNOWN_QUOTED", False
    # A decimal such as `0.0` ends in `.0`, so the generic extension matcher
    # would otherwise mislabel numeric command arguments as filenames before
    # the Commands.xml positional schema gets a chance to classify them.
    if FILE_RE.match(value) and not NUMBER_RE.fullmatch(value):
        return ("RESOURCE_PATH" if command in RESOURCE_COMMANDS else "FILENAME"), False
    # Ask the engine's own signature first.  Positional typing only answers
    # while every preceding slot is required, so an optional parameter never
    # silently shifts the meaning of the arguments after it.
    slot_role = positional_role(command, index)
    if slot_role is not None:
        return slot_role, False
    if command in JUMP_COMMANDS and index == arg_count - 1:
        return "LABEL", False
    if command == "栞" and index == 0:
        return "LABEL", False
    if command in ASSIGN_COMMANDS and index == 0:
        return "VARIABLE_NAME", False
    # A command whose schema we do not have still gets a typed residual token
    # rather than one opaque bucket: the token shape is enough to tell an
    # assignment operator from an asset id from an engine keyword.
    if command in RESOURCE_COMMANDS:
        fine = classify_bare_token(value)
        if fine in {"OPTION_FLAG", "ASSET_ID", "ASSET_GLOB", "NUMBER"}:
            return fine, False
        return "RESOURCE_OR_OPTION", False
    if command in JUMP_COMMANDS:
        return "FILENAME_OR_LABEL", False
    return classify_bare_token(value), False


def _parse_segment(line: str, start: int, end: int) -> tuple[list[Field], str, str]:
    fields: list[Field] = []
    i = start
    while i < end and line[i] in WS:
        i += 1
    while i < end and line[i] in "~.":
        fields.append(Field("PREFIX", i, i + 1, line[i], line[i]))
        i += 1
        while i < end and line[i] in WS:
            i += 1

    if (i < end and line.startswith("【", i)
            and any(field.role == "PREFIX" and field.raw == "~" for field in fields)):
        close = line.find("】", i + 1, end)
        if close >= 0:
            fields.append(Field("SPEAKER_MARKER", i, i + 1, "【", "【"))
            name = line[i + 1:close]
            fields.append(Field("SPEAKER_NAME", i + 1, close, name, name, bool(name),
                                _display_children(name, i + 1, False)))
            fields.append(Field("SPEAKER_MARKER", close, close + 1, "】", "】"))
            rest_fields, rest_kind, rest_confidence = _parse_segment(line, close + 1, end)
            if rest_kind == "empty":
                return fields, "speaker", "high"
            return fields + rest_fields, "mixed", rest_confidence

    # The documented form uses ``~【name】``, but a few Light.vn exports omit
    # the tilde.  Accept only a bracket at the beginning of a segment whose
    # remainder is empty or visibly dialogue-like; otherwise a literal bracket
    # in prose must not be reclassified as a speaker.
    if i < end and line.startswith("【", i):
        close = line.find("】", i + 1, end)
        if close >= 0:
            rest = line[close + 1:end].lstrip(WS)
            dialogue_like = (not rest or rest.startswith(('"', '-"', '<文字色 '))
                             or WAIT_END_RE.search(rest))
            if dialogue_like:
                fields.append(Field("SPEAKER_MARKER", i, i + 1, "【", "【"))
                name = line[i + 1:close]
                fields.append(Field("SPEAKER_NAME", i + 1, close, name, name,
                                    bool(name), _display_children(name, i + 1, False)))
                fields.append(Field("SPEAKER_MARKER", close, close + 1, "】", "】"))
                if not rest:
                    return fields, "speaker", "low"
                rest_fields, rest_kind, rest_confidence = _parse_segment(
                    line, close + 1, end)
                return fields + rest_fields, "mixed", "low"

    if line.startswith("//", i):
        raw = line[start:end]
        return [Field("COMMENT", start, end, raw, raw)], "comment", "high"

    # A segment may contain repeated conditional prefixes, for example
    # `~もし (...) ~もし (...) -"text\\w"`.  Parse each condition in turn;
    # otherwise the second `もし` is mistaken for a command and its dialogue
    # becomes protected unknown code.
    has_condition = False
    valid_condition = True
    while True:
        cond_keyword_start = i
        while cond_keyword_start < end and line[cond_keyword_start] in WS:
            cond_keyword_start += 1
        next_i, next_condition, next_valid = _skip_condition(line[:end], i, 0)
        if not next_condition:
            i = cond_keyword_start
            break
        keyword = next((word for word in CONDITIONALS
                        if line.startswith(word, cond_keyword_start)), None)
        if keyword:
            fields.append(Field("CONDITIONAL_COMMAND", cond_keyword_start,
                                cond_keyword_start + len(keyword), keyword, keyword))
        condition = next_condition
        fields.append(Field(condition.role, condition.start, condition.end,
                            condition.raw, condition.value, condition.translatable,
                            condition.children))
        has_condition = True
        valid_condition = valid_condition and next_valid
        i = next_i
        while i < end and line[i] in WS:
            i += 1
        if i < end and line[i] == "~":
            fields.append(Field("PREFIX", i, i + 1, "~", "~"))
            i += 1
            while i < end and line[i] in WS:
                i += 1
            continue
        break

    # Preserve any non-conditional command prefix after the condition chain.
    while i < end and line[i] == "~":
        fields.append(Field("PREFIX", i, i + 1, "~", "~"))
        i += 1
        while i < end and line[i] in WS:
            i += 1

    # Conditional speaker rows put the speaker marker after the condition,
    # unlike ordinary rows where it is the first construct on the segment.
    if (i < end and line.startswith("【", i)
            and any(field.role == "PREFIX" and field.raw == "~" for field in fields)):
        close = line.find("】", i + 1, end)
        if close >= 0:
            fields.append(Field("SPEAKER_MARKER", i, i + 1, "【", "【"))
            name = line[i + 1:close]
            fields.append(Field("SPEAKER_NAME", i + 1, close, name, name, bool(name),
                                _display_children(name, i + 1, False)))
            fields.append(Field("SPEAKER_MARKER", close, close + 1, "】", "】"))
            rest_fields, rest_kind, rest_confidence = _parse_segment(line, close + 1, end)
            if rest_kind == "empty":
                return fields, "speaker", "high"
            return fields + rest_fields, "mixed", rest_confidence

    # In Light.vn, a conditional dialogue continuation can omit the opening
    # quote (and may use a leading `-` continuation marker). The wait control
    # token is the distinguishing evidence; keep the condition and marker as
    # code while exposing only the visible suffix.
    if (has_condition and WAIT_END_RE.search(line[i:end])
            and any(field.role == "PREFIX" and field.raw == "~" for field in fields)
            and i < end and line[i] != '"'
            and not line.startswith('-"', i)):
        display_start = i
        if line[display_start] == "-":
            fields.append(Field("DIALOGUE_MARKER", display_start, display_start + 1, "-", "-"))
            display_start += 1
        probe = display_start
        while probe < end and line[probe] in WS:
            probe += 1
        command_end = probe
        while command_end < end and line[command_end] not in WS:
            command_end += 1
        candidate = line[probe:command_end]
        if (candidate and candidate not in KNOWN_SCHEMA_COMMANDS
                and candidate not in {"もし", "違ってももし", "違ったら"}
                and candidate not in _project_macro_names()
                and not P.is_known_command(candidate)):
            raw = line[display_start:end]
            fields.append(Field("DISPLAY", display_start, end, raw, raw, True,
                                _display_children(raw, display_start, False)))
            return fields, "dialogue", "high" if valid_condition else "low"

    # Some shipped scripts encode a visible fragment directly as a leading
    # rich-text tag sequence rather than a `文字` command or quoted dialogue.
    # Recognize only the reviewed color-tag grammar; XML/data rows such as
    # `<frame>` and `<tile>` must remain non-translatable.
    rich_raw = line[i:end]
    if rich_raw.startswith("<文字色 ") and "</>" in rich_raw:
        tags = list(re.finditer(r"<[^<>]*>", rich_raw))
        valid_tags = bool(tags) and all(
            re.fullmatch(r"<文字色\s+\d+\s+\d+\s+\d+>|</>", m.group(0))
            for m in tags
        )
        has_payload = any(
            part.strip() for part in re.split(r"<[^<>]*>", rich_raw)
        )
        if valid_tags and has_payload:
            fields.append(Field("DISPLAY", i, end, rich_raw, rich_raw, True,
                                _display_children(rich_raw, i, False)))
            return fields, "dialogue", "high" if valid_condition else "low"

    # A standalone dialogue line, optionally prefixed by a speaker dash.
    quote_pos = i
    if quote_pos < end and line[quote_pos] == "-" and quote_pos + 1 < end and line[quote_pos + 1] == '"':
        fields.append(Field("DIALOGUE_MARKER", quote_pos, quote_pos + 1, "-", "-"))
        quote_pos += 1
    if quote_pos < end and line[quote_pos] == '"':
        # A dialogue's opening quote is a marker, not a quoted-argument
        # delimiter. Inner quotation marks are ordinary visible punctuation;
        # the dialogue ends at a control marker or a later physical line.
        qend = end
        raw = line[quote_pos:qend]
        fields.append(Field("DISPLAY", quote_pos, qend, raw, raw[1:-1] if raw.endswith('"') else raw[1:], True,
                            _display_children(raw, quote_pos, True)))
        return fields, "dialogue", "high" if valid_condition else "low"

    # A bare row ending in `\w` may be dialogue, but only when its first token
    # is not a command or macro. A control-only `\w` remains code.
    bare = line[i:end].strip()
    # Some dialogue rows start with `{{variable}}` and omit the opening quote.
    # The closing `\w` marks the visible text boundary.
    if (not has_condition
            and not any(field.role == "PREFIX" for field in fields)
            and re.match(r"^\{\{[^{}]+\}\}\s*[^\r\n]*\\w[。．.!！?？…]*$", bare)
            and not bare.startswith(("{{栞", "{{ジャンプ", "{{スクリプト"))):
        raw = line[i:end]
        fields.append(Field("DISPLAY", i, end, raw, raw, True,
                            _display_children(raw, i, False)))
        return fields, "dialogue", "low"
    if (not has_condition
            and not any(field.role == "PREFIX" for field in fields)
            and WAIT_END_RE.search(bare)
            and '"' not in bare
            and not re.fullmatch(r"\\+w", bare)
            and not bare.startswith(("//", "#", "■", "栞 ", "栞\t", "栞\u3000",
                                    "{", "}", "/*", "*/", "s/"))):
        probe = i
        while probe < end and line[probe] in WS:
            probe += 1
        command_end = probe
        while command_end < end and line[command_end] not in WS:
            command_end += 1
        candidate = line[probe:command_end]
        if (candidate and candidate not in KNOWN_SCHEMA_COMMANDS
                and candidate not in {"もし", "違ってももし", "違ったら"}
                and candidate not in _project_macro_names()
                and not P.is_known_command(candidate)):
            raw = line[i:end]
            fields.append(Field("DISPLAY", i, end, raw, raw, True,
                                _display_children(raw, i, False)))
            return fields, "dialogue", "low"

    # A few generated scripts contain a bare, split condition fragment on its
    # own physical row (for example `((state == "立ち") &&`).  It is code, not
    # an unknown command or a display candidate; keep the whole fragment
    # protected so a later extraction pass cannot offer its literal to a
    # translator.
    fragment = line[i:end].strip()
    if (fragment.startswith("(")
            and re.search(r"(?:==|!=|<=|>=|&&|\|\|)", fragment)):
        frag_start = i + len(line[i:end]) - len(line[i:end].lstrip())
        fields.append(Field("CODE_FRAGMENT", frag_start, end,
                            line[frag_start:end], line[frag_start:end]))
        return fields, "code", "high" if valid_condition else "low"

    # No command token: preserve as unknown prose/code, never translate.
    if i >= end:
        return fields, "empty", "high"
    cmd_start = i
    while i < end and line[i] not in WS and line[i] != '"':
        i += 1
    if i == cmd_start:
        raw = line[start:end]
        fields.append(Field("UNKNOWN", start, end, raw, raw))
        return fields, "unknown", "low"
    command = line[cmd_start:i]
    known_command = (command in KNOWN_SCHEMA_COMMANDS
                     or command in {"もし", "違ってももし", "違ったら"}
                     or command in EXTRA_COMMANDS
                     or command in _project_macro_names()
                     or P.is_known_command(command))
    command_role = "COMMAND" if known_command else "UNKNOWN_COMMAND"
    fields.append(Field(command_role, cmd_start, i, command, command))
    args = _tokens(line, i, end)
    nested_display_args = set()
    code_literal_args = set()
    base_command = P.command_variant_match(command) or command
    # Light.vn lets a callback command be wrapped in a pair of quotes that are
    # NOT escaped, e.g.
    #   衝突継続時 npc_a player1 "保存変数 表情 = "検索" | 保存変数 相手 = "なし""
    # A plain quote pairing splits that into six fragments and turns most of the
    # callback into unknown junk.  The callback is one opaque argument that runs
    # from its opening quote to the end of the segment, so collapse it here
    # while keeping the exact source spans a replacement needs.
    if P.needs_nested_parse(base_command) and command not in DISPLAY_COMMANDS:
        # A display command (ダイアログ / ボタン文字 …) treats its quoted first
        # argument as visible text, so its quote pairing must stay untouched.
        callback = _nested_callback_span(line, i, end)
        if callback is not None:
            args = [token for token in args if token[1] <= callback[0]]
            args.append(callback)
    if command in CALL_COMMANDS:
        value_args = [
            (arg_index, arg_start, arg_end, quoted)
            for arg_index, (arg_start, arg_end, quoted) in enumerate(args)
        ]
        if len(value_args) >= 2:
            target = line[value_args[0][1]:value_args[0][2]].replace("\\", "/").casefold()
            label = line[value_args[1][1]:value_args[1][2]]
            for position in SCRIPT_CODE_CALL_ARGS.get((target, label), set()):
                arg_index = position + 2
                if arg_index < len(args):
                    code_literal_args.add(arg_index)
    if P.needs_nested_parse(base_command):
        # Some callback-bearing commands contain an inline command sequence
        # rather than quoting the whole callback. Parse recognized display
        # commands from their exact token boundary, then promote only the
        # quoted spans that the ordinary command schema marks as display.
        # This catches e.g. `イベント ... 後 ダイアログ "..."` without
        # treating arbitrary quoted callback payloads as prose.
        for arg_index, (arg_start, arg_end, quoted) in enumerate(args):
            if quoted or line[arg_start:arg_end] not in DISPLAY_COMMANDS:
                continue
            nested = parse_line(line[arg_start:end])
            for nested_field in nested.fields:
                if nested_field.role != "DISPLAY":
                    continue
                abs_start = arg_start + nested_field.start
                abs_end = arg_start + nested_field.end
                for candidate_index, (candidate_start, candidate_end, candidate_quoted) in enumerate(args):
                    if candidate_quoted and candidate_start == abs_start and candidate_end == abs_end:
                        nested_display_args.add(candidate_index)
    for index, (a, b, quoted) in enumerate(args):
        raw = line[a:b]
        if index in nested_display_args:
            role, translatable = "DISPLAY", True
        elif index in code_literal_args:
            role, translatable = "CODE_LITERAL", False
        elif known_command:
            role, translatable = _classify_arg(raw, quoted, command, index, len(args))
        else:
            role, translatable = ("UNKNOWN_QUOTED" if quoted else "UNKNOWN"), False
        value = raw[1:-1] if quoted and raw.endswith('"') else raw[1:] if quoted else raw
        children = _display_children(raw, a, True) if translatable else []
        fields.append(Field(role, a, b, raw, value, translatable, children))
    return fields, "command" if known_command else "unknown", "high" if valid_condition else "low"


def parse_line(line: str) -> ParsedLine:
    """Parse one physical line; unknown or ambiguous text stays non-translatable."""
    fields: list[Field] = []
    body_end = _line_body_end(line)
    source = line[:body_end]
    if source.strip() in NON_DISPLAY_MARKERS:
        start = source.find(source.strip())
        fields.append(Field("COMMENT", start, start + len(source.strip()), source.strip(), source.strip()))
        if body_end < len(line):
            fields.append(Field("LINE_ENDING", body_end, len(line), line[body_end:], line[body_end:]))
        return ParsedLine(line, "comment", fields, "high")
    if _is_bare_wait_marker(source):
        fields.append(Field("CONTROL_TOKEN", 0, body_end, source, source))
        if body_end < len(line):
            fields.append(Field("LINE_ENDING", body_end, len(line), line[body_end:], line[body_end:]))
        return ParsedLine(line, "command", fields, "high")
    segments = _segments(source)
    kinds = []
    confidences = []
    for n, (a, b) in enumerate(segments):
        seg_fields, kind, confidence = _parse_segment(source, a, b)
        fields.extend(seg_fields)
        kinds.append(kind)
        confidences.append(confidence)
        if n + 1 < len(segments):
            sep_start = b
            fields.append(Field("PIPE_SEPARATOR", sep_start, sep_start + 3, source[sep_start:sep_start + 3], source[sep_start:sep_start + 3]))
    if len(kinds) == 1:
        kind = kinds[0]
    elif all(x == "command" for x in kinds):
        kind = "command_chain"
    else:
        kind = "mixed"
    confidence = "low" if "low" in confidences else "high"
    if body_end < len(line):
        fields.append(Field("LINE_ENDING", body_end, len(line), line[body_end:], line[body_end:]))
    return ParsedLine(line, kind, fields, confidence)
