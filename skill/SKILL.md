---
name: doc-translate
description: 用本地模型把长篇外文 PDF（书、手册）批量翻译成中文，并按原书版式排成 PDF/Markdown（doctrans 工具）。当用户要翻译新的 PDF 文档、做中外对照版，或要求"按之前的流程再来一份"时使用。
---

# 长文档本地翻译（doctrans）

工具仓库在 `/home/b/doctrans`（已装成命令 `doctrans`，可编辑安装，运行的就是仓库里的当前代码），用法见其 README，排查和升级见 `docs/manual.md`。
数据放在仓库外的工作区（本机是 `~/doctrans-data`）：inbox/、configs/、glossary/、work/。**任何数据都不要放进仓库。**

## 流程

1. `doctrans doctor` 检查环境：MinerU 本地模式且遥测已关、模型服务在线、字体可用。
2. `doctrans inspect inbox/x.pdf` 生成配置草稿。核对以下几项：
   - 页码范围：原目录、索引、「简明目录/概览」页都要去掉。
   - `domain`。
   - 章节词和图注词（英文书是 Chapter/Appendix、Figure）。
3. 术语表：
   - 手写核心术语，放在 `glossary/x/manual.csv`。
   - 有书后索引时，用 `doctrans glossary configs/x.toml <索引页> -o glossary/x/index.csv` 生成。
4. 先把 `pages` 改成一章试跑 `doctrans run`，让用户确认译文和版式，再跑全书（后台运行，可断点续跑）。
5. 看 `work/x/qa/report.md`：残留标记（成品里露出的 `####`、`<table>` 等，按页核对）、疑似漏译、术语偏差、抽样页截图。改样式后用 `doctrans render` 重排版，不调模型。

## 坑

- 本地模型必须关闭思考模式（工具已处理）。如果给 BabelDOC 等第三方工具用，要经代理强制关闭。
- 术语表：
  - 用 UTF-8 带 BOM 保存，否则 Excel 打开中文乱码。
  - 语言代码必须与工具完全一致，否则会被静默跳过。
  - 屈折语言的复数/变格形式要各写一行。
- MinerU：
  - 绝不加 `--remote`。
  - 它给的标题层级不可信，工具按编号重定。
  - 它常把截图识别成表格，工具已按图注换回原图。
- 长任务期间电脑不能睡眠，模型服务要保持开启。不要用 `pkill -f`，它会把调用它的 shell 也杀掉。
- 日志里的 `解析失败…重试` 是模型偶发 JSON 格式错误后的自动重试，属正常现象。出现 `逐段回退` 或 `翻译失败` 时才需要查看。
- 有文字层的 PDF 不需要 OCR；扫描件会走 OCR，务必先抽查识别质量。
- 小节没有「3.1」式编号的书（部分英文出版社）：`headings = "bookmarks"`，按 PDF 书签定级（inspect 会自动判断）。
- 技术书的代码：工具把跨页拆开的代码并回代码块、不送模型翻译。看抽样页确认代码按等宽块显示。
