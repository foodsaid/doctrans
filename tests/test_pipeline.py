import json

import fitz
import pytest

from doctrans import config, pipeline, translate
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
    pages, index, words = suggest(fitz.open(pdf))
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

    # 只重排版：全部命中缓存，不调模型
    monkeypatch.setattr(translate, "ask_json", lambda *a, **k: pytest.fail("render 不应调用模型"))
    pipeline.run(cfg, offline=True)
    assert "待翻译 0" in (out / "run.log").read_text(encoding="utf-8")
