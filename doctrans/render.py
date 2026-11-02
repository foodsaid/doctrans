"""Markdown → HTML → PDF（WeasyPrint）。生成带页码的目录和书签（章/节/小节三级）。"""
import re
from pathlib import Path
from string import Template

import markdown
from weasyprint import HTML

CSS = Template((Path(__file__).parent / "book.css").read_text(encoding="utf-8"))

# WSL 里看不到 Windows 字体（不在 fontconfig 中），要按文件路径声明；其它平台靠字体族名回退
FONT_CANDIDATES = [
    ("/mnt/c/Windows/Fonts/msyh.ttc", "/mnt/c/Windows/Fonts/msyhbd.ttc"),
    ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc"),
]


def font_faces(regular, bold):
    if not regular:
        regular, bold = next(((r, b) for r, b in FONT_CANDIDATES if Path(r).exists()), ("", ""))
    faces = []
    if regular:
        faces.append(f"@font-face {{ font-family: DocFont; src: url({Path(regular).as_uri()}); }}")
    if bold:
        faces.append(f"@font-face {{ font-family: DocFont; font-weight: bold; src: url({Path(bold).as_uri()}); }}")
    return "\n".join(faces)


def build_toc(body):
    """目录收 h1（章）和带编号的 h2（节，如「3.1 …」），页码由 WeasyPrint 的 target-counter 填。"""
    items = []
    for level, hid, text in re.findall(r'<h([12]) id="([^"]+)">(.*?)</h\1>', body):
        plain = re.sub(r"<[^>]+>", "", text)
        if level == "1" or re.match(r"\d+\.\d+\s", plain):
            items.append(f'<div class="l{level}"><a href="#{hid}">{plain}</a></div>')
    return f'<nav class="toc"><h1>目录</h1>{"".join(items)}</nav>' if items else ""


def to_html(text):
    html = markdown.markdown(text, extensions=["tables", "md_in_html", "toc", "fenced_code"])
    return re.sub(r"<p>((?:图|表) \d+\.\d+\s*[：:])", r'<p class="cap">\1', html)


def render(front_md, body_md, out_path, title, page_size, fonts):
    """front_md：第一章之前的内容（封面、版权页、前言），排在生成的目录前面。写出 .html 和 .pdf。"""
    css = CSS.substitute(font_faces=font_faces(*fonts), page_width=f"{page_size[0]:.0f}", page_height=f"{page_size[1]:.0f}")
    front, body = to_html(front_md), to_html(body_md)
    html = (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{title}</title>'
            f'<style>{css}</style></head><body>{front}{build_toc(body)}{body}</body></html>')
    out_path.with_suffix(".html").write_text(html, encoding="utf-8")
    HTML(string=html, base_url=str(out_path.parent)).write_pdf(out_path.with_suffix(".pdf"))
