"""把 MinerU 的 Markdown 切成段落块：去页码和页眉、按编号重定标题层级、接回跨页断开的段落。
MinerU 给的 # 层级不可靠（几乎全是 ##，页眉也被标成标题），所以只信编号：
「<章词> N 标题」→ h1，「3.1 标题」→ h2，「3.1.1」→ h3；同一编号只有第一次出现是标题，其余是页眉。"""
import re

PAGE_MARK = re.compile(r"^<!-- page \d+ of \d+ -->$")
SENTENCE_END = re.compile(r"[.:!?)»“\"]$")
PAGE_NUMBER = re.compile(r"^\d{1,4}$")
SECTION = re.compile(r"^#*\s*((?:\d+|[A-Z])(?:\.\d+)+)\s+([^\n]{1,100})$")
LIST_TITLE = re.compile(r"- \*\*[^\n]+\*\*")


def chapter_pattern(words):
    """章标题，如「Kapitel 7 Grundlagen」「Anhang A …」「Chapter 3 …」。"""
    alt = "|".join(re.escape(w) for w in words)
    return re.compile(rf"^#*\s*((?:{alt}) (?:\d+|[A-Z]))(?:\s+([^\n]{{1,80}}))?$")


class Normalizer:
    def __init__(self, chapter_words):
        self.chapter = chapter_pattern(chapter_words)
        self.words = chapter_words
        self.seen = set()
        self.pending = None  # 「## Kapitel 7」单独一行时，章名在下一个标题里

    def __call__(self, block):
        """返回规范化后的块，None 表示丢弃（页码、页眉、重复标题）。"""
        if PAGE_NUMBER.match(block):
            return None
        m = re.match(r"^(\d{1,2}) (\S)[^\n]{0,80}$", block)
        if m and m.group(2).isupper() and any(f"{w} {m.group(1)}" in self.seen for w in self.words):
            return None  # 「2 Einführung in …」式页眉
        m = self.chapter.match(block)
        if m:
            if m.group(1) in self.seen:
                return None
            self.seen.add(m.group(1))
            if not m.group(2):
                self.pending = m.group(1)
                return None
            self.pending = None
            return f"# {m.group(1)} {m.group(2)}"
        if self.pending and block.startswith("#"):
            title, self.pending = f"# {self.pending} {block.lstrip('# ')}", None
            return title
        m = SECTION.match(block)
        if m and (block.startswith("#") or len(block) < 100):
            if m.group(1) in self.seen:
                return None
            self.seen.add(m.group(1))
            depth = min(m.group(1).count(".") + 1, 4)
            return f"{'#' * depth} {m.group(1)} {m.group(2)}"
        if block.startswith("#") and not re.match(r"^#+ ?◾", block):
            text = block.lstrip("# ")
            return f"# {text}" if block.startswith("# ") else f"#### {text}"
        return block


def to_blocks(md, chapter_words):
    raw = [b.strip() for b in re.split(r"\n\s*\n", md) if b.strip()]
    normalize = Normalizer(chapter_words)
    blocks, after_page_break = [], False
    for block in raw:
        if PAGE_MARK.match(block):
            after_page_break = True
            continue
        block = normalize(block)
        if block is None:
            continue
        block = re.sub(r"^#+ ◾ ", "- **", block)  # 带方块符号的小标题其实是列表项
        if block.startswith("- **") and "**" not in block[4:]:
            block += "**"
        prev = blocks[-1] if blocks else ""
        if LIST_TITLE.fullmatch(prev) and not block.startswith(("#", "![", "- ", "|")):
            blocks[-1] = f"{prev}\n\n    {block}"  # 列表小标题和它的说明合成一个列表项
        elif (
            after_page_break and prev
            and not prev.startswith(("#", "![", "|"))
            and not LIST_TITLE.fullmatch(prev)
            and not block.startswith(("#", "![", "|"))
            and not SENTENCE_END.search(prev)
        ):
            # 上一段没以句末标点结束就视为被分页截断（德语名词大写，不能靠首字母判断）
            blocks[-1] = prev[:-1] + block if prev.endswith("-") else prev + " " + block
        else:
            blocks.append(block)
        after_page_break = False
    return blocks
