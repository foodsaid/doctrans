"""体检 PDF 并生成配置草稿：文字层、语言、开本、书签 → 建议页码范围（跳过原目录和索引）、章节词、图注词。"""
import collections
import json
import os
import re
from pathlib import Path

import fitz

LANGS = {  # 语言: (常见虚词, 章节词, 图注词)
    "German": ({"der", "die", "und", "nicht", "mit", "für", "ist", "werden", "sie"}, ["Kapitel", "Anhang"], "Abbildung"),
    "English": ({"the", "and", "of", "to", "is", "for", "with", "you", "this"}, ["Chapter", "Appendix"], "Figure"),
    "French": ({"le", "la", "les", "et", "des", "est", "pour", "avec", "vous"}, ["Chapitre", "Annexe"], "Figure"),
    "Spanish": ({"el", "la", "los", "y", "de", "es", "para", "con", "que"}, ["Capítulo", "Apéndice"], "Figura"),
    "Italian": ({"il", "la", "che", "e", "di", "è", "per", "con", "non"}, ["Capitolo", "Appendice"], "Figura"),
    "Dutch": ({"de", "het", "en", "van", "een", "is", "voor", "met", "niet"}, ["Hoofdstuk", "Bijlage"], "Afbeelding"),
}
TOC_TITLES = {"inhalt", "inhaltsverzeichnis", "contents", "table of contents", "sommaire", "índice", "indice", "inhoud"}
INDEX_TITLES = {"index", "register", "stichwortverzeichnis", "indice analitico", "índice alfabético"}


def detect_language(doc):
    sample = " ".join(doc[i].get_text() for i in range(0, doc.page_count, max(doc.page_count // 20, 1)))
    words = collections.Counter(w.lower() for w in re.findall(r"[^\W\d_]+", sample))
    return max(LANGS, key=lambda lang: sum(words[w] for w in LANGS[lang][0]))


def suggest(doc):
    """返回 (页码范围, 索引页范围, 书签里出现的章节词)。没有书签时返回全书。"""
    top = [(title.strip(), page) for level, title, page in doc.get_toc() if level == 1]
    bounds = lambda k: (top[k][1], (top[k + 1][1] - 1) if k + 1 < len(top) else doc.page_count)
    toc = next((bounds(k) for k, (t, _) in enumerate(top) if t.lower() in TOC_TITLES), None)
    index = next((bounds(k) for k, (t, _) in enumerate(top) if t.lower() in INDEX_TITLES), None)
    words = collections.Counter(m.group(1) for t, _ in top if (m := re.match(r"^([^\W\d_]+) (?:\d+|[A-Z])\b", t)))
    end = index[0] - 1 if index else doc.page_count
    ranges = []
    if toc and toc[0] > 1:
        ranges.append((1, toc[0] - 1))
    start = toc[1] + 1 if toc else 1
    if start <= end:
        ranges.append((start, end))
    pages = ",".join(f"{a}-{b}" if a != b else str(a) for a, b in ranges) or "all"
    return pages, index, [w for w, n in words.most_common() if n >= 1]


def inspect(pdf, configs_dir):
    pdf = Path(pdf).absolute()  # 不解析软链接，保留短别名作为配置名
    doc = fitz.open(pdf)
    with_text = sum(1 for p in doc if p.get_text().strip())
    lang = detect_language(doc)
    pages, index, words = suggest(doc)
    rect = doc[doc.page_count // 2].rect
    _, default_words, figure_word = LANGS[lang]
    print(f"{pdf.name}: {doc.page_count} 页，有文字层 {with_text} 页，开本 {rect.width:.0f}×{rect.height:.0f}pt，"
          f"书签 {len(doc.get_toc())} 条，语言 {lang}")
    if with_text < doc.page_count * 0.8:
        print("  注意: 多数页没有文字层（扫描件），MinerU 会走 OCR，速度慢、需抽查识别质量")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", pdf.stem).strip("-").lower()[:40] or "doc"
    configs_dir = Path(configs_dir).resolve()
    configs_dir.mkdir(parents=True, exist_ok=True)
    out = configs_dir / f"{slug}.toml"
    if out.exists():
        print(f"  已存在 {out}，未覆盖")
        return out
    rel = lambda p: Path(os.path.relpath(p, configs_dir)).as_posix()
    index_note = f"{index[0]}-{index[1]}" if index else "未识别"
    out.write_text(f"""# doctrans 配置草稿（由 inspect 生成，请核对页码范围后再运行）
input = "{rel(pdf)}"
output = "{rel(configs_dir.parent / 'work' / slug)}"
# 要翻译的页：已跳过原目录和索引（索引在 {index_note}，可用 doctrans glossary 生成术语表）。
# 前置页里的「概览/简明目录」类页面也建议去掉，生成的中文目录会替代它们。
pages = "{pages}"
source_lang = "{lang}"
domain = ""            # 书的主题，如 "ERP software"，写进提示词帮助选术语
glossaries = ["../glossary/{slug}/*.csv"]

[structure]
chapter_words = {json.dumps(words or default_words, ensure_ascii=False)}
figure_word = "{figure_word}"

[llm]
model = "qwen3.8:27b"
""", encoding="utf-8")
    print(f"  配置草稿 -> {out}")
    return out
