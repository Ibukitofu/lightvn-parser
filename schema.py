# -*- coding: utf-8 -*-
"""schema.py -- Engine metadata: command sets, argument slots, and the role of each slot."""

from __future__ import annotations

import os
import re
from typing import Iterable, Optional
try:
    from . import lvparse as P
except ImportError:
    import lvparse as P

try:
    from .field_types import ASSET_ID_RE, ASSET_PREFIXES, ASSIGN_OPERATORS, BOOLEAN_LITERALS, COMPARE_OPERATORS, MACRO_DEF_RE, MEMO_LINE_RE, NUMBER_RE, SECTION_HEADER_RE, WS
except ImportError:
    from field_types import ASSET_ID_RE, ASSET_PREFIXES, ASSIGN_OPERATORS, BOOLEAN_LITERALS, COMPARE_OPERATORS, MACRO_DEF_RE, MEMO_LINE_RE, NUMBER_RE, SECTION_HEADER_RE, WS


# User-visible command arguments. The `0` forms are engine variants.
# `ダイアログ` may have callback arguments after its display string.
DISPLAY_COMMANDS = {
    "文字", "文字0", "文字窓", "文字窓0", "ボタン文字", "ボタン文字0",
    "バックログ続く文章追加", "バックログ現在話者", "ダイアログ",
}


JUMP_COMMANDS = {"ジャンプ", "スクリプト", "最終ジャンプ"}


CALL_COMMANDS = {"スクリプト", "並列スクリプト"}
# Reviewed display parameters for external script calls.
SCRIPT_DISPLAY_CALL_ARGS = {
    ("item_get.txt", "アチーブメント表示2"): {0},
    ("tut_map_2_kojiken.txt", "名前更新"): {0},
    ("/plugins/map_natuki/map.txt", "説明表示"): {0},
}


SCRIPT_CODE_CALL_ARGS = {
    ("cg/sd_cg8.txt", "cg2_ソフィラ汗"): {0},
    ("cg/sd_cg8.txt", "cg3_ソフィラ汗"): {0},
}


PROTECTED_QUOTED_COMMANDS = {
    "バックログ改ページ接頭辞", "状態更新機", "効果音",
}


_PROJECT_MACRO_NAMES: Optional[set[str]] = None
_PROJECT_MACRO_KEY: Optional[str] = None


ASSIGN_COMMANDS = {"保存変数", "変数", "臨時全域変数", "全域変数", "変数式確認機"}


TEXT_ASSIGN_COMMANDS = ASSIGN_COMMANDS - {"変数式確認機"}


RESOURCE_COMMANDS = {
    "絵", "絵0", "画像", "画像0", "背景", "背景0", "背景音", "効果音",
    "ボイス", "動画", "アニメ登録", "タッチ素材設定",
}


KNOWN_SCHEMA_COMMANDS = DISPLAY_COMMANDS | JUMP_COMMANDS | ASSIGN_COMMANDS | RESOURCE_COMMANDS | {"栞"}
# Commands used by the engine/project but absent from the selected engine
# command table. These are command names only; their arguments remain opaque.
EXTRA_COMMANDS = {
    "衝突開始時", "反復実行",
    "会話向き_モブ", "会話向き_モブ2",
    "会話向き_ヒロインモブ", "会話向き_ヒロインモブ2",
    "会話向き_ヒロインモブ3",
}


# Seed options used when Commands.xml is absent so
# option recognition still works on a test fixture or another install.
STATIC_OPTION_FLAGS = frozenset({
    "全部", "ボタン選択", "メッセージ選択", "演出終了", "アニメ終了", "個体消滅",
    "続行禁止", "文字出力完了", "文字入力完了", "動画終了", "カメラ付着", "y軸固定",
    "xy軸固定", "2D視点", "3D視点", "セーブ無視", "無", "反復", "縦", "横", "干渉可能",
    "中央", "左", "右", "上", "下", "上下", "左右", "前", "後", "透明無視", "初期化",
    "現在年", "現在月", "現在日", "現在時", "現在分", "現在秒", "設定反映",
    "オート設定反映", "表示", "永久", "一フレームのみ", "全画面領域", "同階層画面領域",
    "通常スキップ", "続行時スキップ", "スキップ禁止", "バックログ登録禁止",
    "バックログ登録", "原点回帰時解除", "対象位置から", "侵入禁止", "X衝突時初期化",
    "Y衝突時初期化", "現在", "超過無視", "非同期", "軽量積載", "状態更新", "初期値",
    "更新同期",
})

# Commands added or renamed by this project: the engine variant suffix is
# stripped by command_variant_match, but these names are not in Commands.xml at
# all, so their positional schema is stated here instead of being inferred.
# Only slots that are unambiguous in the corpus are listed.
EXTRA_SIGNATURES = {
    "アウト": ("[対象名]", "[時間:ms]", "[フラグ]"),
    "イン": ("[対象名]", "[時間:ms]", "[フラグ]"),
    "会話向き": ("[対象名]",),
    "会話向き_主人公": ("[対象名]",),
    "会話向き_ヒロイン": ("[対象名]",),
    "会話向き_モブ": ("[対象名]",),
    "会話向き_モブ2": ("[対象名]",),
    "会話向き_ヒロインモブ": ("[対象名]",),
    "会話向き_ヒロインモブ2": ("[対象名]",),
    "会話向き_ヒロインモブ3": ("[対象名]",),
    "自由行動外": (),
    "自由行動内": (),
    "自由行動_ワールド": (),
    "文字窓": ("[対象名]", "[x座標]", "[y座標]", "[横幅]", "[縦幅]", "[文字サイズ]",
              "[フォント名]", "[文字サイズ(px)]", "(カメラオプション)"),
}


_OPTION_FLAGS = None


_COMPARISON_LITERALS: set = set()


_SLOT_CACHE = {}


def official_option_flags() -> set[str]:
    """Every legal option word: Commands.xml CmdOptions plus the shipped seed."""
    global _OPTION_FLAGS
    if _OPTION_FLAGS is not None:
        return _OPTION_FLAGS
    flags = set(STATIC_OPTION_FLAGS)
    xml_path = getattr(P, "CMD_XML", None)
    if xml_path and os.path.isfile(xml_path):
        try:
            with open(xml_path, encoding="utf-8", errors="replace") as stream:
                xml = stream.read()
            for body in re.findall(r"<option\b[^>]*>(.*?)</option>", xml, re.S):
                match = re.search(r'<val\s+lang="jap"\s+value="([^"]*)"', body)
                if match:
                    flags.add(match.group(1))
        except OSError:
            pass
    _OPTION_FLAGS = flags
    return flags


def _syntax_slots(syntax: str) -> list[tuple[Optional[bool], str, Optional[str]]]:
    """Split one Commands.xml syntax line into ordered slot descriptors.

    Each entry is (required, inner_text, opener).  A bare token (the command
    name itself) has opener None.  Only the first signature line is read;
    multi-signature commands keep their common form.
    """
    text = ""
    for line in (syntax or "").split("\n"):
        candidate = line.strip()
        if candidate:
            text = re.sub(r"^\d+\.\s*", "", candidate)
            break
    slots = []
    i, total = 0, len(text)
    closers = {"(": ")", "[": "]", "<": ">", '"': '"'}
    while i < total:
        ch = text[i]
        if ch in WS:
            i += 1
            continue
        if ch in closers:
            close = closers[ch]
            depth = 1
            j = i + 1
            buf = []
            while j < total:
                c = text[j]
                if ch in "([<" and c == ch:
                    depth += 1
                elif c == close:
                    depth -= 1
                    if depth == 0:
                        break
                buf.append(c)
                j += 1
            slots.append((ch == "[", "".join(buf), ch))
            i = j + 1
            continue
        j = i
        while j < total and text[j] not in WS and text[j] not in closers:
            j += 1
        slots.append((None, text[i:j], None))
        i = j
    return slots


# Ordered so a more specific phrase wins over a general one.  The
# "数値/変数名" slot has to be tested before "変数名", or an assignment value
# would be read as a variable name.


# Ordered so a more specific phrase wins over a general one.  The
# "数値/変数名" slot has to be tested before "変数名", or an assignment value
# would be read as a variable name.
_SLOT_RULES = (
    ("Light.vnコマンド", "OPAQUE_NESTED_CODE"),
    ("実行コマンド", "OPAQUE_NESTED_CODE"),
    ("数値/変数名", "ASSIGNMENT_VALUE"),
    ("指定・演算", "ASSIGN_OPERATOR"),
    ("ファイル名", "RESOURCE_PATH"),
    ("ファイル経路", "RESOURCE_PATH"),
    ("パス", "RESOURCE_PATH"),
    ("文章内容", "DISPLAY"),
    ("文字列", "DISPLAY"),
    ("テキスト", "DISPLAY"),
    ("栞名", "LABEL"),
    ("変数名", "VARIABLE_NAME"),
    ("カメラオプション", "OPTION_FLAG"),
    ("true/false", "BOOLEAN"),
    ("対象名", "OBJECT_NAME"),
    ("グループ名", "OBJECT_NAME"),
    ("登録名", "OBJECT_NAME"),
    ("対象種類名", "OBJECT_NAME"),
    ("名前", "OBJECT_NAME"),
    ("名称", "OBJECT_NAME"),
    ("対象", "OBJECT_NAME"),
    ("タイプ", "ENUM_KEY"),
    ("種類", "ENUM_KEY"),
    ("モード", "ENUM_KEY"),
    ("数値", "NUMBER"),
    ("座標", "NUMBER"),
    ("角度", "NUMBER"),
    ("比率", "NUMBER"),
    ("時間", "NUMBER"),
    ("サイズ", "NUMBER"),
    ("幅", "NUMBER"),
    ("高さ", "NUMBER"),
    ("拡大度", "NUMBER"),
    ("回数", "NUMBER"),
    ("音量", "NUMBER"),
    ("層", "NUMBER"),
    ("laye", "NUMBER"),
)


def _slot_role(text: str) -> Optional[str]:
    """Map one syntax slot description to a field role."""
    probe = text.replace('"', "").strip()
    for key, role in _SLOT_RULES:
        if key in probe:
            return role
    return None


def command_slots(name: str) -> list[tuple[bool, str]]:
    """Ordered argument slots for one command name; empty when unknown."""
    if not name:
        return []
    cached = _SLOT_CACHE.get(name)
    if cached is not None:
        return cached
    try:
        syntax = P.command_table().get(name, "") or ""
    except Exception:
        syntax = ""
    if not syntax:
        # A project-added command (アウト / イン / 会話向き, or an engine alias
        # such as 絵0) is not in Commands.xml.  Its base name still carries the
        # schema when the engine only extended the name.
        extra = EXTRA_SIGNATURES.get(name)
        if extra is not None:
            syntax = " ".join(extra)
        else:
            base = P.command_variant_match(name)
            if not base and len(name) > 1:
                # One-character command names (絵, 画 …) and two-character ones
                # fall below the variant matcher's minimum prefix length, so an
                # engine alias like 絵0 never reaches it.  Accept an exact
                # table prefix with a 1..4 character suffix instead.
                try:
                    table = P.command_table()
                except Exception:
                    table = {}
                for cut in range(len(name) - 1, max(0, len(name) - 5), -1):
                    candidate = name[:cut]
                    if candidate in table:
                        base = candidate
                        break
            if base:
                try:
                    syntax = P.command_table().get(base, "") or ""
                except Exception:
                    syntax = ""
    slots = [(is_required, text)
             for is_required, text, opener in _syntax_slots(syntax)
             if opener is not None]
    _SLOT_CACHE[name] = slots
    return slots


def positional_role(name: str, index: int) -> Optional[str]:
    """Role of argument index according to the engine's own syntax.

    Positional typing is only trusted while every earlier slot is required.
    As soon as an optional slot appears the engine may omit it, so the position
    stops identifying the parameter; returning None there keeps the caller on
    its conservative fallback instead of guessing.
    """
    slots = command_slots(name)
    if index < 0 or index >= len(slots):
        return None
    for is_required, _text in slots[:index + 1]:
        if not is_required:
            return None
    return _slot_role(slots[index][1])


def classify_bare_token(value: str) -> str:
    """Fine role for a token that carries no quoting and no known command.

    This is the residual classifier: it only runs for values the command schema
    did not already explain, and it never marks anything translatable.
    """
    if not value:
        return "UNKNOWN"
    if value in ASSIGN_OPERATORS:
        return "ASSIGN_OPERATOR"
    if value in COMPARE_OPERATORS:
        return "COMPARE_OPERATOR"
    if value in BOOLEAN_LITERALS:
        return "BOOLEAN"
    if NUMBER_RE.fullmatch(value):
        return "NUMBER"
    if value in official_option_flags():
        return "OPTION_FLAG"
    try:
        if value in P.engine_keywords():
            return "ENGINE_KEYWORD"
    except Exception:
        pass
    if "*" in value:
        return "ASSET_GLOB"
    if value.startswith(ASSET_PREFIXES) or ASSET_ID_RE.fullmatch(value):
        return "ASSET_ID"
    if SECTION_HEADER_RE.match(value):
        return "SECTION_HEADER"
    if MEMO_LINE_RE.match(value):
        return "MEMO_LINE"
    return "UNKNOWN"


def _starts_with_command(body: str) -> bool:
    """Whether a physical row begins with a known command or conditional."""
    stripped = body.lstrip(WS).lstrip("~.")
    if not stripped:
        return False
    for keyword in ("もし", "違ってももし", "違ったら"):
        if stripped.startswith(keyword):
            return True
    match = re.match(r"[^\s\u3000\"|]+", stripped)
    if not match:
        return False
    name = match.group(0)
    if (name in KNOWN_SCHEMA_COMMANDS or name in EXTRA_COMMANDS
            or name in _project_macro_names()):
        return True
    try:
        return P.is_known_command(name)
    except Exception:
        return False


def _literal_macro_names(lines: Iterable[str]) -> set[str]:
    """Extract exact macro commands; regex/pattern macros remain opaque."""
    names = set()
    for line in lines:
        match = MACRO_DEF_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        if name.startswith("~"):
            name = name[1:]
        if name and re.fullmatch(r"[\w-]+", name):
            names.add(name)
    return names


def _project_macro_names() -> set[str]:
    global _PROJECT_MACRO_NAMES, _PROJECT_MACRO_KEY
    # lvroot resolves the plaintext directory lazily; JP_DIR itself was removed
    # from lvparse when the cache became defered.  Calling the accessor keeps
    # project macros loadable without re-introducing an import-time side effect.
    source_dir = P.jp_dir() if hasattr(P, "jp_dir") else getattr(P, "JP_DIR", None)
    if _PROJECT_MACRO_NAMES is not None and _PROJECT_MACRO_KEY == source_dir:
        return _PROJECT_MACRO_NAMES
    names = set()
    if source_dir and os.path.isdir(source_dir):
        for filename in os.listdir(source_dir):
            if not filename.lower().endswith(".txt"):
                continue
            full = os.path.join(source_dir, filename)
            try:
                with open(full, "r", encoding="utf-8", errors="replace", newline="") as stream:
                    names.update(_literal_macro_names(stream))
            except OSError:
                continue
    _PROJECT_MACRO_NAMES = names
    _PROJECT_MACRO_KEY = source_dir
    return names
