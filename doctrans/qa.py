"""质检报告 qa/report.md：疑似漏译段、术语遵守情况、页数和书签层级，并渲染抽样页供目视检查。"""
import collections
import re

import fitz

CJK = re.compile(r"[一-鿿]")
LATIN = re.compile(r"[A-Za-zÀ-ÿ]")
NOT_PROSE = re.compile(r"\]\([^)]*\)|https?://\S+|`[^`]*`|```.*?```|「[^」]*」|&lt;.*?&gt;|[A-Za-z]:\\\S+|\S+\.(?:exe|xml|ini|dll)\b",
                       re.S)


def untranslated(blocks, zh):
    """拉丁字母多、中文极少的正文段视为疑似漏译（标题、图片、表格、代码除外）。"""
    out = []
    for src, cn in zip(blocks, zh):
        if cn.startswith(("![", "<", "#", "```", "|", "[")) or "<table" in cn:
            continue  # 图片、表格、代码、链接里的原文多是界面数据，不算漏译
        prose = NOT_PROSE.sub(" ", cn)  # 链接、网址、路径、代码、界面标签本来就保留原文
        if len(LATIN.findall(prose)) >= 40 and len(CJK.findall(prose)) < len(prose) * 0.1:
            out.append(cn)
    return out


def glossary_misses(blocks, zh, glossary, min_hits=5):
    """原文出现 ≥ min_hits 次、但译文中目标词不到一半次数的术语。"""
    src_text, zh_text = "\n".join(blocks), "\n".join(zh)
    misses = []
    for s, t in glossary:
        if s == t:
            continue
        n_src = len(re.findall(rf"\b{re.escape(s)}\b", src_text))
        if n_src >= min_hits and zh_text.count(t) < n_src / 2:
            misses.append((s, t, n_src, zh_text.count(t)))
    return sorted(misses, key=lambda m: -m[2])


def report(cfg, blocks, zh, glossary):
    qa_dir = cfg.output / "qa"
    qa_dir.mkdir(exist_ok=True)
    left = untranslated(blocks, zh)
    misses = glossary_misses(blocks, zh, glossary)
    lines = [f"# 质检报告：{cfg.name}", ""]
    pdf = fitz.open(cfg.output / "zh.pdf")
    levels = collections.Counter(level for level, *_ in pdf.get_toc())
    size_mb = (cfg.output / "zh.pdf").stat().st_size / 1e6
    lines += [f"- 页数 {pdf.page_count}，体积 {size_mb:.1f} MB，书签 {dict(sorted(levels.items()))}",
              f"- 段落 {len(blocks)}，疑似漏译 {len(left)}，术语偏差 {len(misses)}", ""]
    if left:
        lines += ["## 疑似漏译", ""] + [f"- {b[:120]}" for b in left[:50]] + [""]
    if misses:
        lines += ["## 术语偏差（原文次数 / 译文中目标词次数）", ""]
        lines += [f"- {s} → {t}：{n} / {m}" for s, t, n, m in misses[:50]] + [""]
    # 抽样页：第 2 页和全书均匀取几页
    samples = sorted({1, *range(pdf.page_count // 7, pdf.page_count, max(pdf.page_count // 7, 1))})[:8]
    for p in samples:
        pdf[p].get_pixmap(dpi=80).save(qa_dir / f"page_{p + 1:04d}.png")
    lines += ["## 抽样页", ""] + [f"- qa/page_{p + 1:04d}.png" for p in samples]
    (qa_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"漏译 {len(left)}，术语偏差 {len(misses)}，见 qa/report.md"
