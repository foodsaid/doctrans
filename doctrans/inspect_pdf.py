"""体检 PDF 并生成配置草稿：文字层、语言、开本、书签 → 建议页码范围（跳过原目录和索引）、章节词、图注词。"""
import collections
import json
import os
import re
from pathlib import Path

import pymupdf as fitz

LANGS = {  # 语言: (常见虚词, 章节词, 图注词)
    "German": ({"der", "die", "und", "nicht", "mit", "für", "ist", "werden", "sie"}, ["Kapitel", "Anhang"], "Abbildung"),
    "English": ({"the", "and", "of", "to", "is", "for", "with", "you", "this"}, ["Chapter", "Appendix"], "Figure"),
    "French": ({"le", "la", "les", "et", "des", "est", "pour", "avec", "vous"}, ["Chapitre", "Annexe"], "Figure"),
    "Spanish": ({"el", "la", "los", "y", "de", "es", "para", "con", "que"}, ["Capítulo", "Apéndice"], "Figura"),
    "Italian": ({"il", "la", "che", "e", "di", "è", "per", "con", "non"}, ["Capitolo", "Appendice"], "Figura"),
    "Dutch": ({"de", "het", "en", "van", "een", "is", "voor", "met", "niet"}, ["Hoofdstuk", "Bijlage"], "Afbeelding"),
}
TOC_TITLES = {"content", "inhalt", "inhaltsverzeichnis", "contents", "table of contents", "sommaire", "índice", "indice", "inhoud"}
INDEX_TITLES = {"index", "register", "stichwortverzeichnis", "indice analitico", "índice alfabético"}


def detect_language(doc):
    sample = " ".join(doc[i].get_text() for i in range(0, doc.page_count, max(doc.page_count // 20, 1)))
    words = collections.Counter(w.lower() for w in re.findall(r"[^\W\d_]+", sample))
    return max(LANGS, key=lambda lang: sum(words[w] for w in LANGS[lang][0]))


def suggest(doc):
    """返回 (页码范围, 索引页范围, 书签里出现的章节词, 标题定级方式)。没有书签时返回全书。"""
    toc_entries = doc.get_toc()
    chapter_like = lambda t: re.match(r"^([^\W\d_]+) (\d+|[A-Z])\b", t.strip())
    # 章节词的编号全书不重复；「Case 10」「Step 2」这类每章重新编号的不是章
    numbers = collections.defaultdict(list)
    for level, t, _ in toc_entries:
        if m := chapter_like(t):
            numbers[m.group(1)].append((level, m.group(2)))
    chapter_words = {w for w, ns in numbers.items() if len(set(n for _, n in ns)) == len(ns)}
    # 有的书把各章挂在「Contents」书签下面：取章节词所在的那一层，连同它上面的层一起展平
    hits = collections.Counter(level for w in chapter_words for level, _ in numbers[w])
    bare = False
    if not hits:  # 章名直接以编号开头（「5 Installing …」）、没有章节词：取这种书签最多的一层
        hits = collections.Counter(level for level, t, _ in toc_entries if re.match(r"^\d{1,2} \S", t.strip()))
        bare = bool(hits)
    depth = max(hits, key=hits.get) if hits else 1
    top = [(title.strip(), page) for level, title, page in toc_entries if level <= depth]

    def bounds(k):
        later = [p for _, p in top[k + 1:] if p > top[k][1]]
        return top[k][1], (later[0] - 1) if later else doc.page_count

    toc = next((bounds(k) for k, (t, _) in enumerate(top) if t.lower() in TOC_TITLES), None)
    index = next((bounds(k) for k, (t, _) in enumerate(top) if t.lower() in INDEX_TITLES), None)
    if index:  # 索引后面常跟版权、广告页：截到最后一页「行尾是页码」的行仍占三成以上的页
        last = index[0]
        for p in range(index[0], index[1] + 1):
            lines = [l for l in doc[p - 1].get_text().splitlines() if l.strip()]
            if not lines or sum(bool(re.search(r"\d\s*$", l)) for l in lines) < len(lines) * 0.3:
                break
            last = p
        index = (index[0], last)
    words = collections.Counter(m.group(1) for t, _ in top if (m := chapter_like(t)) and m.group(1) in chapter_words)
    # 小节标题带编号（3.1、3.1.1）就按编号定级；不带编号的书改按书签定级
    sections = [t for level, t, _ in toc_entries if level == depth + 1]
    numbered = sum(bool(re.match(r"^\s*(?:\d+|[A-Z])(?:\.\d+)+\s", t)) for t in sections)
    headings = "numbers" if not bare and (not sections or numbered >= len(sections) / 2) else "bookmarks"
    end = index[0] - 1 if index else doc.page_count
    ranges = []
    if toc and toc[0] > 1:
        ranges.append((1, toc[0] - 1))
    start = toc[1] + 1 if toc else 1
    if start <= end:
        ranges.append((start, end))
    pages = ",".join(f"{a}-{b}" if a != b else str(a) for a, b in ranges) or "all"
    # 章节词：[] 表示章名直接以编号开头；None 表示没识别出来，用该语言的默认词
    found = [w for w, n in words.most_common() if n >= 1]
    return pages, index, [] if bare else (found or None), headings


def inspect(pdf, configs_dir):
    pdf = Path(pdf).absolute()  # 不解析软链接，保留短别名作为配置名
    doc = fitz.open(pdf)
    with_text = sum(1 for p in doc if p.get_text().strip())
    lang = detect_language(doc)
    pages, index, words, headings = suggest(doc)
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
chapter_words = {json.dumps(default_words if words is None else words, ensure_ascii=False)}
figure_word = "{figure_word}"
headings = "{headings}"   # numbers：按「3.1」式编号定标题层级；bookmarks：按 PDF 书签定级（小节不带编号的书）

[llm]
model = "qwen3.8:27b"
""", encoding="utf-8")
    print(f"  配置草稿 -> {out}")
    return out
