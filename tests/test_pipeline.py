import json

import pymupdf as fitz
import pytest

from doctrans import config, pipeline, qa, translate
from doctrans.inspect_pdf import inspect, suggest
from doctrans.structure import to_blocks

from .conftest import MINERU_MD, fake_ask_json, make_pdf


def test_structure_headings_headers_and_page_joins():
    blocks = to_blocks(MINERU_MD, ["Kapitel", "Anhang"])
    assert blocks[0] == "# Kapitel 1 Einleitung"            # 「## Kapitel 1」+ 下一行标题合并成章
    assert "## 1.1 Grundlagen" in blocks                      # 编号定层级
    assert "Ein Satz ohne Ende, der auf der nächsten Seite weiter geht und dort endet." in blocks  # 跨页接回
    assert "1 Einleitung" not in blocks and "4" not in blocks  # 页眉、页码丢弃
    assert "# Kapitel 2 Auswertung" in blocks


def test_glossary_first_file_wins_and_longest_first(book):
    cfg = config.load(book)
    gl = translate.load_glossary(cfg.glossaries)
    assert dict(gl)["Rechnungen"] == "发票"
    assert [len(s) for s, _ in gl] == sorted((len(s) for s, _ in gl), reverse=True)


def test_translate_retries_bad_json_and_caches(book, monkeypatch):
    cfg = config.load(book)
    cfg.output.mkdir(parents=True, exist_ok=True)
    calls = []

    def flaky(url, model, system, user, timeout=900):
        calls.append(system)
        if len(calls) == 1:
            raise ValueError("Expecting ',' delimiter")
        return fake_ask_json(url, model, system, user)

    monkeypatch.setattr(translate, "ask_json", flaky)
    blocks = ["Die Rechnungen der Lieferanten.", "![](images/x.png)"]
    zh = translate.translate(cfg, blocks, translate.load_glossary(cfg.glossaries), print)
    assert zh == ["译Die Rechnungen der Lieferanten.", "![](images/x.png)"]
    assert "Rechnungen = 发票" in calls[-1] and "Beleg" not in calls[-1]  # 只带本批出现的术语
    cache = [json.loads(l) for l in (cfg.output / "translate_cache.jsonl").read_text().splitlines()]
    assert len(cache) == 1


def test_inspect_suggests_ranges_and_writes_draft(tmp_path):
    pdf = tmp_path / "Mein Buch.pdf"
    make_pdf(pdf)
    pages, index, words, _ = suggest(fitz.open(pdf))
    assert pages == "1,3-4" and index == (5, 5) and words == ["Kapitel"]
    out = inspect(pdf, tmp_path / "configs")
    cfg = config.load(out)
    assert cfg.pages == "1,3-4" and cfg.source_lang == "German" and cfg.chapter_words == ["Kapitel"]


def test_end_to_end_with_fake_model(book, monkeypatch):
    monkeypatch.setattr(translate, "ask_json", fake_ask_json)
    cfg = config.load(book)
    pipeline.run(cfg)
    out = cfg.output
    zh_md = (out / "zh.md").read_text(encoding="utf-8")
    assert "fig_2_1_orig" in zh_md and "<table" not in zh_md        # 误识别成表格的截图换回原图
    assert "[+]" not in zh_md                                        # 页边图标不当标题
    assert list((out / "images").glob("page_3_block_2_orig.*"))      # 普通图换成原书嵌入图
    pdf = fitz.open(out / "zh.pdf")
    titles = [t for _, t, _ in pdf.get_toc()]
    assert "目录" in titles and "译Kapitel 1 Einleitung" in titles
    assert round(pdf[0].rect.width) == 477                           # 开本取原书
    assert (out / "images" / "cover.jpg").exists()                   # 无文字层的第 1 页当封面
    assert (out / "bi.pdf").exists() and (out / "qa" / "report.md").exists()
    for name in ("zh.pdf", "bi.pdf"):                                 # 成品质检：不能露出任何排版标记
        assert not qa.residue(fitz.open(out / name)), name
    assert "残留标记 0 类" in (out / "qa" / "report.md").read_text(encoding="utf-8")

    # 只重排版：全部命中缓存，不调模型
    monkeypatch.setattr(translate, "ask_json", lambda *a, **k: pytest.fail("render 不应调用模型"))
    pipeline.run(cfg, offline=True)
    assert "待翻译 0" in (out / "run.log").read_text(encoding="utf-8")


ENGLISH_MD = """<!-- page 20 of 99 -->

## Chapter 3

## Stock Basics

The warehouse keeps stock in several bins, and the count runs

<!-- page 21 of 99 -->

21

Stock Basics

every night.

## The report shows two values:

## ▪ Quantity

▪ Plain item

– Nested item

<!-- page 22 of 99 -->

▪ Item after page break"""


def test_structure_english_layout():
    from doctrans.structure import listify
    blocks = to_blocks(ENGLISH_MD, ["Chapter", "Appendix"])
    assert blocks[0] == "# Chapter 3 Stock Basics"
    assert "Stock Basics" not in blocks                                   # 只印章名的页眉丢弃
    assert "The warehouse keeps stock in several bins, and the count runs every night." in blocks
    assert "The report shows two values:" in blocks                       # 冒号结尾的不是标题
    assert "- **Quantity**" in blocks
    assert "▪ Item after page break" in blocks                            # 新列表项不接到上一段
    assert listify(blocks[-3:]) == ["- Plain item", "    - Nested item", "- Item after page break"]
    # 二级符号前面不是列表时不能缩进（会被排成代码块）；整行加粗的列表项也要认；多行说明逐行缩进
    assert listify(["Text.", "– Lone dash item", "**▪ Bold item**", "- **T**\n\n    a\nb"]) == [
        "Text.", "- Lone dash item", "- **Bold item**", "- **T**\n\n    a\n    b"]


def test_code_block_after_list_title_stays_separate():
    md = "## ▪ For one browser:\n\n```xml\n<a>\n\n</a>\n```\n\nSELECT T0.Doc\\_Num FROM T0 WHERE T0.x &lt; 3\n\nNext paragraph."
    blocks = to_blocks(md, ["Chapter"])
    assert blocks == ["- **For one browser:**", "```xml\n<a>\n\n</a>\nSELECT T0.Doc_Num FROM T0 WHERE T0.x < 3\n```",
                      "Next paragraph."]


def test_suggest_nested_bookmarks_and_pages_after_index(tmp_path):
    doc = fitz.open()
    for title in ["", "Contents", "Chapter 1 Start", "", "Chapter 2 End", "Index", "Index", "Service"]:
        doc.new_page().insert_text((60, 60), title or "text")
    doc.set_toc([[1, "Cover", 1], [1, "Contents", 2], [2, "Chapter 1: Start", 3],
                 [2, "Chapter 2: End", 5], [2, "Index", 6]])
    pages, index, words, headings = suggest(doc)
    assert (pages, index, words, headings) == ("1,3-5", (6, 6), ["Chapter"], "numbers")


OUTLINE = [[1, "Preface", 1], [1, "Chapter 1:Getting Started", 2], [2, "Basic ideas", 2], [2, "Summary", 3],
           [1, "Chapter 2:Going Further", 4], [2, "Advanced ideas", 4], [3, "Case 1—First worked example", 4],
           [2, "Summary", 5]]
OUTLINE_MD = """## Preface

Intro text.

## Getting Started

Some text.

## Basic ideas

[ 3 ]

Chapter 1

## Summary

Getting Started

## Going Further

## Advanced ideas

## Case 1—First worked

example

## A heading not in the bookmarks

## Summary"""


def test_structure_bookmark_headings():
    blocks = to_blocks(OUTLINE_MD, ["Chapter"], OUTLINE)
    assert [b for b in blocks if b.startswith("#")] == [
        "# Preface", "# Chapter 1 Getting Started", "## Basic ideas", "## Summary",
        "# Chapter 2 Going Further", "## Advanced ideas", "### Case 1—First worked example",
        "#### A heading not in the bookmarks", "## Summary"]
    assert "[ 3 ]" not in blocks and "Chapter 1" not in blocks and "Getting Started" not in blocks  # 页码、页眉


def test_translate_retries_when_markup_is_lost(book, monkeypatch):
    cfg = config.load(book)
    cfg.output.mkdir(parents=True, exist_ok=True)
    calls = []

    def drops_heading(url, model, system, user, timeout=900):
        calls.append(1)
        out = fake_ask_json(url, model, system, user)
        if len(calls) == 1:
            out = [{"i": x["i"], "zh": x["zh"].lstrip("# ")} for x in out]  # 第一次把标题符号弄丢
        return out

    monkeypatch.setattr(translate, "ask_json", drops_heading)
    zh = translate.translate(cfg, ["## 1.1 Grundlagen", "- Punkt"], [], lambda m: None)
    assert zh == ["## 译1.1 Grundlagen", "- 译Punkt"] and len(calls) == 2


def test_ui_labels_mode_retranslates_only_latin_labels(book, monkeypatch):
    cfg = config.load(book)
    cfg.output.mkdir(parents=True, exist_ok=True)
    blocks = ["Open the tab.", "Plain sentence."]
    first = lambda *a, **k: [{"i": 0, "zh": "打开「Security」选项卡。"}, {"i": 1, "zh": "普通句子。"}]
    monkeypatch.setattr(translate, "ask_json", first)
    assert translate.translate(cfg, blocks, [], lambda m: None)[0] == "打开「Security」选项卡。"

    cfg.ui_labels, calls = "both", []

    def second(url, model, system, user, timeout=900):
        calls.append((system, json.loads(user)))
        return [{"i": 0, "zh": "打开「Security」选项卡。"}]          # 模型坚持不译（如产品名）

    monkeypatch.setattr(translate, "ask_json", second)
    translate.translate(cfg, blocks, [], lambda m: None)
    assert len(calls) == 1 and [x["src"] for x in calls[0][1]] == ["Open the tab."]   # 只重译带外文界面名的那段
    assert "(Original)" in calls[0][0]
    translate.translate(cfg, blocks, [], lambda m: None)
    assert len(calls) == 1                                                            # 已按新模式翻过，不再反复重译
