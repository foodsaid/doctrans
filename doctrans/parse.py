"""用本地 MinerU 把 PDF 解析为 Markdown，并导出图片。只走本地模式，解析前检查隐私设置。"""
import re
import subprocess

IMAGE = re.compile(r"^!\[[^\]]*\]\((doc:[^)]+)\)$")


def check_local_only(mineru):
    """MinerU 支持远程解析和遥测。书稿不能外传：本地模式未设成 managed 或遥测未关时拒绝运行。"""
    mode = subprocess.run([mineru, "config", "get", "parse_server.local.mode"], capture_output=True, text=True).stdout
    tele = subprocess.run([mineru, "telemetry", "status"], capture_output=True, text=True).stdout
    problems = []
    if "managed" not in mode:
        problems.append("mineru config set parse_server.local.mode managed")
    if "disabled" not in tele:
        problems.append("mineru telemetry disable")
    if problems:
        raise SystemExit("MinerU 未锁定为本地模式，请先执行:\n  " + "\n  ".join(problems))


def parse_pdf(cfg, pages):
    """pages 可写多个范围（如 2-4,6,19-1034），每个范围单独解析并缓存，追加范围时不必重解析已有部分。"""
    parts = []
    for rng in pages.split(","):
        md_path = cfg.output / f"source_{rng}.md"
        if not md_path.exists():
            check_local_only(cfg.mineru)
            # 本地 server 空闲会自动退出，解析前确保它在运行
            status = subprocess.run([cfg.mineru, "server", "status"], capture_output=True, text=True)
            if "not running" in status.stdout + status.stderr:
                subprocess.run([cfg.mineru, "server", "start"], check=True)
            subprocess.run(
                [cfg.mineru, "parse", cfg.input, "--pages", rng, "--tier", "standard", "--wait", "14400", "-o", md_path],
                check=True,
            )
        parts.append(md_path.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def export_images(cfg, md):
    """把 MinerU 的 doc: 图片引用导出成 images/page_N_block_M.png。小于 1KB 的碎图（分隔线等）丢弃，
    文件保留以便续跑时知道已处理过。"""
    img_dir = cfg.output / "images"
    img_dir.mkdir(exist_ok=True)
    lines = []
    for line in md.splitlines():
        m = IMAGE.match(line.strip())
        if m:
            name = re.sub(r"[^\w]+", "_", m.group(1).split("/", 2)[-1]) + ".png"
            if not (img_dir / name).exists():
                subprocess.run([cfg.mineru, "read", m.group(1), "-f", "image", "-o", img_dir / name],
                               check=True, capture_output=True)
            if (img_dir / name).stat().st_size < 1024:
                continue
            line = f"![](images/{name})"
        lines.append(line)
    return "\n".join(lines)
