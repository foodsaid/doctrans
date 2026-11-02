"""测试只用脚本生成的合成 PDF 和伪造的 MinerU 输出，不依赖真实文档、MinerU 或模型服务。"""
import random
import re

import fitz
import pytest

W, H = 477, 680
GERMAN = ("Die Software unterstützt die Verwaltung der Rechnungen und Lieferanten. "
          "Sie können mit dem Programm die Daten für die Kunden pflegen, und die Belege werden automatisch erstellt.")


def solid_png(width, height, rgb):
    """带噪点的色块（纯色 PNG 压缩后不到 1KB，会被当成分隔线碎图丢掉）。"""
    noise = random.Random(width * height).randbytes(width * height * 3)
    samples = bytes((c + n % 40) % 256 for c, n in zip(rgb * (width * height), noise))
    return fitz.Pixmap(fitz.csRGB, width, height, samples, False)


def make_pdf(path):
    """5 页：封面（只有图）、目录、第 1 章（图 + 图注）、第 2 章（被误识别成表格的截图 + 图注）、索引。"""
    doc = fitz.open()
    cover = doc.new_page(width=W, height=H)
    cover.insert_image(fitz.Rect(40, 40, W - 40, H - 40), pixmap=solid_png(200, 300, (40, 90, 160)))
    toc = doc.new_page(width=W, height=H)
    toc.insert_text((60, 80), "Inhalt")
    p3 = doc.new_page(width=W, height=H)
    p3.insert_text((60, 60), "Kapitel 1 Einleitung")
    p3.insert_textbox(fitz.Rect(60, 80, W - 40, 200), GERMAN, fontsize=9)
    p3.insert_image(fitz.Rect(40, 220, 440, 420), pixmap=solid_png(800, 400, (200, 50, 50)))
    p3.insert_text((60, 440), "Abbildung 1.1: Testbild")
    p4 = doc.new_page(width=W, height=H)
    p4.insert_text((60, 60), "Kapitel 2 Auswertung")
    p4.insert_image(fitz.Rect(40, 100, 440, 300), pixmap=solid_png(600, 300, (50, 160, 50)))
    p4.insert_text((60, 320), "Abbildung 2.1: Bericht")
    p4.insert_textbox(fitz.Rect(60, 340, W - 40, 500), GERMAN, fontsize=9)
    idx = doc.new_page(width=W, height=H)
    idx.insert_text((40, 60), "Index")
    for k, term in enumerate(["Beleg ........ 12", "Lieferant ........ 30", "Rechnung ........ 45"]):
        idx.insert_text((40, 100 + 14 * k), term, fontsize=9)
    doc.set_toc([[1, "Inhalt", 2], [1, "Kapitel 1 Einleitung", 3], [1, "Kapitel 2 Auswertung", 4], [1, "Index", 5]])
    doc.save(path)


MINERU_MD = f"""<!-- page 3 of 5 -->

## Kapitel 1

## Einleitung

{GERMAN[:80]}

<!-- page 3 of 5 -->

![](doc:abc/tier:standard/page:3/block:2)

Abbildung 1.1: Testbild

## 1.1 Grundlagen

Ein Satz ohne Ende, der auf der nächsten Seite weiter

<!-- page 4 of 5 -->

1 Einleitung

4

geht und dort endet.

## Kapitel 2 Auswertung

<table><tr><td>Spalte</td><td>Wert</td></tr></table>

Abbildung 2.1: Bericht

## [+]

{GERMAN}
"""


def fake_ask_json(url, model, system, user, timeout=900):
    """伪模型：把「Abbildung」换成「图」，其余前面加「译」，保留 Markdown 标题前缀。"""
    import json
    items = json.loads(user)
    out = []
    for item in items:
        src = item["src"]
        if re.match(r"^Abbildung \d", src) or src.startswith("<"):
            zh = re.sub(r"^Abbildung (\d+\.\d+):", r"图 \1：", src)  # 图注和 HTML 原样结构
        else:
            zh = re.sub(r"^(#+ )?", lambda m: (m.group(1) or "") + "译", src, count=1)
        out.append({"i": item["i"], "zh": zh})
    return out


@pytest.fixture
def book(tmp_path):
    pdf = tmp_path / "inbox" / "sample.pdf"
    pdf.parent.mkdir()
    make_pdf(pdf)
    work = tmp_path / "work" / "sample"
    (work / "images").mkdir(parents=True)
    (work / "source_3-4.md").write_text(MINERU_MD, encoding="utf-8")
    solid_png(400, 200, (200, 50, 50)).save(work / "images" / "page_3_block_2.png")  # MinerU 重渲染图（同宽高比）
    gl = tmp_path / "glossary"
    gl.mkdir()
    (gl / "a_manual.csv").write_text("source,target,tgt_lng\nRechnungen,发票,zh-CN\nLieferanten,供应商,zh-CN\n", encoding="utf-8-sig")
    (gl / "b_index.csv").write_text("source,target,tgt_lng\nRechnungen,账单,zh-CN\nBeleg,单据,zh-CN\n", encoding="utf-8-sig")
    cfg = tmp_path / "configs" / "sample.toml"
    cfg.parent.mkdir()
    cfg.write_text('input = "../inbox/sample.pdf"\noutput = "../work/sample"\npages = "1,3-4"\n'
                   'domain = "ERP"\nglossaries = ["../glossary/*.csv"]\n'
                   '[render]\nfont_regular = ""\n', encoding="utf-8")
    return cfg
