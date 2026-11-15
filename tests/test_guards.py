"""守护测试：把项目的隐私承诺写成自动检查。这些测试失败，说明改动破坏了「数据不出本机」。
改这个文件需要代码负责人批准（见 .github/CODEOWNERS）。"""
import ast
import subprocess
from pathlib import Path

import pytest

from doctrans import parse

PACKAGE = Path(parse.__file__).parent
NETWORK_MODULES = {"urllib", "http", "socket", "ssl", "requests", "httpx", "aiohttp", "ftplib", "smtplib", "websockets"}


def imported_modules(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module.split(".")[0]


def test_only_llm_module_may_touch_the_network():
    """唯一允许联网的模块是 llm.py（发往使用者配置的模型服务）。别的模块引入网络库就失败。"""
    offenders = {p.name: sorted(set(imported_modules(p)) & NETWORK_MODULES)
                 for p in PACKAGE.glob("*.py") if p.name != "llm.py"}
    assert not {name: mods for name, mods in offenders.items() if mods}


def test_default_model_endpoint_is_local():
    from doctrans.config import Config
    assert Config(input=Path("."), output=Path(".")).llm_url.startswith("http://localhost:")


def fake_mineru(mode, telemetry):
    def run(cmd, **kwargs):
        out = {"status": "running", "get": f"parse_server.local.mode = {mode}", "telemetry": f"state: {telemetry}"}
        key = "telemetry" if cmd[1] == "telemetry" else cmd[2]
        return subprocess.CompletedProcess(cmd, 0, stdout=out.get(key, ""), stderr="")
    return run


@pytest.mark.parametrize("mode, telemetry", [("remote", "disabled"), ("managed", "enabled"), ("remote", "enabled")])
def test_privacy_check_refuses_remote_mode_or_telemetry(monkeypatch, mode, telemetry):
    monkeypatch.setattr(parse.subprocess, "run", fake_mineru(mode, telemetry))
    with pytest.raises(SystemExit):
        parse.check_local_only("mineru")


def test_privacy_check_passes_when_local_and_silent(monkeypatch):
    monkeypatch.setattr(parse.subprocess, "run", fake_mineru("managed", "disabled"))
    parse.check_local_only("mineru")


def test_parsing_always_runs_the_privacy_check_and_never_goes_remote(monkeypatch, tmp_path):
    """parse_pdf 必须先过隐私检查，传给 MinerU 的命令里不能出现远程解析参数。"""
    calls = []

    def run(cmd, **kwargs):
        calls.append([str(c) for c in cmd])
        if cmd[1] == "parse":
            Path(cmd[cmd.index("-o") + 1]).write_text("text", encoding="utf-8")
        return fake_mineru("managed", "disabled")(cmd, **kwargs)

    monkeypatch.setattr(parse.subprocess, "run", run)
    cfg = type("Cfg", (), {"output": tmp_path, "input": tmp_path / "x.pdf", "mineru": "mineru"})()
    parse.parse_pdf(cfg, "1-2")
    parse_at = next(i for i, c in enumerate(calls) if c[1] == "parse")
    assert any(c[1:3] == ["config", "get"] for c in calls[:parse_at])       # 解析之前查过本地模式
    assert any(c[1:3] == ["telemetry", "status"] for c in calls[:parse_at])  # 解析之前查过遥测
    assert not any("remote" in arg for c in calls for arg in c)

    monkeypatch.setattr(parse.subprocess, "run", fake_mineru("remote", "disabled"))
    with pytest.raises(SystemExit):
        parse.parse_pdf(cfg, "3-4")                                          # 模式不对时不解析
    assert not (tmp_path / "source_3-4.md").exists()
