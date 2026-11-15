# 参与贡献

doctrans 是为本地、离线处理私人文档而做的。欢迎改进，但有几条不能让步的规则。

## 不可变的原则

1. **数据不出本机。** 不新增任何网络访问；不加遥测、统计、自动更新检查。
2. **仓库里没有真实文档。** 不提交任何书、手册、译文、术语表、配置、截图。测试只用脚本生成的合成样本和自己编写的文字。
3. **隐私检查不能绕过。** `check_local_only` 及其调用点不能删、不能加跳过开关。

违反这三条的 PR 不会合并，无论功能多有用。

## 代码分层：哪些可以自由改，哪些要先讨论

| 层 | 文件 | 规则 |
|---|---|---|
| 框架 | `pipeline.py`、`config.py`、`cli.py`、`parse.py`、`llm.py`、`translate.py` 的缓存与重试 | 改动前先开 Issue 讨论设计。需要代码负责人批准 |
| 规则 | `structure.py`、`figures.py`、`inspect_pdf.py`、`glossary.py`、`qa.py` | 欢迎直接提 PR。每条新规则必须带一个合成测试，并保证已有测试不变 |
| 表现 | `book.css`、`render.py`、提示词文本 | 欢迎直接提 PR。附改动前后的截图（合成文档） |
| 数据表 | `inspect_pdf.py` 里的语言表、`render.py` 里的字体候选 | 最容易上手的贡献：加一种语言、一个平台的字体路径 |

配置文件的字段和缓存文件的格式属于对外接口：只能新增带默认值的字段，不能改名或改变已有字段的含义。

## 提交前

```bash
git config core.hooksPath .githooks     # 启用本地防泄露钩子（克隆后做一次）
```

```bash
uv pip install --python .venv/bin/python -r requirements-dev.txt && uv pip install --python .venv/bin/python --no-deps -e .
```

```bash
.venv/bin/ruff check && .venv/bin/pytest -q
```

## PR 要求

- 一个 PR 做一件事。说明"遇到了什么样的文档结构、现在怎么处理"，用结构描述代替原文内容。
- 新的切段或排版规则：先写一个会失败的合成测试，再改代码。
- 不能让已有文档的翻译缓存大面积失效。切段结果变了，缓存键就变了，使用者要重新翻译几小时。确实需要改时，把转换放到翻译之后做（参考 `structure.listify`）。
- CI 必须全绿：防泄露检查、静态检查、三个 Python 版本的测试、依赖漏洞检查。
- 改依赖：按 [docs/dependencies.md](docs/dependencies.md) 重新生成锁定清单，单独一个 PR。

## 许可证

贡献的代码以 AGPL-3.0 发布。
