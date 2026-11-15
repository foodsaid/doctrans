"""每份文档一个 TOML 配置。相对路径以配置文件所在目录为基准。字段说明见 examples/example.toml。"""
import glob
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    input: Path
    output: Path
    pages: str = "all"
    source_lang: str = "German"
    domain: str = ""
    ui_labels: str = "auto"  # 界面名称：auto 由模型决定；translate 译成中文；both 中文后括号带原文
    glossaries: list[Path] = field(default_factory=list)
    chapter_words: list[str] = field(default_factory=lambda: ["Kapitel", "Anhang"])
    figure_word: str = "Abbildung"
    headings: str = "numbers"  # numbers：按「3.1」式编号定标题层级；bookmarks：按 PDF 书签
    llm_url: str = "http://localhost:11434/v1/chat/completions"
    model: str = "qwen3.8:27b"
    batch: int = 8
    parallel: int = 4
    mineru: str = "mineru"
    bilingual: bool = True
    font_regular: str = ""
    font_bold: str = ""

    @property
    def name(self):
        return self.output.name


def load(path):
    path = Path(path).resolve()
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    base = path.parent
    rel = lambda p: (base / p).resolve()
    s, llm, mineru, render = (raw.get(k, {}) for k in ("structure", "llm", "mineru", "render"))
    glossaries = []
    for pattern in raw.get("glossaries", []):
        glossaries += sorted(Path(p) for p in glob.glob(str(rel(pattern))))  # 列在前面的优先
    cfg = Config(input=rel(raw["input"]), output=rel(raw["output"]), glossaries=glossaries)
    for key in ("pages", "source_lang", "domain", "ui_labels"):
        if key in raw:
            setattr(cfg, key, raw[key])
    for section, keys in ((s, ("chapter_words", "figure_word", "headings")),
                          (llm, ("model", "batch", "parallel")),
                          (render, ("bilingual", "font_regular", "font_bold"))):
        for key in keys:
            if key in section:
                setattr(cfg, key, section[key])
    if "url" in llm:
        cfg.llm_url = llm["url"]
    if "bin" in mineru:
        cfg.mineru = str(rel(mineru["bin"])) if "/" in mineru["bin"] else mineru["bin"]
    if cfg.ui_labels not in ("auto", "translate", "both"):
        raise SystemExit(f"{path}: ui_labels 只能是 auto、translate 或 both，现在是 {cfg.ui_labels!r}")
    return cfg
