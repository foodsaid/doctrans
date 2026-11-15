"""命令行入口：
  doctrans inspect  <pdf>...                 体检并生成配置草稿（默认写到 ./configs/）
  doctrans glossary <配置> <索引起-止页> -o 输出.csv    从书后索引生成术语表
  doctrans run      <配置>...                 批量执行（逐份排队，一份失败不影响后面的）
  doctrans render   <配置>...                 只用缓存重新排版，不调模型
  doctrans doctor   [配置]                    检查 MinerU 本地模式、遥测、模型服务、字体
"""
import argparse
import subprocess
import sys
import traceback
from pathlib import Path

from . import config


def cmd_inspect(args):
    from .inspect_pdf import inspect
    for pdf in args.pdf:
        inspect(pdf, args.configs)


def cmd_glossary(args):
    from .glossary import build
    cfg = config.load(args.config)
    first, last = (int(x) for x in args.pages.split("-"))
    build(cfg, first, last, Path(args.output).resolve())


def cmd_run(args, offline=False):
    from .llm import ModelUnavailable
    from .pipeline import run
    failed = []
    for path in args.config:
        try:
            run(config.load(path), offline=offline)
        except ModelUnavailable as e:
            print(f"[{Path(path).stem}] {e}")
            failed.append(path)
        except Exception:
            traceback.print_exc()
            failed.append(path)
    if failed:
        print("失败: " + ", ".join(failed))
        sys.exit(1)


def cmd_doctor(args):
    from .llm import list_models
    from .parse import check_local_only
    from .render import font_faces
    cfg = config.load(args.config) if args.config else config.Config(input=Path("."), output=Path("."))
    ok = True
    try:
        check_local_only(cfg.mineru)
        print(f"MinerU   本地模式、遥测已关  ✓ ({cfg.mineru})")
    except (SystemExit, FileNotFoundError) as e:
        print(f"MinerU   ✗ {e}")
        ok = False
    try:
        models_url, names = list_models(cfg.llm_url)
        mark = "✓" if cfg.model in names else f"✗ 未找到 {cfg.model}，现有 {names}"
        print(f"模型服务 {models_url} {mark}")
        ok &= cfg.model in names
    except OSError as e:
        print(f"模型服务 ✗ {e}")
        ok = False
    faces = font_faces(cfg.font_regular, cfg.font_bold)
    print("字体     " + ("按文件声明 ✓" if faces else "未找到字体文件，回退到系统字体族名（确认已装 Noto Sans CJK 或苹方）"))
    try:
        subprocess.run(["git", "-C", str(Path(__file__).parent), "config", "core.hooksPath"], check=True, capture_output=True)
        print("提交检查 已启用 ✓")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("提交检查 未启用（在仓库里执行 git config core.hooksPath .githooks）")
    sys.exit(0 if ok else 1)


def main():
    p = argparse.ArgumentParser(prog="doctrans", description="本地批量翻译长篇 PDF 为中文并按原书版式重排")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("inspect", help="体检 PDF，生成配置草稿")
    s.add_argument("pdf", nargs="+")
    s.add_argument("--configs", default="configs", help="配置草稿目录（默认 ./configs）")
    s.set_defaults(func=cmd_inspect)
    s = sub.add_parser("glossary", help="从书后索引生成术语表")
    s.add_argument("config")
    s.add_argument("pages", help="索引页范围，如 1035-1052")
    s.add_argument("-o", "--output", required=True, help="输出 CSV，建议放在配置里 glossaries 指向的目录")
    s.set_defaults(func=cmd_glossary)
    s = sub.add_parser("run", help="解析、翻译、排版、质检（可断点续跑）")
    s.add_argument("config", nargs="+")
    s.set_defaults(func=cmd_run)
    s = sub.add_parser("render", help="只用缓存重新排版，不调模型")
    s.add_argument("config", nargs="+")
    s.set_defaults(func=lambda a: cmd_run(a, offline=True))
    s = sub.add_parser("doctor", help="检查运行环境")
    s.add_argument("config", nargs="?")
    s.set_defaults(func=cmd_doctor)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
