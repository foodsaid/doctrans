"""用本地 MinerU 把 PDF 解析为 Markdown，并导出图片。只走本地模式，解析前检查隐私设置。"""
import re
import subprocess
import time

IMAGE = re.compile(r"^!\[[^\]]*\]\((doc:[^)]+)\)$")


def check_local_only(mineru):
    """MinerU 支持远程解析和遥测。书稿不能外传：本地模式未设成 managed 或遥测未关时拒绝运行。
    本地 server 空闲会自动退出，它不在时连配置都读不出来，所以先确保它在运行。"""
    status = subprocess.run([mineru, "server", "status"], capture_output=True, text=True)
    if "not running" in status.stdout + status.stderr:
        subprocess.run([mineru, "server", "start"], check=True, capture_output=True)
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
            cmd = [cfg.mineru, "parse", cfg.input, "--pages", rng, "--tier", "standard", "--wait", "14400", "-o", md_path]
            for _ in range(30):  # 本地服务刚启动的头几秒解析端还没就绪，等一等再试
                result = subprocess.run(cmd, capture_output=True, text=True)
                if "not ready" not in result.stdout + result.stderr:
                    break
                time.sleep(6)
            if result.returncode or not md_path.exists():
                raise RuntimeError(f"MinerU 解析 {rng} 失败: {(result.stderr or result.stdout).strip()[-500:]}")
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
