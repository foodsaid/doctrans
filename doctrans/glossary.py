"""从书后索引生成术语表：抽取索引词条 → 模型译成中文（人工术语表优先，已有的跳过）。
输出列 source,target,tgt_lng（UTF-8 带 BOM，Excel 直接打开不乱码；tgt_lng=zh-CN 兼容 BabelDOC）。"""
import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor

import pymupdf as fitz

from .llm import ask_json
from .translate import load_glossary

DOTS_PAGES = re.compile(r"(?:\s*\.{2,}[\s.]*|\s{2,}|\u2002\s*)([\d,\s–-]+)\s*$")  # 「词 ..... 12」「词  12, 15」
SEE_ALSO = re.compile(r"\.?\s+(?:See|siehe|voir)\b.*$")
CONTINUED = re.compile(r"\s*\((?:Forts|cont|suite|cont\.)\.?\)")

SYSTEM = """You are a terminologist for {domain} ({source_lang} → Simplified Chinese).
Use the official terminology of the Chinese product UI where one exists.
For each index entry return:
- "src": the form used in running text (undo index inversion, e.g. "Abfrage, gespeicherte" → "gespeicherte Abfrage"; otherwise unchanged)
- "zh": the Chinese translation (keep abbreviations and product names unchanged)
Reply ONLY with a JSON array: [{{"i": <index>, "src": "...", "zh": "..."}}]
Mandatory reference terms:
"""


def extract_index(doc, first, last):
    """两栏索引，按缩进分主词条/子词条（更深缩进是折行，忽略）。返回主词条列表（去重保序）。"""
    terms = []
    for pno in range(first - 1, last):
        page = doc[pno]
        mid = page.rect.width / 2
        lines = [(l["bbox"][0], l["bbox"][1], "".join(s["text"] for s in l["spans"]).strip())
                 for b in page.get_text("dict")["blocks"] for l in b.get("lines", [])]
        lines = sorted((l for l in lines if l[2]), key=lambda t: (t[0] >= mid, t[1]))  # 先左栏后右栏
        col_left = {}
        for x, _, _ in lines:
            col_left[x >= mid] = min(col_left.get(x >= mid, x), x)
        for x, _, text in lines:
            if re.fullmatch(r"\d+|[^\W\d_]|Index|Symbols|Symbole", text):
                continue  # 页眉、页码、字母分组标题
            label = SEE_ALSO.sub("", CONTINUED.sub("", DOTS_PAGES.sub("", text))).strip().rstrip(",")
            if x - col_left[x >= mid] < 5 and label and label not in terms:
                terms.append(label)
    return terms


def build(cfg, first, last, out_csv):
    manual = dict(load_glossary(cfg.glossaries))
    terms = [t for t in extract_index(fitz.open(cfg.input), first, last) if t not in manual]
    print(f"索引主词条 {len(terms)} 个（已排除人工术语表中的 {len(manual)} 条）")
    system = SYSTEM.format(domain=cfg.domain or "this book", source_lang=cfg.source_lang)
    system += "\n".join(f"{k} = {v}" for k, v in manual.items())

    def run_batch(start):
        chunk = terms[start:start + 30]
        user = json.dumps([{"i": i, "term": t} for i, t in enumerate(chunk)], ensure_ascii=False)
        for _ in range(3):
            try:
                return ask_json(cfg.llm_url, cfg.model, system, user, timeout=600)
            except (ValueError, KeyError, TypeError) as e:
                print(f"  批次 {start} 解析失败: {e}，重试")
        return []

    out = {}
    with ThreadPoolExecutor(cfg.parallel) as pool:
        for n, items in enumerate(pool.map(run_batch, range(0, len(terms), 30)), 1):
            for item in items:
                src, zh = str(item.get("src", "")).strip(), str(item.get("zh", "")).strip()
                if src and zh and src not in manual and "→" not in zh:
                    out[src] = zh
            print(f"{min(n * 30, len(terms))}/{len(terms)}", flush=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "target", "tgt_lng"])
        w.writerows([s, t, "zh-CN"] for s, t in sorted(out.items()))
    print(f"写出 {len(out)} 条 -> {out_csv}")
