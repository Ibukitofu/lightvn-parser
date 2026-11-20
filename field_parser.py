# -*- coding: utf-8 -*-
"""field_parser.py -- compatibility facade.

The parser used to be one 2,142-line module. It is now split by change
reason; this module only re-exports the pieces so existing callers keep
working. See README.md for the module map.
"""

try:
    from .field_types import (  # noqa: F401
        ASSET_ID_RE,
        ASSET_PREFIXES,
        ASSIGN_OPERATORS,
        BOOLEAN_LITERALS,
        COMPARE_OPERATORS,
        CONDITIONALS,
        DISPLAY_ROLES,
        FILE_RE,
        Field,
        MACRO_DEF_RE,
        MEMO_LINE_RE,
        NON_DISPLAY_MARKERS,
        NUMBER_RE,
        PLUGIN_DOC_HEADING_RE,
        ParsedLine,
        SECTION_HEADER_RE,
        TOKEN_RE,
        URL_RE,
        WAIT_END_RE,
        WS,
    )
except ImportError:
    from field_types import (  # noqa: F401
        ASSET_ID_RE,
        ASSET_PREFIXES,
        ASSIGN_OPERATORS,
        BOOLEAN_LITERALS,
        COMPARE_OPERATORS,
        CONDITIONALS,
        DISPLAY_ROLES,
        FILE_RE,
        Field,
        MACRO_DEF_RE,
        MEMO_LINE_RE,
        NON_DISPLAY_MARKERS,
        NUMBER_RE,
        PLUGIN_DOC_HEADING_RE,
        ParsedLine,
        SECTION_HEADER_RE,
        TOKEN_RE,
        URL_RE,
        WAIT_END_RE,
        WS,
    )

try:
    from .grammar import (  # noqa: F401
        _display_children,
        _is_bare_wait_marker,
        _line_body_end,
        _quote_end,
        _segments,
        _tokens,
    )
except ImportError:
    from grammar import (  # noqa: F401
        _display_children,
        _is_bare_wait_marker,
        _line_body_end,
        _quote_end,
        _segments,
        _tokens,
    )

try:
    from .schema import (  # noqa: F401
        ASSIGN_COMMANDS,
        CALL_COMMANDS,
        DISPLAY_COMMANDS,
        EXTRA_COMMANDS,
        EXTRA_SIGNATURES,
        JUMP_COMMANDS,
        KNOWN_SCHEMA_COMMANDS,
        PROTECTED_QUOTED_COMMANDS,
        RESOURCE_COMMANDS,
        SCRIPT_CODE_CALL_ARGS,
        SCRIPT_DISPLAY_CALL_ARGS,
        STATIC_OPTION_FLAGS,
        TEXT_ASSIGN_COMMANDS,
        _SLOT_CACHE,
        _SLOT_RULES,
        _literal_macro_names,
        _project_macro_names,
        _slot_role,
        _starts_with_command,
        _syntax_slots,
        classify_bare_token,
        command_slots,
        official_option_flags,
        positional_role,
    )
except ImportError:
    from schema import (  # noqa: F401
        ASSIGN_COMMANDS,
        CALL_COMMANDS,
        DISPLAY_COMMANDS,
        EXTRA_COMMANDS,
        EXTRA_SIGNATURES,
        JUMP_COMMANDS,
        KNOWN_SCHEMA_COMMANDS,
        PROTECTED_QUOTED_COMMANDS,
        RESOURCE_COMMANDS,
        SCRIPT_CODE_CALL_ARGS,
        SCRIPT_DISPLAY_CALL_ARGS,
        STATIC_OPTION_FLAGS,
        TEXT_ASSIGN_COMMANDS,
        _SLOT_CACHE,
        _SLOT_RULES,
        _literal_macro_names,
        _project_macro_names,
        _slot_role,
        _starts_with_command,
        _syntax_slots,
        classify_bare_token,
        command_slots,
        official_option_flags,
        positional_role,
    )

try:
    from .line_parser import (  # noqa: F401
        _classify_arg,
        _nested_callback_span,
        _parse_segment,
        _skip_condition,
        parse_line,
    )
except ImportError:
    from line_parser import (  # noqa: F401
        _classify_arg,
        _nested_callback_span,
        _parse_segment,
        _skip_condition,
        parse_line,
    )

try:
    from .documents import (  # noqa: F401
        _bare_dialogue_candidate,
        _continued_bare_dialogue_end,
        _display_body_span,
        _ends_text_window,
        _infer_bare_dialogue_end,
        classify_document_role,
        classify_source_content,
        group_dialogue_windows,
        parse_document,
        triage_unresolved_line,
    )
except ImportError:
    from documents import (  # noqa: F401
        _bare_dialogue_candidate,
        _continued_bare_dialogue_end,
        _display_body_span,
        _ends_text_window,
        _infer_bare_dialogue_end,
        classify_document_role,
        classify_source_content,
        group_dialogue_windows,
        parse_document,
        triage_unresolved_line,
    )

try:
    from .inference import (  # noqa: F401
        LOGIC_STRING_VALUES,
        _assignment_aliases,
        _numeric_dynamic_assignment_links,
        _pipe_groups,
        _variable_refs,
        collect_comparison_literals,
        infer_display_only_variables,
        infer_display_parameter_indices,
        infer_display_variable_roles,
        promote_inferred_display_arguments,
        promote_inferred_display_assignments,
    )
except ImportError:
    from inference import (  # noqa: F401
        LOGIC_STRING_VALUES,
        _assignment_aliases,
        _numeric_dynamic_assignment_links,
        _pipe_groups,
        _variable_refs,
        collect_comparison_literals,
        infer_display_only_variables,
        infer_display_parameter_indices,
        infer_display_variable_roles,
        promote_inferred_display_arguments,
        promote_inferred_display_assignments,
    )

try:
    from .audit import (  # noqa: F401
        main,
        scan_directory,
    )
except ImportError:
    from audit import (  # noqa: F401
        main,
        scan_directory,
    )

__all__ = [
    'ASSET_ID_RE',
    'DISPLAY_ROLES',
    'ASSET_PREFIXES',
    'ASSIGN_OPERATORS',
    'BOOLEAN_LITERALS',
    'COMPARE_OPERATORS',
    'CONDITIONALS',
    'FILE_RE',
    'Field',
    'MACRO_DEF_RE',
    'MEMO_LINE_RE',
    'NON_DISPLAY_MARKERS',
    'NUMBER_RE',
    'PLUGIN_DOC_HEADING_RE',
    'ParsedLine',
    'SECTION_HEADER_RE',
    'TOKEN_RE',
    'URL_RE',
    'WAIT_END_RE',
    'WS',
    '_display_children',
    '_is_bare_wait_marker',
    '_line_body_end',
    '_quote_end',
    '_segments',
    '_tokens',
    'ASSIGN_COMMANDS',
    'CALL_COMMANDS',
    'DISPLAY_COMMANDS',
    'EXTRA_COMMANDS',
    'EXTRA_SIGNATURES',
    'JUMP_COMMANDS',
    'KNOWN_SCHEMA_COMMANDS',
    'PROTECTED_QUOTED_COMMANDS',
    'RESOURCE_COMMANDS',
    'SCRIPT_CODE_CALL_ARGS',
    'SCRIPT_DISPLAY_CALL_ARGS',
    'STATIC_OPTION_FLAGS',
    'TEXT_ASSIGN_COMMANDS',
    '_SLOT_CACHE',
    '_SLOT_RULES',
    '_literal_macro_names',
    '_project_macro_names',
    '_slot_role',
    '_starts_with_command',
    '_syntax_slots',
    'classify_bare_token',
    'command_slots',
    'official_option_flags',
    'positional_role',
    '_classify_arg',
    '_nested_callback_span',
    '_parse_segment',
    '_skip_condition',
    'parse_line',
    '_bare_dialogue_candidate',
    '_continued_bare_dialogue_end',
    '_display_body_span',
    '_ends_text_window',
    '_infer_bare_dialogue_end',
    'classify_document_role',
    'classify_source_content',
    'group_dialogue_windows',
    'parse_document',
    'triage_unresolved_line',
    'LOGIC_STRING_VALUES',
    '_assignment_aliases',
    '_numeric_dynamic_assignment_links',
    '_pipe_groups',
    '_variable_refs',
    'collect_comparison_literals',
    'infer_display_only_variables',
    'infer_display_parameter_indices',
    'infer_display_variable_roles',
    'promote_inferred_display_arguments',
    'promote_inferred_display_assignments',
    'main',
    'scan_directory',
]


try:
    from . import inference as _inference_module, schema as _schema_module
except ImportError:
    import inference as _inference_module, schema as _schema_module


_LIVE_FORWARDS = {
    '_OPTION_FLAGS': ('schema', '_OPTION_FLAGS'),
    '_PROJECT_MACRO_NAMES': ('schema', '_PROJECT_MACRO_NAMES'),
    '_COMPARISON_LITERALS': ('inference', '_COMPARISON_LITERALS'),
}


def __getattr__(name):
    """Forward mutable module-level caches so readers see the live value.

    A plain ``from .x import y`` snapshots the binding at import time, so
    ``_OPTION_FLAGS`` would stay ``None`` and ``_COMPARISON_LITERALS`` would stay
    empty forever.  Forwarding keeps this facade honest.
    """
    if name in _LIVE_FORWARDS:
        _, attr = _LIVE_FORWARDS[name]
        source = _schema_module if name != "_COMPARISON_LITERALS" else _inference_module
        return getattr(source, attr)
    raise AttributeError(name)
