# doctrans 操作手册

本手册可离线阅读，覆盖安装、日常操作、排查、升级、迁移。

**所有命令都在 Linux / WSL2 终端里执行，不能在 PowerShell 或 CMD 里执行**（MinerU 和 doctrans 装在 Linux 一侧）。Windows 上先打开 WSL 终端。

**手册里的路径是示例，要换成你机器上的实际路径。** 先设两个变量，后面的命令都用它们：

```bash
export MINERU_BIN=~/.local/bin              # MinerU 可执行文件所在目录（uv tool 安装的默认位置）
```

```bash
export DOCTRANS=~/doctrans                  # doctrans 仓库目录
```

不知道 MinerU 装在哪：看任意一份文档配置里 `[mineru] bin = "..."` 那一行，或运行 `doctrans doctor configs/某文档.toml`，第一行括号里就是。变量只在当前终端有效，新开终端要重新设。

## 1. 这套流程做什么

把外文 PDF（书、手册）翻译成中文，并按原书版式重新排版。分三步，全部在本机完成：

| 步骤 | 工具 | 做什么 | 运行位置 |
|---|---|---|---|
| 解析 | MinerU（本地模式） | PDF → Markdown + 图片 | 本机，模型在 `~/.mineru/models` |
| 翻译 | Ollama + 本地大模型 | 逐段翻译，带术语表 | 本机，`localhost:11434` |
| 排版 | WeasyPrint | Markdown → PDF | 本机 |

**文档内容不出本机。** 只有三件事需要联网：第一次安装软件、下载模型、以后升级。装好之后拔掉网线也能完整跑。

### MinerU 用的是本地的吗

是。MinerU 有两种解析方式：本地（`managed`）和远程（官方云服务 mineru.net）。本流程只用本地：

- 配置锁定为 `parse_server.local.mode = managed`，遥测关闭。
- 每次解析前 doctrans 都会检查这两项，任何一项不对就拒绝运行。
- 代码里从不传 `--remote` 参数。

自己核对：

```bash
$MINERU_BIN/mineru config get parse_server.local.mode
```

```bash
$MINERU_BIN/mineru telemetry status
```

第一条应显示 `managed`，第二条应显示 `state: disabled`、`last_flush_at: never`。

离线实测方法（可选，证明解析不联网）：在无网络的沙箱里启动服务并解析一份新 PDF。

```bash
unshare -rn bash -c "ip link set lo up; $MINERU_BIN/mineru server start; sleep 15; $MINERU_BIN/mineru parse 某文件.pdf --pages 1-2 --tier standard -o /tmp/out.md; $MINERU_BIN/mineru server stop"
```

## 2. 目录约定

代码和数据分开放。代码仓库里永远不放文档、配置、术语表、输出。

```
~/doctrans/              代码仓库（可以推到 GitHub）
~/doctrans-data/         数据工作区（不进任何仓库）
  inbox/                 原文 PDF
  configs/               每份文档一个 .toml
  glossary/<文档名>/      术语表 CSV
  work/<文档名>/          输出和缓存
```

`work/<文档名>/` 里的文件：

| 文件 | 内容 | 能否删除 |
|---|---|---|
| `zh.pdf` / `zh.html` | 纯中文版 | 可重新生成 |
| `bi.pdf` / `bi.html` | 原文 + 中文逐段对照版 | 可重新生成 |
| `zh.md` | Markdown 译文 | 可重新生成 |
| `qa/report.md` | 质检报告和抽样页截图 | 可重新生成 |
| `source_*.md` | MinerU 解析结果（缓存） | 删了要重新解析 |
| `translate_cache.jsonl` | 逐段译文（缓存） | **不要删**，删了要重新翻译几小时 |
| `images/`、`figs/` | 图片 | 删了要重新导出 |
| `run.log` | 运行日志 | 可删 |

## 3. 首次安装（需要联网一次）

### 3.1 doctrans

```bash
git clone <仓库地址> ~/doctrans && cd ~/doctrans
```

```bash
git config core.hooksPath .githooks
```

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[test]"
```

### 3.2 MinerU（装成独立工具，多个项目可以共用）

```bash
uv tool install --python 3.12 mineru
```

它有自己的隔离环境，命令出现在 `~/.local/bin`（`mineru`、`mineru-kit` 等），模型和配置在 `~/.mineru`。

锁定本地模式、关闭遥测、下载模型（约 2 GB）：

```bash
$MINERU_BIN/mineru server start
```

```bash
$MINERU_BIN/mineru config set parse_server.local.mode managed
```

```bash
$MINERU_BIN/mineru telemetry disable
```

```bash
$MINERU_BIN/mineru-kit models download --tier standard
```

```bash
$MINERU_BIN/mineru-kit models verify
```

`~/.local/bin` 在 PATH 里时，配置里不用写 `[mineru]`；否则用 `[mineru] bin = "/home/你/.local/bin/mineru"` 写绝对路径（后台任务、定时任务里 PATH 可能不全，写绝对路径最稳）。

### 3.3 Ollama 和翻译模型

从 ollama.com 安装 Ollama（Windows、macOS、Linux 均可；WSL 里可以直接访问 Windows 上的 Ollama）。然后下载模型：

```bash
ollama pull qwen3.8:27b
```

27B 级模型需要约 16 GB 显存。显存小就换小一档的模型，并在配置的 `[llm] model` 里改名字。

### 3.4 字体

- WSL / Windows：自动使用微软雅黑（`msyh.ttc` 和粗体 `msyhbd.ttc`）。
- macOS / Linux：回退到苹方、Noto Sans CJK 等；也可以在配置 `[render]` 里用 `font_regular`、`font_bold` 指定字体文件。**必须同时给出粗体文件**，否则粗体不显示。
- macOS 需要先 `brew install pango`。

### 3.5 检查

```bash
$DOCTRANS/.venv/bin/doctrans doctor configs/某文档.toml
```

四项都打勾才算装好：MinerU 本地模式、模型服务、字体、提交检查。

## 4. 日常操作：翻译一份新文档

以下命令在数据工作区（`~/doctrans-data`）里执行，`doctrans` 指 `$DOCTRANS/.venv/bin/doctrans`。

### 第 1 步：放文件，起短名

把 PDF 放进 `inbox/`。文件名长或带空格时建一个短名链接，短名会成为配置名和输出目录名：

```bash
ln -s "很长的原始文件名.pdf" inbox/mybook.pdf
```

### 第 2 步：体检，生成配置草稿

```bash
doctrans inspect inbox/mybook.pdf
```

它会判断语言、页码范围（跳过原目录和索引）、章节词、标题定级方式，写出 `configs/mybook.toml`。**打开配置逐项核对**，重点是 `pages`：

- 原目录页、索引页要去掉（译本会自动生成中文目录）。
- 广告页、空白页去掉。
- 填上 `domain`（书的主题，一句英文，帮助模型选术语）。
- 需要时加上 `[mineru] bin = "..."`（见 3.2）。
- 界面名称怎么处理：`ui_labels`（见第 5 节）。操作手册类文档建议用 `both`。

### 第 3 步：术语表（可选，强烈建议）

有书后索引时，从索引自动生成：

```bash
doctrans glossary configs/mybook.toml 464-476 -o glossary/mybook/index.csv
```

核心术语可以手写一份 `glossary/mybook/manual.csv`（列 `source,target,tgt_lng`，UTF-8 带 BOM）。文件名排序在前的优先。同一领域的书可以共用术语表：在配置的 `glossaries` 里多列一个路径。

### 第 4 步：先试一章

把配置里的 `pages` 临时改成一章的范围，运行：

```bash
doctrans run configs/mybook.toml
```

看 `work/mybook/zh.pdf` 和 `qa/report.md`。重点看：标题层级对不对、列表和代码块是否正常、术语是否符合预期。满意后把 `pages` 改回全书。

### 第 5 步：跑全书

长任务放后台，关掉终端也不会断：

```bash
setsid nohup doctrans run configs/mybook.toml > work/mybook/batch.log 2>&1 < /dev/null &
```

看进度：

```bash
tail -3 work/mybook/batch.log
```

批量跑多份：`doctrans run configs/*.toml`，逐份排队，一份失败不影响其它。

**中断了怎么办**：重新执行同一条命令。解析结果、图片、每一段译文都有缓存，会从断点续上。

**速度参考**（RTX 4080 16 GB，27B 模型）：解析每百页约 5–6 分钟；翻译每千段约 30–35 分钟；排版 1–3 分钟。一本 1000 页的书约 6–7 小时。

**跑的时候电脑不能睡眠**，Ollama 要一直开着。

### 第 6 步：看质检报告

`work/mybook/qa/report.md` 有四部分：

| 部分 | 含义 | 怎么处理 |
|---|---|---|
| 残留标记 | 成品里露出了 `####`、`<table>`、`**` 等排版符号，列出页码 | 翻到那几页看。表格单元格里的项目符号、代码里的 `#` 注释属于正常 |
| 疑似漏译 | 英文字母多、中文很少的段落 | 多数是路径、命令、界面名称，属于正常；整段英文正文才是真漏译 |
| 术语偏差 | 术语表里的词，译文没按要求翻 | 偏差大时检查术语表是否合适，改后删掉对应缓存行重跑 |
| 抽样页 | 均匀抽 8 页的截图 | 目视检查版式 |

### 只改版式，不重新翻译

改了字体、样式或代码后，只重排版（1–3 分钟，不调用模型）：

```bash
doctrans render configs/mybook.toml
```

### 重新翻译某几段

译文按"原文段落的哈希"缓存在 `translate_cache.jsonl`，一行一段。想让某段重新翻译：用译文里的几个字找到那一行（`grep -n "译文片段" translate_cache.jsonl`），删掉它，再 `doctrans run`。想整本重新翻译（比如换了模型或大改了术语表）：把这个文件改名备份，再运行。

## 5. 配置文件字段

```toml
input = "../inbox/mybook.pdf"
output = "../work/mybook"
pages = "1,3-4,14-462"        # 逗号分隔多个范围
source_lang = "English"        # 写进提示词
domain = "ERP software"        # 书的主题
ui_labels = "auto"             # 界面名称（按钮、选项卡、字段名），见下
glossaries = ["../glossary/mybook/*.csv"]

[structure]
chapter_words = ["Chapter", "Appendix"]   # 章标题的词；章名直接以编号开头时写 []
figure_word = "Figure"                    # 原文图注词
headings = "numbers"                      # numbers 或 bookmarks，见下

[llm]
url = "http://localhost:11434/v1/chat/completions"
model = "qwen3.8:27b"
batch = 8          # 每次请求的段数
parallel = 4       # 并发请求数

[mineru]
bin = "/home/你/.local/bin/mineru"

[render]
bilingual = true   # 是否另出对照版
```

`ui_labels` 怎么选：

| 取值 | 效果 | 适合 |
|---|---|---|
| `auto` | 由模型决定，外文界面名称多数保留原文 | 只读不操作的书 |
| `translate` | 译成中文：「常规设置」 | 使用中文界面 |
| `both` | 中文后括号带原文：「常规设置 (General Settings)」 | 操作手册；中英文界面都要能对上 |

模型给的译名不一定和软件中文界面的实际叫法一致，所以操作类文档推荐 `both`。改了这个选项后重跑 `doctrans run`：只会重新翻译那些还留着纯外文界面名称的段落，其余段落继续用缓存。

`headings` 怎么选（`inspect` 会自动判断，一般不用改）：

- `numbers`：小节带编号（3.1、3.1.1）。按编号定标题层级。
- `bookmarks`：小节不带编号，或章名直接以编号开头。按 PDF 自带的书签定层级。PDF 没有书签时不能用这个模式。

## 6. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `连不上模型服务` | Ollama 没启动 | 启动 Ollama 后重跑，已翻译的段落都在缓存里 |
| `模型服务返回 404` | 配置里的模型名没下载 | `ollama list` 核对名字，或 `ollama pull` |
| `MinerU 未锁定为本地模式` | 设置被改动 | 按提示执行两条命令。不要绕过这项检查 |
| `Local parse-server is not ready` | MinerU 服务刚启动 | doctrans 会自动等待重试；手动用 MinerU 时等十几秒 |
| 日志里 `解析失败…重试`、`格式不符…重试` | 模型偶发输出格式错误 | 正常，自动重试。出现 `翻译失败` 才需要看 |
| 日志里 `逐段回退` | 一批连续三次失败，改成一段一段翻 | 正常，只是那一批慢一些 |
| 翻译异常慢（一批几分钟） | 模型开了思考模式，或显存被别的程序占用 | doctrans 已强制关闭思考；检查是否有别的程序占用显卡 |
| 粗体不显示 | 字体缺粗体文件 | 配置 `[render] font_bold` |
| 中文术语表在 Excel 里乱码 | CSV 没带 BOM | 另存为"UTF-8 带 BOM" |
| 标题层级乱 | `headings` 模式不对，或书签不全 | 换模式；看 `inspect` 输出的书签条数 |
| 一大片正文变成等宽字体 | 代码围栏没闭合 | 质检报告"残留标记"会报出页码；把那一页的情况反馈给维护者 |
| 工作目录里冒出 `blobs/` 文件夹 | MinerU 服务把解析过的文件副本存在"启动它时的当前目录" | doctrans 会从 `~/.mineru` 启动服务，副本集中在 `~/.mineru/blobs`。手动启动服务时先 `cd ~/.mineru`。散落的 `blobs/` 可以删除 |
| 进程被误杀 | 用了 `pkill -f doctrans` | 它会把当前终端一起杀掉。用 `pgrep -f "doctrans run"` 找到进程号再 `kill` |

## 7. 升级

原则：**一次只升级一个组件，升级前记下版本，升级后做同一套验证，不对就回退。** 所有升级都需要联网。

### 7.1 记下当前版本

```bash
$MINERU_BIN/mineru version; ollama --version; uv pip list --python $DOCTRANS/.venv/bin/python | grep -iE "pymupdf|weasyprint|markdown"
```

### 7.2 升级后的统一验证

```bash
cd $DOCTRANS && .venv/bin/pytest -q
```

```bash
doctrans doctor configs/某文档.toml
```

再拿一份已经跑完的文档做回归：只重排版，对比质检报告里的页数、书签数、漏译数、残留标记数是否和升级前一致。

```bash
doctrans render configs/某文档.toml
```

升级 MinerU 或换翻译模型后，还要试跑一章新内容（第 4 步），因为 `render` 只验证排版，不验证解析和翻译。

### 7.3 升级 doctrans 本身

```bash
cd $DOCTRANS && git pull && uv pip install --python .venv/bin/python -e ".[test]"
```

回退：`git log --oneline` 找到之前的提交，`git checkout <提交号>`。

### 7.4 升级 MinerU

先记下当前版本，回退时用：

```bash
$MINERU_BIN/mineru version
```

停服务、升级（用 `uv tool` 安装的）：

```bash
$MINERU_BIN/mineru server stop
```

```bash
uv tool upgrade mineru
```

装在普通虚拟环境里的，把第二条换成 `uv pip install --python 虚拟环境/bin/python -U mineru`。

升级后必须重新确认三件事（新版本可能改默认值或需要新模型）：

```bash
$MINERU_BIN/mineru server start && $MINERU_BIN/mineru config get parse_server.local.mode && $MINERU_BIN/mineru telemetry status
```

```bash
$MINERU_BIN/mineru-kit models verify
```

`verify` 报缺模型时重新下载：`mineru-kit models download --tier standard`。

注意事项：

- MinerU 的命令行在大版本之间变化很大（本流程基于 4.x）。跨大版本升级前先看发布说明；doctrans 用到的命令只有 `server start/status`、`config get`、`telemetry status`、`parse --pages --tier --wait -o`、`read -f image`。
- 新版本的解析结果会和旧的略有不同。已有文档的 `source_*.md` 是缓存，不会自动重新解析；想用新版本重新解析，删掉这些文件（译文缓存按段落内容匹配，没变的段落不会重新翻译）。
- 回退：`uv tool install --force --python 3.12 mineru==旧版本号`。
- 小版本升级（如 4.1 → 4.2）实测：隐私设置保留、模型不用重新下载、解析结构不变，整个过程几分钟。

### 7.5 升级 Ollama 和翻译模型

- Ollama 程序：用它自己的更新功能或重新安装。模型文件不受影响。
- 模型：`ollama pull 模型名` 会更新到该名字下的最新版本。
- **换模型或模型更新后，新旧译文的风格和术语可能不一致。** 同一本书不要中途换模型；要换就把 `translate_cache.jsonl` 改名备份后整本重跑。
- 换一个不同的模型：先 `ollama pull`，再改配置 `[llm] model`，试跑一章对比质量。

### 7.6 升级 Python 依赖（PyMuPDF、WeasyPrint、Markdown）

```bash
uv pip install --python $DOCTRANS/.venv/bin/python -U pymupdf weasyprint markdown
```

排版依赖升级后版式可能有细微变化（分页、行距），用 7.2 的回归对比页数。回退：安装时指定旧版本号，如 `weasyprint==70.0`。

## 8. 完全离线使用和迁移到另一台机器

装好之后日常使用不需要网络。要把整套环境搬到一台**不能联网**的机器，需要在能联网的机器上准备好这些东西带过去：

| 内容 | 位置 | 大小参考 |
|---|---|---|
| MinerU 模型 | `~/.mineru/models/` 整个目录 | 约 2 GB |
| MinerU 配置 | `~/.mineru/config.yaml` | 很小 |
| Ollama 模型 | Ollama 的模型目录（环境变量 `OLLAMA_MODELS`，默认 `~/.ollama/models`） | 27B 模型约 18 GB |
| Ollama 安装包 | 官网下载 | — |
| doctrans 代码 | `~/doctrans`（不含 `.venv`） | 很小 |
| Python 包 | 见下 | 约 1 GB |
| 中文字体 | 常规体 + 粗体各一个文件 | — |
| 数据工作区 | `~/doctrans-data` | 视文档而定 |

Python 包：虚拟环境不能直接拷贝（里面写死了路径）。在联网机器上把安装包下载到一个目录，带到离线机器上安装。两台机器的操作系统和 Python 版本要一致。

```bash
pip download -d wheels/ mineru pymupdf weasyprint markdown pytest
```

```bash
uv pip install --python .venv/bin/python --no-index --find-links wheels/ -e ".[test]"
```

模型目录拷到相同位置后，用 `mineru-kit models verify` 确认完整，再跑 `doctrans doctor`。

> 说明：上面"离线迁移 Python 包"这两条是 pip / uv 的标准用法，编写本手册时没有在离线机器上完整演练过。第一次做时请预留排查时间。其余命令都在实际环境中执行过。

## 9. 备份什么

| 必须备份 | 原因 |
|---|---|
| `configs/`、`glossary/` | 手工核对过的配置和术语 |
| `work/*/translate_cache.jsonl` | 几小时的翻译成果 |
| 成品 `zh.pdf`、`bi.pdf`、`zh.md` | 最终交付物 |

`source_*.md`、`images/` 可以重新生成（解析需要半小时级别的时间），空间够就一起备份。模型和软件可以重新下载，不必备份，除非要离线迁移。

## 10. 数据安全

- 仓库 `.gitignore` 是白名单：默认忽略一切，只放行代码和文档。
- 提交前检查（`.githooks/pre-commit`）拒绝 PDF、Office 文件、图片、缓存、大文件，以及 `examples/` 以外的配置和术语表。新克隆的仓库要执行一次 `git config core.hooksPath .githooks` 才生效。
- `.git/info/denylist`（不入库）：每行一个敏感词（书名、作者、客户名），提交内容命中就拒绝。匹配不区分大小写，短词会误伤代码，尽量写全名或词组。
- 只翻译你有权使用的文档。带他人水印的副本、来源不明的版权书不要处理。

### 自动检查（CI）

每次推送到 GitHub，`.github/workflows/ci.yml` 会自动跑两项，结果在仓库的 Actions 页看：

| 检查 | 内容 |
|---|---|
| 防泄露 | `.githooks/check-tree` 扫描所有已入库文件：文档、图片、缓存、大文件、`examples/` 以外的配置和术语表一律拒绝 |
| 测试 | Python 3.11 / 3.12 / 3.13 下跑全部测试，包括用合成 PDF 和模拟模型走完整流程，并对成品做"残留标记"质检 |

另外每周一自动跑一次，依赖出了新版本导致的问题能及早发现。

CI 里**不会也不能**跑真实文档：那需要把文档传到 GitHub 的机器上，而且那里没有显卡。真实文档的质检报告只在本机生成。

可选：把敏感词表放进仓库 Secret（名字 `DENYLIST`，每行一个词），CI 会多做一遍敏感词扫描，日志只显示命中的文件和行号。注意这等于把这些词（书名、作者名等）交给 GitHub 保管，是否这样做由你决定；不设置时这一步自动跳过。

本机手动跑同样的全库检查：

```bash
cd $DOCTRANS && .githooks/check-tree
```

## 11. 已知局限

维护约定：这里只列**当前确实存在**的局限。某条被修复后，先用一份受影响的文档验证，再从这里删掉，并在提交说明里写明。升级 MinerU 后也顺带复查与解析有关的几条。

- **截图里的文字不翻译**，保持原文。
- **页码和原书不对应**；正文里"参见第 N 页"指的是原书页码。
- **表格**：跨页的表格会被拆成两张；截图偶尔被识别成表格（工具会按图注换回原图）。重要的数据表格请对照原文核对。
- **代码块不翻译**，代码里的注释保持原文。
- **标题识别**依赖编号或书签。既没有编号也没有书签的 PDF，标题层级需要人工调整或扩展 `structure.py`。
- **扫描件**会走 OCR，速度慢、错误多，先抽查识别质量。
- 只处理 PDF。Word / PowerPoint / Excel 应直接改原文件里的文字，本工具不处理。
