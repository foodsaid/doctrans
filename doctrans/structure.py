"""把 MinerU 的 Markdown 切成段落块：去页码和页眉、按编号重定标题层级、接回跨页断开的段落。
MinerU 给的 # 层级不可靠（几乎全是 ##，页眉也被标成标题），所以只信编号：
「<章词> N 标题」→ h1，「3.1 标题」→ h2，「3.1.1」→ h3；同一编号只有第一次出现是标题，其余是页眉。
小节不带编号的书改用 PDF 书签定级（OutlineNormalizer）。"""
import collections
import html
import re

PAGE_MARK = re.compile(r"^<!-- page \d+ of \d+ -->$")
SENTENCE_END = re.compile(r"[.:!?)»“\"]$")
PAGE_NUMBER = re.compile(r"^(?:\d{1,4}|\[ *(?:\d{1,4}|[ivxlc]{1,6}) *\])$")  # 「12」「[ 12 ]」「[ vi ]」
SECTION = re.compile(r"^#*\s*((?:\d+|[A-Z])(?:\.\d+)+)\s+([^\n]{1,100})$")
LIST_TITLE = re.compile(r"- \*\*[^\n]+\*\*")
BULLET = "[◾▪•■●]"  # 各出版社的列表符号，MinerU 原样保留
# 没被 MinerU 包进代码块的 SQL 行（多是跨页代码的续行）：大写关键字或表别名开头，
# 或大小写混写的关键字开头且带代码符号；都不能像英文句子
CODE_LINE = re.compile(r"^(?:SELECT|FROM|WHERE|DECLARE|IF|INNER|LEFT|RIGHT|ORDER BY|GROUP BY|CREATE|ALTER|BEGIN|END|SET|"
                       r"UNION|AND|OR|ON|CASE|WHEN|ELSE|EXEC|INSERT|UPDATE|DELETE|T\d+\.)\b")
CODE_LINE_ANYCASE = re.compile(CODE_LINE.pattern, re.I)
CODE_MARK = re.compile(r"[=@<>(]|\b[A-Z]\d\.\w")
PROSE = re.compile(r"[a-z]{3,} [a-z]{3,} [a-z]{3,} [a-z]{3,}")
LATEX_TEXT = re.compile(r"^\$\$\s*\\text\s*\{(SELECT|ORDER|WHERE|FROM|GROUP)", re.I)


def is_code_line(block):
    if PROSE.search(block):
        return False
    return bool(CODE_LINE.match(block) or (CODE_LINE_ANYCASE.match(block) and CODE_MARK.search(block)))


def latex_to_text(block):
    """MinerU 偶尔把 SQL 识别成公式（$$\\text{SELECT …}$$）：去掉 LaTeX 外壳还原成文字。"""
    s = block.strip("$\n ")
    s = re.sub(r"\^\s*\{\\prime\}", "'", s)
    s = re.sub(r"\\(?:text|mathrm|mathsf|operatorname)\s*\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+", "", s).replace("{", "").replace("}", "")
    s = re.sub(r"(?<=\d) (?=[\d-])|(?<=-) (?=\d)", "", s)  # 「1 0 - 1 0」→「10-10」
    return re.sub(r"\s+", " ", s).strip()


def plain_code(text):
    """正文里的代码行带着 Markdown 转义（\\_、&lt;），放进代码块前还原。"""
    return re.sub(r"\\([_*\[\]#<>&|`~-])", r"\1", html.unescape(text))


LIST_START = ("#", "![", "|", "- ", "– ", "◾", "▪", "•", "■", "●")  # 这些开头的块不是上一段的延续
NOT_LIST_BODY = LIST_START + ("```", "<", "$$")  # 代码块、表格等不并进列表项：排版引擎不认缩进的围栏


def listify(blocks):
    """把列表符号转成 Markdown 列表：「◾ 」「▪ 」等（含整行加粗的「**◾ …**」）→ 一级，「– 」→ 二级。
    在翻译之后对原文和译文各做一遍（模型会保留这些符号），切段结果不变，已有翻译缓存继续有效。
    四个空格的缩进只有跟在列表项后面才是二级列表，否则会被排版成代码块，所以要看上一块。"""
    out = []
    for block in blocks:
        block = re.sub(rf"^\*\*{BULLET} ?", "- **", block)
        block = re.sub(rf"^{BULLET} ?", "- ", block)
        in_list = bool(out) and bool(re.match(r"- |    |\d+\. ", out[-1]))
        if block.startswith("– "):
            block = ("    - " if in_list else "- ") + block[2:]
        elif block.startswith("    ") and not in_list:
            block = block.lstrip()
        if block.startswith("- ") and "\n\n    " in block:  # 列表项的说明有多行时每行都要缩进
            head, body = block.split("\n\n    ", 1)
            block = head + "\n\n    " + re.sub(r"\n(?!    |\n)", "\n    ", body)
        out.append(block)
    return out


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
        self.titles = set()  # 章名：奇数页页眉常只印章名、不带编号

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
            self.titles.add(m.group(2))
            return f"# {m.group(1)} {m.group(2)}"
        if self.pending and block.startswith("#"):
            self.titles.add(block.lstrip("# "))
            title, self.pending = f"# {self.pending} {block.lstrip('# ')}", None
            return title
        if block in self.titles:
            return None
        m = SECTION.match(block)
        if m and (block.startswith("#") or len(block) < 100):
            if m.group(1) in self.seen:
                return None
            self.seen.add(m.group(1))
            depth = min(m.group(1).count(".") + 1, 4)
            return f"{'#' * depth} {m.group(1)} {m.group(2)}"
        if block.startswith("#") and not re.match(rf"^#+ ?{BULLET}", block):
            text = block.lstrip("# ")
            if text.endswith(":"):
                return text  # 冒号结尾的引导句被误标成标题
            return f"# {text}" if block.startswith("# ") else f"#### {text}"
        return block


def title_key(text):
    """比较标题用：去掉 #、标点、商标符号和大小写差异。"""
    return re.sub(r"[\W_]+", " ", text.lstrip("# ").lower()).strip()


class OutlineNormalizer:
    """按书签定标题层级。书签按文档顺序排队，标题块只和队头附近的书签比，避免各章都有的
    「Summary」之类配错；章书签「Chapter 1: 标题」输出为「# Chapter 1 标题」。"""
    LOOKAHEAD = 20

    def __init__(self, toc, chapter_words):
        chapter = re.compile(rf"^((?:{'|'.join(map(re.escape, chapter_words))}) (?:\d+|[A-Z]))\s*[:.—–-]?\s*(.*)$")
        self.queue, self.labels = [], set()
        toc = list(toc)
        self.roots = set()  # 被去掉的根书签（文档标题）：「文档标题 章名」式页脚要丢掉
        while toc and sum(level == toc[0][0] for level, *_ in toc) == 1:
            # 顶层只有一个书签（整份文档的标题）：去掉它，下面各层上提一级
            top = toc[0][0]
            self.roots.add(title_key(toc[0][1]))
            toc = [(level - 1 if level > top else level, t, p) for level, t, p in toc[1:]]
        self.chapters = {k for level, t, _ in toc if level == 1
                         for k in (title_key(t), re.sub(r"^\d+ ", "", title_key(t)))}  # 页脚里的章名常不带编号
        for level, title, _ in toc:
            m = chapter.match(title.strip())
            if m and m.group(2):
                self.labels.add(title_key(m.group(1)))
                self.queue.append((level, title_key(m.group(2)), " ".join(f"{m.group(1)} {m.group(2)}".split())))
            else:
                self.queue.append((level, title_key(title), " ".join(title.split())))
        self.pos = 0
        self.passed = set()  # 已出现过的章名：再出现就是页眉
        self.rest = None  # 折行标题：MinerU 只把第一行标成标题，第二行成了下一块

    def __call__(self, block):
        if PAGE_NUMBER.match(block):
            return None
        key = title_key(block)
        rest, self.rest = self.rest, None
        if rest and key == rest:
            return None
        if key in self.labels or (not block.startswith("#") and key in self.passed):
            return None  # 「Chapter 1」或章名式页眉
        if any(key == r or key.startswith(r + " ") and key[len(r) + 1:] in self.chapters for r in self.roots):
            return None  # 「文档标题 章名」式页脚
        if block.startswith("#") or len(block) < 120:
            for j in range(self.pos, min(self.pos + self.LOOKAHEAD, len(self.queue))):
                level, k, title = self.queue[j]
                wrapped = block.startswith("#") and len(key) >= 15 and k.startswith(key + " ")
                if k == key or wrapped:
                    self.rest = k[len(key):].strip() if wrapped else None
                    self.pos = j + 1
                    if level == 1:
                        self.passed.add(key)
                    return f"{'#' * min(level, 4)} {title}"
        if block.startswith("#") and not re.match(rf"^#+ ?{BULLET}", block):
            text = block.lstrip("# ")
            return text if text.endswith(":") else f"#### {text}"
        return block


def split_blocks(md):
    """按空行切块；代码围栏内部的空行不切。"""
    out, cur, fence = [], [], False
    for line in md.split("\n"):
        if line.strip().startswith("```"):
            fence = not fence
        if not line.strip() and not fence:
            if cur:
                out.append("\n".join(cur).strip())
            cur = []
        else:
            cur.append(line)
    if cur:
        out.append("\n".join(cur).strip())
    return [b for b in out if b]


def to_blocks(md, chapter_words, outline=None):
    """outline 给出 PDF 书签（[(层级, 标题, 页)]）时按书签定标题层级，否则按编号。"""
    raw = split_blocks(md)
    # 一半以上的页面都出现的短块是页眉页脚里的版式文字（如密级标记「PUBLIC」）
    pages = sum(bool(PAGE_MARK.match(b)) for b in raw)
    counts = collections.Counter(b for b in raw if len(b) <= 40 and not b.startswith(LIST_START))
    boiler = {b for b, n in counts.items() if pages >= 20 and n >= pages / 2}
    raw = [b for b in raw if b not in boiler]
    normalize = OutlineNormalizer(outline, chapter_words) if outline else Normalizer(chapter_words)
    blocks, after_page_break = [], False
    for block in raw:
        if PAGE_MARK.match(block):
            after_page_break = True
            continue
        block = normalize(block)
        if block is None:
            continue
        block = re.sub(rf"^#+ ?{BULLET} ?", "- **", block)  # 带方块符号的小标题其实是列表项
        if block.startswith("- **") and "**" not in block[4:]:
            block += "**"
        if LATEX_TEXT.match(block):
            block = latex_to_text(block)
        prev = blocks[-1] if blocks else ""
        if prev.startswith("```") and (
                is_code_line(block)
                or (after_page_break and block.startswith("```"))):
            # 代码续行（或跨页拆成两段的代码块）并回上一个代码块
            body = block.split("\n", 1)[1].rsplit("```", 1)[0] if block.startswith("```") else plain_code(block) + "\n"
            blocks[-1] = prev.rstrip()[:-3].rstrip("\n") + "\n" + body + "```"
        elif is_code_line(block):
            blocks.append(f"```\n{plain_code(block)}\n```")
        elif LIST_TITLE.fullmatch(prev) and not block.startswith(NOT_LIST_BODY):
            blocks[-1] = f"{prev}\n\n    {block}"  # 列表小标题和它的说明合成一个列表项
        elif (
            after_page_break and prev
            and not prev.startswith(("#", "![", "|", "```"))
            and not LIST_TITLE.fullmatch(prev)
            and not block.startswith(LIST_START + ("```",))
            and not SENTENCE_END.search(prev)
        ):
            # 上一段没以句末标点结束就视为被分页截断（德语名词大写，不能靠首字母判断）
            blocks[-1] = prev[:-1] + block if prev.endswith("-") else prev + " " + block
        else:
            blocks.append(block)
        after_page_break = False
    # 「Note」「Procedure」这类小标题，MinerU 时而标成标题时而当正文：多数是标题的就统一成标题
    minor = collections.Counter(b[5:] for b in blocks if b.startswith("#### "))
    return [f"#### {b}" if len(b) <= 30 and minor[b] >= 5 else b for b in blocks]
