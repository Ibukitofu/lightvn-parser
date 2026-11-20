# lvparse_tool — Light.vn 脚本结构化解析工具

> 把解包后的明文脚本解析成机器可读的结构化字段，分开「可翻译的显示文本」与「不可动的代码」，用于翻译、查找、验证。
>
> 引擎格式：`Data/**/*.mcdat` 是 XOR 加密后的脚本，解密出的明文 `.txt` 与之一一对应。工具解析的是明文；未设置 `LV_JP` 时它可以自动解密（见下文「写盘行为」）。

## 目录

- [一、快速开始](#一快速开始)
- [二、使用说明](#二使用说明)
- [三、验收命令](#三验收命令)
- [四、模块结构](#四模块结构)
- [五、三层验证](#五三层验证)
- [六、主测试语料验证结果](#六主测试语料验证结果)
- [七、多游戏兼容性样本](#七多游戏兼容性样本)
- [八、测试](#八测试)
- [九、已知限制](#九已知限制)
- [十、文件清单](#十文件清单)

---

## 一、快速开始

### 环境变量

| 变量 | 必填 | 作用 |
|---|---|---|
| `LV_GAME` | **必填** | 游戏根目录（含 `Config/Commands.xml` 与 `Data/_/*.mcdat`）。命令表的唯一来源 |
| `LV_JP` | 可选 | 明文脚本目录（`<fid>.txt`）。不设则首次解析时自动解密 `LV_GAME` 的 `.mcdat` 写入 `_cache/`（见下） |
| `LV_LIB` | 可选 | `lvlib.py`（XOR 加解密实现）所在目录。不设则按常见位置自动查找 |

未设置 `LV_GAME` 时，工具会明确报错并给出可操作的提示，不会静默使用空的命令表。

### 写盘行为（请先读）

单独执行 `import lvparse_tool` 不会写盘，也不会修改标准输出。只有一种情况会在首次解析时写盘：

- 项目宏表来自 `jp_dir()`。只设 `LV_GAME`、不设 `LV_JP` 时，`jp_dir()` 会调用 `lvroot._cache_jp()`，把解密后的脚本写进 **包目录下的 `_cache/`**（主游戏约数百 MB）。

只做只读检查时，显式设置 `LV_JP` 即可避免这条路径。

`_cache/` 默认不会被 git 跟踪。若希望完全不写盘，请直接传入已经解包的脚本目录。

### 命令速查

```powershell
# 语料扫描：文件分类 / 脚本数 / 非空行 / 可翻 DISPLAY / 续写
python -m lvparse_tool.lvscan <脚本目录>

# 建索引（产出 5 个文件，含 protected.json）
python -m lvparse_tool.lvindex <脚本目录> -o .\index

# 查询（--index 缺省读包目录下的 _index；--limit 控制条数，默认 20）
python -m lvparse_tool.lvquery --index .\index --speaker 琳          # 按说话人查台词
python -m lvparse_tool.lvquery --index .\index --untranslated        # 仍含假名的显示字段
python -m lvparse_tool.lvquery --index .\index --var スキル効果       # 变量的赋值点与取值
python -m lvparse_tool.lvquery --index .\index --file 66756          # 单个文件的显示字段
python -m lvparse_tool.lvquery --index .\index --role LABEL          # 按角色查结构字段
python -m lvparse_tool.lvquery --index .\index --grep "回復薬"       # 正则搜索显示文本

# 受保护字段（可见但不可翻）单独查
python -c "import json; d=json.load(open(r'.\index\protected.json',encoding='utf-8')); print(d['count'])"

# 三层验证（结构 + 逻辑域）；加 --miss 才跑漏译扫描
python -m lvparse_tool.lvverify --jp <日文> --zh <中文> --miss

# 字段级明细（JSON）：unknown 行细分、受保护赋值、往返一致性
python -m lvparse_tool.audit --scan-dir <脚本目录> > report.json
```

### 索引文件

| 文件 | 内容 | 可翻 |
|---|---|---|
| `display.json` | `DISPLAY` / `DISPLAY_CONTINUATION` / `DISPLAY_INFERRED` / `SPEAKER_NAME` | 是 |
| `dialogue.json` | 按说话人归档的台词 | 是 |
| `struct.json` | 命令名 / 变量名 / 路径 / 标签等结构字段 | 否 |
| `variables.json` | 变量与赋值点 | — |
| `protected.json` | `DISPLAY_UNSAFE`（可见但不可翻），带 `variable` 与 `reasons` | **否** |

每个文件都带 `schema_version` / `source` / `generated_at` / `count` 元信息；
`lvquery` 读入时会校验版本号，旧索引会被要求重建。

### 作为库

```python
from lvparse_tool import lvscan

pf = lvscan.parse_file('66756.txt')
for parsed, field, line_no in pf.fields():   # 含文档级续写片段
    if field.translatable:
        print(line_no, field.role, field.value)
```

`ParsedFile` 还提供 `line_fields()`（仅行级字段）与 `windows()`（对话窗口），`lvscan.iter_files(directory)` 可遍历整个语料并自动跳过非脚本文档。

## 二、使用说明

### 安装

在仓库父目录执行：

```powershell
python -m pip install .\lvparse_tool
```

安装后可以从任意目录导入：

```python
import lvparse_tool
from lvparse_tool import lvscan
```

### 配置要点

解析命令参数需要引擎的 `Config/Commands.xml`，因此 `LV_GAME` 必填；要识别自定义宏，再设置 `LV_JP` 指向解包后的脚本目录。只做只读扫描时建议两个都设，这样不会触发自动解密和缓存写入。

**两个环境变量各自独立**（详见第七节）：命令表来自 `LV_GAME/Config/Commands.xml`，宏表来自 `LV_JP` 的脚本目录。只换其中一个会得到混合结果。

### 常用流程

1. 准备解包后的脚本目录。
2. 设置 `LV_GAME`，必要时再设 `LV_JP` 和 `LV_LIB`。
3. 用 `lvscan` 查看文件分类、显示字段和未解决行。
4. 用 `lvindex` 生成查询索引，`lvquery` 检索。
5. 翻译或替换后，用 `lvverify` 检查结构、逻辑域和漏译。

`lvscan`、`lvquery`、`lvverify` 默认只读，`lvindex` 只写入 `-o` 指定的索引目录，`audit --scan-dir` 只读。
工具不会直接修改游戏的 `.mcdat` 文件。

---

## 三、验收命令

以下命令在 `lvparse_tool/` 的父目录执行，环境变量先设好。

```powershell
$env:LV_GAME='<游戏根目录>'
$env:LV_JP='<明文脚本目录>'
$env:LV_LIB='<lvlib.py 所在目录>'
$env:PYTHONIOENCODING='utf-8'
# 单元测试
python -W ignore -m unittest discover -s lvparse_tool/tests -t .

# 语料扫描：脚本数 / 非空行 / 可翻 DISPLAY / 续写
python -u -X utf8 -m lvparse_tool.lvscan '<明文脚本目录>'

# 三层验证：标签名 / 结构字段 / 逻辑域
python -u -X utf8 -m lvparse_tool.lvverify --jp '<日文目录>' --zh '<中文目录>'

# 加 --miss 才跑漏译扫描（会比上面慢一倍）
python -u -X utf8 -m lvparse_tool.lvverify --jp '<日文目录>' --zh '<中文目录>' --miss

# 各游戏命令表与宏
# 注意：命令表来自 LV_GAME/Config/Commands.xml，宏表来自 LV_JP 的脚本目录。
# 只换其中一个会得到混合结果（见下表）。
$env:LV_GAME='<其他游戏根目录>'
$env:LV_JP='<其他明文脚本目录>'
python -c "import sys; sys.path.insert(0, 'lvparse_tool'); import lvparse, schema; print(len(lvparse.command_table()), len(schema._project_macro_names()))"
```

> 以 `-m` 方式运行子命令时，stderr 会先出现一条 `found in sys.modules` 的 `RuntimeWarning`。
> 这是包入口预导入子模块的已知现象，不影响解析结果。

**统计口径**：`lvscan` 的「行级 DISPLAY」只包含 `DISPLAY`，不包含 `DISPLAY_UNSAFE`。

---

## 四、模块结构

| 模块 | 变更原因 |
|---|---|
| `field_types.py` | 数据结构或词法常量变化 |
| `grammar.py` | 引号/分隔符/令牌形状变化 |
| `schema.py` | 命令表或槽位规则变化 |
| `line_parser.py` | 单行字段分类变化 |
| `documents.py` | 对话窗口/续写判定变化 |
| `inference.py` | 跨语料推断策略变化 |
| `audit.py` | 语料扫描 / CLI 变化 |
| `field_parser.py` | **兼容门面，零逻辑** |

工具层：`lvroot` 目标定位 / `lvparse` 命令表 / `lvscan` 语料扫描 / `lvindex` 索引构建 / `lvquery` 查询 / `lvverify` 三层验证 / `role_report` 变量角色 / `lvctx` 页面上下文

---

## 五、三层验证

### 1. 结构字段保护

`lvverify` 对 28 类结构角色做字节级比对，必须与日文完全一致：

- **引擎字段（18 类）**：`COMMAND` / `VARIABLE_NAME` / `LABEL` / `RESOURCE_PATH` /
  `FILENAME` / `OPTION_FLAG` / `ASSIGN_OPERATOR` / `NUMBER` / `ASSET_ID` /
  `ENGINE_KEYWORD` / `SPEAKER_MARKER` / `PREFIX` / `DIALOGUE_MARKER` /
  `PIPE_SEPARATOR` / `CONDITIONAL_COMMAND` / `FILENAME_OR_LABEL` /
  `ASSET_GLOB` / `OPAQUE_NESTED_CODE`
- **注释与代码字面量（10 类）**：`COMMENT` / `CODE_LITERAL` / `CODE_FRAGMENT` /
  `REGEX_LITERAL` / `EXTERNAL_URL` / `BOOLEAN` / `COMPARE_OPERATOR` /
  `ENUM_KEY` / `RESOURCE_OR_OPTION` / `DOCUMENT_ROLE`

**赋值值与条件是故意排除的**：同一字面量对不同变量可能既是显示文本又是逻辑键，逐字节比对会产生大量误报（实测 8,442 → 3,690 → 28 → 0）。

三处豁免都写在 `lvverify.py` 里，分别对应一个明确规则，便于审查：

- `LINE_WL`：10 个文件允许物理行数不同——译文会插入查找表与守卫行；
- `GUARD`：以 `// zh-` 或 `もし (特性表_ready / 技能名表_ready / lvHashMapHasKey…)` 开头的行不参与比对；
- `LABEL_WL`：`説明_` / `エフェクト_` 前缀的标签不参与字节比对与标签计数。

### 2. 逻辑域一致性

```
变量 X 的值 V 同时满足：
  JP 有赋值 X = "V"  且  JP 有比较 X == "V"
检查 ZH：
  ZH 赋值域已无 V       ← 赋值被翻译了
  但 ZH 比较域仍有 V     ← 比较没翻
  → FAIL（这条分支永远进不去）
```

### 3. 漏译检查（`--miss`）

所有 `translatable=True` 字段（含文档级续写），剥掉 `{{变量}}` 后仍含假名的会被逐条列出。它暴露的是**语料残余**（注音、假名表、疑似乱码、漏翻条目），是翻译收尾的清单，不是解析器缺陷。当前主语料的实测结果见第六节。

---

## 六、主测试语料验证结果

```
Label names:        checked 22,219,             FAIL 0
Structural fields:  checked 115,396 changed lines, FAIL 0
Logic domain:       checked 1,001,              FAIL 0
Total: PASS
```

### 漏译扫描（`--miss`，与上面三层分开跑）

```
Untranslated display text: 124655 translatable fields, 28 still kana
```

该模式下 `Total` 会因这 28 条报 FAIL。残余是注音标签里的假名、假名选择行、疑似乱码行和个别未译条目——正是这条扫描要暴露的对象；完整清单用 `lvverify --json` 输出。

### 无损性

`audit --scan-dir` 全语料实测：`roundtrip_mismatches` 0（序列化重建原文）、
`unclassified_spans` 0（没有字符落在任何字段之外）、`window_uncovered_rows` 0（对话窗口无漏行）。

### 语料分类

```
script_candidate   1090
tiled_map_json       14   ← 非脚本，不产生字段
shader                9
xml_data              1

脚本 1090 / 非空行 528,046
行级 DISPLAY 92,064 / 文档级续写 3,426 / 合计 95,490
```

### 字段口径（重要）

`lvscan` 只统计**可翻译的显示字段**。有两种容易混淆的口径：

| 口径 | 字段 | 数量 | 可翻译 |
|---|---|---:|---|
| 行级 DISPLAY | `DISPLAY` | 92,064 | 是 |
| 文档级续写 | `DISPLAY_CONTINUATION` + `DISPLAY_INFERRED` | 3,426 | 是 |
| 可见但受保护 | `DISPLAY_UNSAFE` | 7,158 | **否** |

**`DISPLAY_UNSAFE` 的准确含义**：赋值所属的**变量**被语料级分析判定为「既参与显示、又参与比较 / 资源路径 / 标签用途」，因此这类赋值不能默认原地翻译。

注意这是**变量级的保守推断**，不是逐值证明：

- 被标记的赋值一定属于一个「有显示引用且另有非显示用途」的变量；
- 但**不保证每一个被标记的赋值值都真的出现在屏幕上**；
- 结论是「不可翻」，不是「已确认上屏」。

`translatable=False`，替换接口也会拒绝它。它以独立片段写进 `protected.json`，带
`variable` 与 `reasons`（`compared` / `resource_or_label`），便于审计但不混入可翻统计。

> `DISPLAY_ROLES` 采用显式集合而不是子串匹配——`'DISPLAY' in role` 会同时命中 `DISPLAY_UNSAFE`。

### 脚本解析未解决行

非脚本文档行（Tiled JSON / shader / xml，共 24 个文件）被扫描器分类后跳过，不算解析缺口。脚本内真正未解决的是 512 行，以作者笔记、章节标题、资源标识符等低风险内容为主；逐类计数用 `audit --scan-dir` 输出的 `unresolved_unknown_categories` 查看。

---

## 七、多游戏兼容性样本

> **冒烟测试，非全量覆盖证明。** Game B 只有 9 个脚本文件，Game C 只有 35 个，
> 相对主测试语料的 1,090 个只是小样本。它证明的是「换游戏后命令表能自获取、
> 解析不崩、无未覆盖字符」，**不能证明**这两个游戏的全部语料都被正确处理。

| 游戏 | 命令签名 | 脚本 | 异常 | 未覆盖 |
|---|---:|---:|---:|---:|
| Game A（主语料） | 419 | 1,090 | 0 | 0 |
| Game B | 405 | 9 | 0 | 0 |
| Game C | 404 | 35 | 0 | 0 |

「异常 / 未覆盖」= `roundtrip_mismatches` / `unclassified_spans`（`audit --scan-dir` 输出）。

命令签名来自各游戏的 `Config/Commands.xml`；`data/engine_keywords.json` 是随包分发的引擎通用关键字表，不含任何游戏内容。

**两个环境变量各自独立**：
- 命令表来自 `LV_GAME/Config/Commands.xml`
- 宏表来自 `LV_JP` 的脚本目录（含 `マクロ "…"` 定义的文件）

只换 `LV_GAME` 会得到「新游戏的命令签名 + 旧游戏的宏」。实测：

```
LV_GAME=<game-b>  LV_JP=<game-b-scripts>  → commands=405  macros=0
LV_GAME=<game-b>  LV_JP=<game-a-scripts>  → commands=405  macros=13   ← 混合结果，不能这样使用
```

---

## 八、测试

```powershell
python -m unittest discover -s lvparse_tool/tests -t . -v
```

```
Ran 43 tests in 4.6s
OK
```

语料相关用例依赖第三节的三个环境变量：未设置时不会全绿（实测 14 errors / 1 skipped——宏用例自动 skip，其余因缺 `LV_GAME` 报 error）；设置后 43 项全部通过。

| 文件 | 测什么 |
|---|---|
| `test_serialize.py` | 真重建：往返、gap、重叠拒绝、过期 span |
| `test_replace_gate.py` | 6 道结构注入拦截 |
| `test_verify.py` | 逻辑域一致性、zh 缺失、空目录 |
| `test_documents.py` | 续写片段、非脚本零输出、块注释 |
| `test_display_caliber.py` | 统计口径守护：`DISPLAY_UNSAFE` 永不混入可翻统计 |
| `test_macro_cache.py` | 宏缓存跨目录切换：两个目录的宏互不串扰 |
| `test_protected_index.py` | 索引必须单独暴露受保护字段，且带变量与原因 |
| `test_review_fixes.py` | 评审回归：宏加载、条件后空格、间接显示可翻、报告服从语料推断、索引含续写 |
| `test_package.py` | 包可导入、import 不改 stdout |
| `test_package_contract.py` | **版本、真包、无导入环、门面全覆盖、惰性全局** |

---

## 九、已知限制

| # | 限制 | 影响 |
|---|---|---|
| 1 | 英文命令名不识别 | `text`/`btnText` 不会产生 `DISPLAY`，需要扩展命令表或规则 |
| 2 | `SCRIPT_DISPLAY_CALL_ARGS` 只 3 条规则 | 跨脚本显示参数靠推断 |
| 3 | `role_report` 按变量统计 | 命令字面量 DISPLAY 无变量 |
| 4 | 块注释只识别独占整行的 `/*` 和 `*/` | 行内 `/* ... */` 会按普通脚本内容解析，不会自动拆成注释字段 |

---

## 十、文件清单

```
lvparse_tool/
├── __init__.py              包入口
├── README.md                本文档
├── pyproject.toml
├── .gitignore
├── field_types.py           ┐
├── grammar.py               │
├── schema.py                │ 解析器七个模块
├── line_parser.py           │
├── documents.py             │
├── inference.py             │
├── audit.py                 ┘
├── field_parser.py          兼容门面
├── lvroot.py                目标定位（惰性解密）
├── lvparse.py               命令表
├── lvscan.py                文档级解析 / 语料扫描
├── lvindex.py               索引构建
├── lvquery.py               查询 CLI
├── lvverify.py              三层验证
├── role_report.py           变量角色
├── lvctx.py                 页面上下文
├── data/
│   └── engine_keywords.json 引擎关键字表
├── reports/                 本地报告输出
└── tests/                   10 个测试文件 · 43 个用例

index-root/                  lvindex -o 的输出示例
├── index/                   日文索引
├── index_zh/                中文索引
└── jp_cache/                解包缓存
```
