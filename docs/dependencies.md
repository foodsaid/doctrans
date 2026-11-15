# 依赖清单与升级流程

本文件单独列出项目依赖的所有外部软件，以及正常升级和紧急安全升级的做法。

## 1. Python 依赖（随 doctrans 安装）

直接依赖只有三个，声明在 `pyproject.toml`：

| 包 | 用途 | 允许范围 | 已验证版本 | 许可证 |
|---|---|---|---|---|
| PyMuPDF | 读 PDF：书签、原图、封面、成品质检 | `>=1.24,<2` | 1.25.2 | AGPL-3.0 |
| WeasyPrint | HTML → PDF 排版 | `>=62` | 70.0 | BSD-3 |
| Markdown | Markdown → HTML | `>=3.5` | 3.11.2 | BSD-3 |

开发依赖：pytest（测试）、ruff（静态检查）。

**锁定清单**：`requirements.txt`（运行）和 `requirements-dev.txt`（运行 + 开发）把上面三个包连同它们的间接依赖全部钉死到具体版本。CI 用锁定清单安装，所以"测试通过"指的就是这一组版本。两个文件由工具生成，不要手改：

```bash
uv pip compile pyproject.toml --universal --python-version 3.11 -o requirements.txt --no-header
```

```bash
uv pip compile pyproject.toml --extra test --universal --python-version 3.11 -o requirements-dev.txt --no-header
```

PyMuPDF 2.x 是大改版（多出一批重依赖），尚未验证，所以上限设为 `<2`。验证步骤见第 4 节，通过后再放开。

## 2. 外部工具（不随 doctrans 安装，各自独立升级）

| 工具 | 用途 | 已验证版本 | doctrans 用到的接口 |
|---|---|---|---|
| MinerU | 本地解析 PDF | 4.1.3、4.2.2 | `server start/status`、`config get`、`telemetry status`、`parse --pages --tier --wait -o`、`read -f image` |
| Ollama | 本地运行翻译模型 | 0.40.x | OpenAI 兼容接口 `/v1/chat/completions`，参数 `reasoning_effort: "none"` |
| 翻译模型 | 翻译 | qwen3.8:27b | 能按要求输出 JSON 数组即可 |
| 系统库 Pango | WeasyPrint 的排版引擎 | 发行版自带 | — |
| 中文字体 | 排版 | 微软雅黑 / Noto Sans CJK / 苹方 | 常规体 + 粗体 |

推荐把 MinerU 装成独立工具，方便多个项目共用：`uv tool install mineru`，升级 `uv tool upgrade mineru`。

## 3. 自动监控

| 机制 | 做什么 | 频率 |
|---|---|---|
| Dependabot 安全更新 | 依赖出现已知漏洞时自动开修复 PR | 漏洞公布后 |
| Dependabot 版本更新 | Python 依赖和 GitHub Actions 有新版本时开 PR（同类合并成一个） | 每周 |
| CI `audit` 任务 | 用 pip-audit 按锁定清单查已知漏洞 | 每次推送 + 每周 |
| CI `latest-deps` 任务 | 不用锁定清单、装最新版跑测试，提前发现即将到来的不兼容 | 每周 |

## 4. 正常升级（每月或按需）

1. 重新生成两个锁定清单（第 1 节的两条命令）。
2. `uv pip install --python .venv/bin/python -r requirements-dev.txt`，跑 `pytest -q` 和 `ruff check`。
3. 拿一份已翻译完的文档做回归：`doctrans render`，对比质检报告里的页数、书签数、残留标记数。排版依赖升级后页数可能有 ±1% 的变化，属正常。
4. 更新本文件的"已验证版本"，提 PR。

升级 MinerU、Ollama、模型的步骤见操作手册第 7 节。

## 5. 紧急安全升级

目标：从发现到修复版本合入，当天完成。

1. **确认影响**：看 Dependabot 告警或 `uvx pip-audit -r requirements.txt` 的输出，确认是哪个包、哪个修复版本。
2. **只升这一个包**（不顺带升别的，缩小变更面）：

   ```bash
   uv pip compile pyproject.toml --universal --python-version 3.11 -o requirements.txt --no-header --upgrade-package 包名
   ```

   ```bash
   uv pip compile pyproject.toml --extra test --universal --python-version 3.11 -o requirements-dev.txt --no-header --upgrade-package 包名
   ```

3. 本地跑测试，提 PR，标题以 `security:` 开头。CI 全绿即可合并，不必等例行评审排期。
4. 打补丁版本标签（如 `v0.1.1`），发布流程自动生成 Release。
5. 修复版本和 `pyproject.toml` 的允许范围冲突时（比如修复只在新的大版本里）：先放开范围、跑回归；回归不过就在 Release 说明里写明受影响的功能和临时规避办法。

**这个项目的实际暴露面很小**：它只在本机处理使用者自己选的文件，不监听端口，唯一的网络访问是发往本机模型服务的请求。最值得关注的是"打开恶意 PDF 触发解析库漏洞"这一类，对应 PyMuPDF 和 MinerU。

## 6. 许可证

doctrans 以 AGPL-3.0 发布，原因是 PyMuPDF 和 MinerU 都是 AGPL。新增依赖前先确认许可证与 AGPL-3.0 兼容。
