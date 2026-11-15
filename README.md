# doctrans

**English** | [中文](README.zh-CN.md)

Translate long PDFs (books, manuals) into Chinese and re-typeset them as a readable book, entirely on your own machine. Parsing runs on a local [MinerU](https://github.com/opendatalab/MinerU), translation on a local model (Ollama or any OpenAI-compatible endpoint), layout on WeasyPrint. No document content leaves your computer.

> Status: alpha. The target language is currently fixed to Simplified Chinese; source documents in German and English have been tested. Most of the documentation is in Chinese for now.

## What you get

One folder per document:

| File | Content |
|---|---|
| `zh.pdf` | Chinese edition: original page size, generated table of contents with page numbers, three-level bookmarks, the original embedded figures |
| `bi.pdf` | Bilingual edition, paragraph by paragraph (source in grey above, Chinese below) |
| `zh.md` | The translation as clean Markdown, ready for a knowledge base |
| `qa/report.md` | Quality report: leftover markup in the PDF, paragraphs that look untranslated, glossary deviations, page and bookmark counts, sample page screenshots |

## How it differs from in-place PDF translators

Tools such as BabelDOC / PDFMathTranslate keep the original page layout and replace text in place. doctrans takes the other route: it rebuilds the document.

- **A book you can read from start to finish**: reflowed text, a real table of contents, bookmarks, a bilingual edition.
- **Markdown as a first-class output** for search and knowledge bases.
- **Glossary from the book's own index**: index entries are extracted and translated once, then enforced in every paragraph.
- **A QA report after every run**, so you know where to look instead of proofreading 1000 pages.
- **Privacy as a hard constraint**, enforced by tests: parsing refuses to run unless MinerU is in local mode with telemetry off, and only one module in the code base is allowed to open a network connection (to the model endpoint you configure).

Use it only for documents you have the right to process: your own material, vendor documentation, books you bought.

## Your data never enters the repository

The repository holds code only. Sources, configs, glossaries, caches and outputs live in a **separate data workspace**:

```
~/doctrans-data/
  inbox/      source PDFs
  configs/    one .toml per document (drafted by `doctrans inspect`)
  glossary/   glossary CSVs
  work/       outputs and caches
```

Three guards keep it that way: a whitelist `.gitignore`, a pre-commit hook that rejects documents, images, caches and large files, and an optional local denylist of sensitive strings. CI repeats the check on every push.

## Install (Linux / WSL2 / macOS)

```bash
git clone <this repo> && cd doctrans
git config core.hooksPath .githooks
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[test]"
```

- **MinerU 4.x** as a standalone tool: `uv tool install --python 3.12 mineru`, then lock it to local mode:
  `mineru config set parse_server.local.mode managed`, `mineru telemetry disable`, `mineru-kit models download --tier standard`.
- **Model server**: Ollama on Windows, macOS or Linux. A 27B-class model is recommended (about 16 GB of VRAM); smaller models work with lower quality. Thinking mode is switched off by doctrans.
- **Fonts**: Microsoft YaHei on WSL/Windows, PingFang or Noto Sans CJK on macOS/Linux, or set font files in the config.
- macOS: `brew install pango` first (needed by WeasyPrint).
- Native Windows: the test suite passes in CI, but WSL2 is the recommended setup.

Check the environment: `doctrans doctor configs/xxx.toml`

### Model server on another machine

The translation model does not have to run where doctrans runs. A common setup is to parse and typeset on a laptop or mini PC and send translation requests to a GPU machine on the same network. One line in the config:

```toml
[llm]
url = "http://192.168.1.50:11434/v1/chat/completions"   # address of that machine
```

Ollama on that machine must listen on the LAN (`OLLAMA_HOST=0.0.0.0`) and port 11434 must be open in its firewall. Document text then travels unencrypted across your network, so only point this at a machine you control. Parsing (MinerU) always runs locally on the machine running doctrans.

## Usage

```bash
cd ~/doctrans-data
doctrans inspect inbox/*.pdf                # 1. inspect, write a draft configs/<name>.toml
#    review the draft: page ranges (original TOC and index are skipped), domain, chapter words
doctrans glossary configs/xxx.toml 1035-1052 -o glossary/xxx/index.csv   # 2. optional: glossary from the index pages
doctrans run configs/xxx.toml               # 3. try one chapter first, then the whole book
doctrans run configs/*.toml                 # 4. batch: documents are queued, one failure does not stop the rest
doctrans render configs/xxx.toml            # re-typeset only after style changes (1-3 minutes, no model calls)
```

Long runs in the background: `setsid nohup doctrans run configs/*.toml > batch.log 2>&1 &`. If a run is interrupted, start the same command again: parse results, images and every translated paragraph are cached.

Config fields: [`examples/example.toml`](examples/example.toml). Glossary format: [`examples/glossary_example.csv`](examples/glossary_example.csv) (columns `source,target,tgt_lng`, UTF-8 with BOM).

## Documents it has been run on

| Kind | Language | Pages | Heading detection |
|---|---|---|---|
| Technical book with numbered sections | German | ~1000 | section numbers |
| Technical book with unnumbered sections and many code listings | English | ~350 | PDF bookmarks |
| Publicly available vendor administration guide | English | ~280 | single root bookmark, chapters titled by bare numbers |

No document or translation is included in this repository. To reproduce a run yourself, use documentation a vendor publishes openly, for example the SAP Business One administrator's guide on the SAP Help Portal: [`examples/public-admin-guide.toml`](examples/public-admin-guide.toml) contains the download address and a ready-to-use config.

## Speed

A book of about 1000 pages on an RTX 4080 (16 GB) with a 27B model: parsing about 30 minutes, translation about 6 hours, typesetting about 1.5 minutes.

## Known limitations

- Output language is Simplified Chinese only.
- Text inside screenshots stays untranslated; page numbers do not match the original.
- Heading levels come from section numbers (`3.1`, `3.1.1`) or PDF bookmarks. PDFs with neither need an extension of `structure.py`.
- Code blocks are kept verbatim; tables split across pages become two tables.
- Scanned PDFs, two-column layouts and formula-heavy documents are untested.
- PDF only.

## Documentation (Chinese)

- [Operations manual](docs/manual.md): install, daily use, troubleshooting, upgrades, offline migration.
- [Dependencies and upgrade procedures](docs/dependencies.md), [Security policy](SECURITY.md).
- [Contributing](CONTRIBUTING.md): three non-negotiable rules, and which parts of the code are open for direct changes.
- [Roadmap](docs/roadmap.md).

## License

AGPL-3.0, because PyMuPDF and MinerU are AGPL. Using the tool on your own machine without distributing it puts no obligations on you.
