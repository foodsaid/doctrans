"""单份文档：解析 → 切段 → 翻译 → 图片换原图 → 排版（纯中文 + 对照）→ 质检报告。"""
import re
import time

import fitz

from . import figures, qa
from .parse import export_images, parse_pdf
from .render import render
from .structure import chapter_pattern, listify, to_blocks
from .translate import load_glossary, translate


def make_logger(cfg):
    log_file = open(cfg.output / "run.log", "a", encoding="utf-8")

    def log(msg):
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        log_file.write(line + "\n")
        log_file.flush()
    return log


def run(cfg, offline=False):
    cfg.output.mkdir(parents=True, exist_ok=True)
    log = make_logger(cfg)
    doc = fitz.open(cfg.input)
    pages = cfg.pages if cfg.pages != "all" else f"1-{doc.page_count}"
    cover, pages = figures.cover(doc, pages, cfg.output)

    log(f"[{cfg.name}] 解析 {pages}")
    md = export_images(cfg, parse_pdf(cfg, pages)) if pages else ""
    blocks = to_blocks(md, cfg.chapter_words, doc.get_toc() if cfg.headings == "bookmarks" else None)
    zh = translate(cfg, blocks, load_glossary(cfg.glossaries), log, offline=offline)

    # 被识别成表格的截图换回原图；页边小图标（[+]、[!] 等）不是标题，丢掉
    captions = figures.caption_pages(doc, cfg.figure_word)
    pairs = []
    for i, (src, cn) in enumerate(zip(blocks, zh)):
        if re.match(r"^#+ \[.{1,3}\]$", src):
            continue
        nxt = re.match(r"图 (\d+\.\d+)", zh[i + 1]) if i + 1 < len(zh) else None
        if src.lstrip().startswith("<table") and nxt:
            fig = figures.screenshot_for_caption(doc, captions, cfg.figure_word, nxt.group(1), cfg.output)
            if fig:
                src = cn = fig
        pairs.append((src, cn))
    blocks, zh = [listify(p[0]) for p in pairs], [listify(p[1]) for p in pairs]
    (cfg.output / "zh.md").write_text("\n\n".join(zh) + "\n", encoding="utf-8")

    log(f"[{cfg.name}] 排版")
    fig_map = figures.figure_html(doc, md, cfg.output)
    swap = lambda text: re.sub(r"^!\[\]\(images/[^)]+\)$", lambda m: fig_map.get(m.group(0), m.group(0)), text, flags=re.M)
    # 第一章之前是前置内容：标题降为 h2（不当章、不进页眉），每个标题另起一页
    chapter = chapter_pattern(cfg.chapter_words)
    n_front = next((i for i, b in enumerate(blocks) if chapter.match(b)), 0)
    as_front = lambda items: "\n\n".join([cover] * bool(cover) + [
        f'<div class="front"></div>\n\n#{b}' if b.startswith("# ") else b for b in items[:n_front]])
    outputs = {"zh": zh}
    if cfg.bilingual:
        # 标题和图片只放中文，正文段落前放原文
        outputs["bi"] = [cn if src.startswith(("![", "#", '<div class="fig"'))
                         else f'<div class="de" markdown="1">\n\n{src}\n\n</div>\n\n{cn}'
                         for src, cn in zip(blocks, zh)]
    page_size = (doc[doc.page_count // 2].rect.width, doc[doc.page_count // 2].rect.height)
    for name, items in outputs.items():
        render(swap(as_front(items)), swap("\n\n".join(items[n_front:])), cfg.output / name,
               cfg.name, page_size, (cfg.font_regular, cfg.font_bold))

    report = qa.report(cfg, blocks, zh, load_glossary(cfg.glossaries))
    log(f"[{cfg.name}] 完成: {cfg.output}（质检: {report}）")
