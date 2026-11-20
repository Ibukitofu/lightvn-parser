# -*- coding: utf-8 -*-
"""field_types.py -- Field and ParsedLine: the parsed-line data model."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Iterable, Optional


WS = " \t\u3000"

# Display roles that are safe to translate. DISPLAY_UNSAFE is excluded.
DISPLAY_ROLES = frozenset({'DISPLAY', 'DISPLAY_CONTINUATION', 'DISPLAY_INFERRED'})


CONDITIONALS = ("違ってももし", "もし")
TOKEN_RE = re.compile(r"\{\{.*?\}\}|\\[A-Za-z/]+|</>|<[^<>]*>", re.S)


FILE_RE = re.compile(r"(?i)(?:^|[/\\])[^\s\"|]+\.[a-z0-9]{1,8}$|^[^\s\"|]+\.[a-z0-9]{1,8}$")


URL_RE = re.compile(r"(?i)^https?://[^\s\"]+$")


WAIT_END_RE = re.compile(r"\\w[。．.!！?？…]*\s*$")


NON_DISPLAY_MARKERS = {"----------更新----------"}


MACRO_DEF_RE = re.compile(r'^\s*[~.]?\s*(?:マクロ|コマンドマクロ)\s+"([^"]+)"')



ASSIGN_OPERATORS = frozenset({"=", "+=", "-=", "*=", "/=", "%=", "^=", "&=", "|="})


COMPARE_OPERATORS = frozenset({"==", "!=", "<=", ">=", "<", ">"})


BOOLEAN_LITERALS = frozenset({"true", "false", "True", "False", "TRUE", "FALSE",
                             "ON", "OFF", "on", "off"})


NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)%?")
# Chapter/menu headings the editor writes as plain rows (■攻撃（通常）).


SECTION_HEADER_RE = re.compile(r"^[■●◆◇▼▽▷►]")
# Author/patch notes carry a row locator instead of prose (319行目, （元名：…）).


MEMO_LINE_RE = re.compile(r"^(?:\d+\s*行目|[（(]元名[：:]|※)")


PLUGIN_DOC_HEADING_RE = re.compile(
    r"^(?:説明|対応バージョン|設置|使い方|作者|作者名|ライセンス|更新履歴)[：:]?\s*$"
)
# Asset identifiers that never resolve to a file on disk.


ASSET_PREFIXES = ("map_", "cg_", "bat_", "se_", "bgm_", "voice_", "enemy_",
                  "img/", "chip/", "menu/", "atk_ef/", "モブ立ち絵/", "背景/",
                  "icon/", "子宮/", "e出産", "e敗北", "音量_")


ASSET_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+){2,}")

@dataclass
class Field:
    role: str
    start: int
    end: int
    raw: str
    value: str
    translatable: bool = False
    children: list["Field"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass


@dataclass
class ParsedLine:
    raw: str
    kind: str
    fields: list[Field]
    confidence: str

    def serialize(self) -> str:
        """Rebuild the source line from parsed spans."""
        spans = sorted((f.start, f.end, f.raw) for f in self.fields if f.end > f.start)
        out = []
        cursor = 0
        for begin, finish, raw in spans:
            if begin < cursor:
                raise ValueError('overlapping field span at %d' % begin)
            if self.raw[begin:finish] != raw:
                raise ValueError('stale field span at %d' % begin)
            out.append(self.raw[cursor:begin])
            out.append(raw)
            cursor = finish
        out.append(self.raw[cursor:])
        rebuilt = ''.join(out)
        if rebuilt != self.raw:
            raise ValueError('rebuild mismatch')
        return rebuilt

    def unclassified_spans(self) -> list[tuple[int, int, str]]:
        """Return uncovered non-whitespace source spans for the extraction gate."""
        covered = bytearray(len(self.raw))
        for item in self.fields:
            for i in range(max(0, item.start), min(len(self.raw), item.end)):
                covered[i] = 1
        spans = []
        i = 0
        while i < len(self.raw):
            if covered[i] or self.raw[i].isspace():
                i += 1
                continue
            start = i
            while i < len(self.raw) and not covered[i] and not self.raw[i].isspace():
                i += 1
            spans.append((start, i, self.raw[start:i]))
        return spans

    def replace_field(self, target: Field, translated: str) -> str:
        """Replace one translatable field and verify its source span."""
        if not target.translatable:
            raise ValueError("field is not translatable")
        if self.raw[target.start:target.end] != target.raw:
            raise ValueError("stale or invalid field span")
        is_speaker = target.role == "SPEAKER_NAME"
        if is_speaker:
            if any(c in translated for c in "\r\n【】"):
                raise ValueError("speaker translation cannot alter marker structure")
            source_tokens = [m.group(0) for m in TOKEN_RE.finditer(target.value)]
            translated_tokens = [m.group(0) for m in TOKEN_RE.finditer(translated)]
            if source_tokens != translated_tokens:
                raise ValueError("translated speaker changed or reordered protected tokens")
            return self.raw[:target.start] + translated + self.raw[target.end:]
        quoted_dialogue = target.raw.startswith('"')
        continuation = target.role in {"DISPLAY_CONTINUATION", "DISPLAY_INFERRED"}
        if not quoted_dialogue and self.kind != "dialogue" and not continuation:
            raise ValueError("unquoted display field is only valid for dialogue text")
        balanced_argument = quoted_dialogue and target.raw.endswith('"') and len(target.raw) > 1
        if quoted_dialogue and not balanced_argument and self.kind != "dialogue":
            raise ValueError("unbalanced quote is only valid for dialogue text")
        if '"' in translated or "\r" in translated or "\n" in translated:
            raise ValueError("translation cannot add quotes or physical line breaks")
        source_value = target.value
        if " | " in translated and " | " not in source_value:
            raise ValueError("translation cannot inject a segment separator")
        if chr(0) in translated:
            raise ValueError("translation cannot contain NUL")
        if translated.startswith("-") and not source_value.startswith("-"):
            raise ValueError("translation cannot start with a dialogue continuation dash")
        if translated.lstrip().startswith("【") and not source_value.lstrip().startswith("【"):
            raise ValueError("translation cannot inject a speaker marker")
        source_tokens = [m.group(0) for m in TOKEN_RE.finditer(source_value)]
        translated_tokens = [m.group(0) for m in TOKEN_RE.finditer(translated)]
        if source_tokens != translated_tokens:
            raise ValueError("translated display changed, removed, or reordered protected tokens")
        if not quoted_dialogue:
            return self.raw[:target.start] + translated + self.raw[target.end:]
        suffix = self.raw[target.end - 1:] if balanced_argument else ""
        return self.raw[:target.start + 1] + translated + suffix

    def replace_display(self, field_index: int, translated: str) -> str:
        """Replace one line-level DISPLAY value while protecting tokens."""
        candidates = [f for f in self.fields if f.role in {"DISPLAY", "SPEAKER_NAME"} and f.translatable]
        return self.replace_field(candidates[field_index], translated)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "confidence": self.confidence,
            "raw": self.raw,
            "fields": [x.to_dict() for x in self.fields],
        }
