"""按段落批量翻译：带术语表、逐批写缓存（断点续跑）、格式错误自动重试，批量失败退回逐段。"""
import csv
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from .llm import ask_json

SYSTEM = """You translate a {source_lang} technical book{domain} into Simplified Chinese.
Rules:
- Translate every entry completely, fluently and accurately; add nothing, omit nothing.
- Keep Markdown syntax (#, **, -, numbering, tables, HTML tags) unchanged.
- Do not translate product names, release numbers, abbreviations or code.
- {ui_rule}
- Figure and table captions "{figure_word} N.N: …" become "图 N.N：…"; table captions become "表 N.N：…".
- Glossary terms are mandatory.
Reply ONLY with a JSON array: [{{"i": <index>, "zh": "..."}}]"""


UI_RULES = {
    "auto": 'UI labels, menu paths and field names in quotes (»…«, „…“, "…") are rendered as 「…」.',
    "translate": 'UI labels, menu paths, tab, button and field names (in quotes or bold) are translated into the wording '
                 'of the Chinese product UI and rendered as 「…」.',
    "both": 'UI labels, menu paths, tab, button and field names (in quotes or bold) are translated into the wording of '
            'the Chinese product UI, followed by the original in parentheses, and rendered as 「中文 (Original)」, '
            'e.g. 「常规设置 (General Settings)」. Product names stay untranslated.',
}
LATIN_LABEL = re.compile(r"「[^」一-鿿]*[A-Za-z]{3,}[^」一-鿿]*」")  # 还留着纯外文的界面名称


def load_glossary(paths):
    """读取术语表 CSV（列 source,target；UTF-8，可带 BOM）。先加载的文件优先；长词在前，避免短词抢先匹配。"""
    entries = {}
    for path in paths:
        with open(path, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                entries.setdefault(r["source"], r["target"])
    return sorted(entries.items(), key=lambda kv: -len(kv[0]))


def shape(text):
    """段落的结构特征：标题层级、表格行数和单元格数、开头的列表/编号符号。译文必须和原文一致。"""
    marker = re.match(r"\s*(?:[-–◾▪•■●] |\d+\. |[a-z]\. )?", text).group()
    marker = re.sub(r"\d+", "1", marker)
    return (len(re.match(r"#*", text).group()), text.count("<tr"), text.count("<td") + text.count("<th"), marker)


def block_key(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def load_cache(path):
    """返回 (译文, 界面名称模式)：{段落哈希: 译文}、{段落哈希: 翻译时的 ui_labels}。同一段有多行时后写的生效。"""
    cache, modes = {}, {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                cache[rec["k"]] = rec["zh"]
                modes[rec["k"]] = rec.get("ui", "auto")
    return cache, modes


def translate(cfg, blocks, glossary, log, offline=False):
    """返回与 blocks 一一对应的译文。offline=True 时不调模型，缺译文的段保留原文（只重排版用）。"""
    cache_path = cfg.output / "translate_cache.jsonl"
    cache, modes = load_cache(cache_path)
    is_code = lambda b: b.startswith("```")  # 代码原样保留，不送模型

    def missing(b):
        k = block_key(b)
        if k not in cache:
            return True
        # 改了 ui_labels：只重译还留着纯外文界面名称、且没按新模式翻过的段，其余继续用缓存
        return (not offline and cfg.ui_labels != "auto" and modes[k] != cfg.ui_labels
                and bool(LATIN_LABEL.search(cache[k])))

    todo = [i for i, b in enumerate(blocks) if not b.startswith("![") and not is_code(b) and missing(b)]
    log(f"共 {len(blocks)} 段，缓存命中 {len(blocks) - len(todo)}，待翻译 {len(todo)}")
    if offline:
        if todo:
            log(f"警告: {len(todo)} 段没有译文，保留原文")
        return [b if is_code(b) else cache.get(block_key(b), b) for b in blocks]

    system_base = SYSTEM.format(source_lang=cfg.source_lang, figure_word=cfg.figure_word, ui_rule=UI_RULES[cfg.ui_labels],
                                domain=f" about {cfg.domain}" if cfg.domain else "")

    def run(ids):
        texts = [blocks[i] for i in ids]
        joined = "\n".join(texts)
        terms = [f"{s} = {t}" for s, t in glossary if s != t and re.search(rf"\b{re.escape(s)}\b", joined)]
        system = system_base + ("\nGlossary:\n" + "\n".join(terms) if terms else "")
        user = json.dumps([{"i": k, "src": t} for k, t in enumerate(texts)], ensure_ascii=False)
        for attempt in range(3):
            try:
                out = {int(x["i"]): x["zh"] for x in ask_json(cfg.llm_url, cfg.model, system, user)}
                if set(out) != set(range(len(texts))):
                    log(f"  条数不符 {len(out)}/{len(texts)}，重试")
                    continue
                broken = [k for k in out if shape(out[k]) != shape(texts[k])]
                if not broken or (attempt == 2 and len(ids) == 1):  # 单段重试到头仍不符就接受，由质检报告提示
                    return {ids[k]: v for k, v in out.items()}
                log(f"  格式不符 {len(broken)} 段（标题/表格/列表符号与原文不一致），重试")
            except (ValueError, KeyError, TypeError) as e:
                log(f"  解析失败 {e}，重试")
        if len(ids) > 1:
            log(f"  逐段回退 {len(ids)} 段")
            return {i: run([i])[i] for i in ids}
        return {ids[0]: None}  # 彻底失败：不进缓存，保留原文，下次运行再试

    chunks = [todo[k:k + cfg.batch] for k in range(0, len(todo), cfg.batch)]
    with ThreadPoolExecutor(cfg.parallel) as pool, open(cache_path, "a", encoding="utf-8") as cf:
        futures = [pool.submit(run, c) for c in chunks]
        for n, fut in enumerate(as_completed(futures), 1):
            for i, zh in fut.result().items():
                if zh is None:
                    log(f"  第 {i} 段翻译失败，保留原文")
                    continue
                cache[block_key(blocks[i])] = zh
                cf.write(json.dumps({"k": block_key(blocks[i]), "zh": zh, "ui": cfg.ui_labels}, ensure_ascii=False) + "\n")
            cf.flush()
            log(f"翻译 {n}/{len(chunks)} 批")
    return [b if is_code(b) else cache.get(block_key(b), b) for b in blocks]
