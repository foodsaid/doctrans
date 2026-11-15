# doctrans

本地批量把长篇外文 PDF（书、手册）翻译成中文，并按原书版式重新排版。全程离线：本地 MinerU 解析，本地模型（Ollama 等 OpenAI 兼容接口）翻译，WeasyPrint 排版。

输出（每份文档一个目录）：

| 文件 | 内容 |
|---|---|
| `zh.pdf` | 纯中文版：原书开本、带页码的中文目录、章/节/小节三级书签、原书嵌入图 |
| `bi.pdf` | 逐段对照版（原文灰色在上，中文在下） |
| `zh.md` | Markdown 译文，可直接放进知识库 |
| `qa/report.md` | 质检：残留排版标记、疑似漏译、术语偏差、页数和书签，以及抽样页截图 |

## 数据不入库

代码仓库只放通用代码。原文、配置、术语表、缓存、输出都放在**仓库之外的数据工作区**：

```
~/doctrans-data/
  inbox/      原文 PDF
  configs/    每份文档一个 .toml（doctrans inspect 生成草稿）
  glossary/   术语表 CSV
  work/       输出和缓存
```

仓库自带三道防线：

1. `.gitignore` 白名单：默认忽略一切，只放行代码目录。
2. 提交前检查（`.githooks/pre-commit`）：拒绝 PDF、Office 文档、图片、缓存、超过 300KB 的文件，以及 `examples/` 以外的配置和术语表。
3. `.git/info/denylist`（不入库）：每行一个敏感字符串（书名、作者、客户名等），提交内容命中就拒绝。

另外，MinerU 未锁定为本地模式或未关闭遥测时，解析步骤会直接拒绝运行。

## 安装（Linux / WSL2；macOS 同理）

```bash
git clone <本仓库> && cd doctrans
git config core.hooksPath .githooks
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[test]"
```

- **MinerU 4.x** 装在独立虚拟环境（依赖重），然后锁定本地模式：
  `mineru config set parse_server.local.mode managed`、`mineru telemetry disable`、`mineru-kit models download --tier standard`。
  配置里 `[mineru] bin` 指向它的可执行文件。
- **模型服务**：Ollama（Windows/macOS/Linux 均可），推荐 27B 级模型。程序会关闭思考模式。
- **字体**：WSL/Windows 自动用微软雅黑（按文件声明，粗体用 `msyhbd.ttc`）；macOS/Linux 回退到苹方、Noto Sans CJK 等字体族名，也可在配置里指定字体文件。
- macOS 需先 `brew install pango`（WeasyPrint 依赖）。

检查环境：`doctrans doctor configs/xxx.toml`

## 使用

```bash
cd ~/doctrans-data
doctrans inspect inbox/*.pdf                       # 1. 体检，生成 configs/<名>.toml 草稿
#    核对草稿：页码范围（原目录、索引、简明目录已跳过）、domain、章节词
doctrans glossary configs/xxx.toml 1035-1052 -o glossary/xxx/index.csv   # 2. 可选：从书后索引生成术语表
#    另建 glossary/xxx/manual.csv 写核心术语（文件名排序在前的优先）
doctrans run configs/xxx.toml                      # 3. 先把 pages 改成一章试跑，满意后改回全书
doctrans run configs/*.toml                        # 4. 批量：逐份排队，一份失败不影响其它
doctrans render configs/xxx.toml                   # 改了样式后只重排版（约 1–2 分钟，不调模型）
```

长任务放后台：`setsid nohup doctrans run configs/*.toml > batch.log 2>&1 &`。中断后重跑同一命令即可续上（解析结果、图片、逐段译文都有缓存）。

配置字段见 [`examples/example.toml`](examples/example.toml)；术语表格式见 [`examples/glossary_example.csv`](examples/glossary_example.csv)（列 `source,target,tgt_lng`，UTF-8 带 BOM）。

完整的安装、排查、升级、离线迁移说明见 [操作手册](docs/manual.md)。

## 已知局限

- 截图里的界面文字保持原文；页码与原书不对应。
- 标题层级靠编号（`3.1`、`3.1.1`）或 PDF 书签确定。两者都没有的 PDF 需要扩展 `structure.py`。
- 代码块原样保留、不翻译；表格识别偶有缺漏，数据表格请对照原文。
- 只处理 PDF。DOCX/PPTX/XLSX 应直接改原文件中的文字（python-docx、python-pptx、openpyxl），计划另做。

## 规模参考

约 1000 页的书（RTX 4080 16GB，27B 模型）：解析约半小时，翻译约 6 小时，排版约 1.5 分钟。

## 许可证

AGPL-3.0（依赖的 PyMuPDF、MinerU 为 AGPL）。
