"""图片尽量用原 PDF 里的嵌入图：MinerU 导出的是 200dpi 重渲染的大 PNG（约 5 倍体积），
而且会把界面截图误识别成 HTML 表格（宽表右侧数据被裁掉）。"""
import re

import pymupdf as fitz

MINERU_DPI = 200


def fig_tag(path, width):
    return f'<div class="fig"><img src="images/{path.name}" style="width:{width:.0f}pt"></div>'


def save_original(doc, xref, stem):
    """原样存出嵌入图（PNG/JPEG 直接写字节，其它格式或带透明蒙版的转成 RGB PNG）。"""
    img = doc.extract_image(xref)
    ext = img["ext"] if img["ext"] in ("png", "jpeg") and not img.get("smask") else "png"
    dst = stem.with_suffix(f".{ext}")
    if not dst.exists():
        if ext == img["ext"]:
            dst.write_bytes(img["image"])
        else:
            p = fitz.Pixmap(doc, xref)
            if p.n - p.alpha > 3:
                p = fitz.Pixmap(fitz.csRGB, p)
            p.save(dst)
    return dst


def figure_html(doc, md, out_dir):
    """为每个 MinerU 图片行找原书同页、宽高比相近的嵌入图，按原尺寸显示。返回 {Markdown 图片行: HTML}。"""
    used, figures = set(), {}
    for m in re.finditer(r"^!\[\]\(images/(page_(\d+)_block_\d+)\.png\)$", md, re.M):
        name, page = m.group(1), int(m.group(2))
        src = out_dir / "images" / f"{name}.png"
        pix = fitz.Pixmap(str(src))
        aspect, best = pix.width / pix.height, None
        for info in doc[page - 1].get_image_info(xrefs=True):
            x0, y0, x1, y1 = info["bbox"]
            if not info["xref"] or (page, info["xref"]) in used or x1 - x0 < 40 or y1 <= y0:
                continue
            diff = abs((x1 - x0) / (y1 - y0) / aspect - 1)
            if diff < 0.15 and (best is None or diff < best[0]):
                best = (diff, info["xref"], x1 - x0)
        if best:
            _, xref, width = best
            used.add((page, xref))
            dst = save_original(doc, xref, src.with_name(f"{name}_orig"))
        else:
            dst, width = src, pix.width * 72 / MINERU_DPI
        figures[m.group(0)] = fig_tag(dst, width)
    return figures


def caption_pages(doc, figure_word):
    """{图号: 页索引}，按原文图注「Abbildung 6.44:」定位。"""
    pages = {}
    for i, page in enumerate(doc):
        for num in re.findall(rf"{re.escape(figure_word)} (\d+\.\d+):", page.get_text()):
            pages.setdefault(num, i)
    return pages


def screenshot_for_caption(doc, captions, figure_word, num, out_dir):
    """取图注上方最近的嵌入图。找不到返回 None（保留表格）。"""
    if num not in captions:
        return None
    page = doc[captions[num]]
    hits = page.search_for(f"{figure_word} {num}:")
    if not hits:
        return None
    best = None
    for info in page.get_image_info(xrefs=True):
        x0, y0, x1, y1 = info["bbox"]
        if info["xref"] and x1 - x0 >= 40 and y1 <= hits[0].y0 + 5 and (best is None or y1 > best[1]):
            best = (info["xref"], y1, x1 - x0)
    if not best:
        return None
    dst = save_original(doc, best[0], out_dir / "images" / f"fig_{num.replace('.', '_')}_orig")
    return fig_tag(dst, best[2])


def cover(doc, pages, out_dir):
    """第 1 页没有文字层时当封面：直接渲染原页（交给 MinerU 会把封面上的截图解析成乱表格）。
    返回 (封面 HTML 或 "", 去掉第 1 页后的页码范围)。"""
    first = doc[0]
    if not re.match(r"1(\D|$)", pages) or first.get_text().strip():
        return "", pages
    (out_dir / "images").mkdir(parents=True, exist_ok=True)
    first.get_pixmap(dpi=150).save(out_dir / "images" / "cover.jpg", jpg_quality=85)
    html = f'<div class="fig"><img src="images/cover.jpg" style="width:{first.rect.width - 68:.0f}pt"></div>'
    if pages.startswith("1-"):
        return html, "2-" + pages[2:]
    return html, pages.split(",", 1)[1] if "," in pages else ""
