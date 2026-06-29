# translate-book

An AI skill that translates entire books (PDF, DOCX, EPUB) into any language using parallel sub-agents, then produces a **beautiful print-quality PDF** with professional typography.

Works with **Claude Code** and **Codex** (OpenClaw-compatible skill format).

---

## Attribution

This project is a fork of [**deusyu/translate-book**](https://github.com/deusyu/translate-book), which was itself inspired by [wizlijun/claude_translater](https://github.com/wizlijun/claude_translater).

**Changes in this fork:**
- New print template (`template_print.html`) — 6×9 inch book layout, Navy + Gold color scheme, DejaVu Serif body, Lato headings
- Running chapter headers; first-line small-caps opener (replaces drop cap — drop caps break multi-char consonant clusters in Vietnamese, German, etc.)
- HTML artifact cleanup: `[]` placeholder anchors from EPUB converters are stripped before PDF rendering
- `--pdf-only` flag in `merge_and_build.py` — skip DOCX/EPUB, produce only PDF
- Default skill build command uses `--pdf-only`

Original MIT license is preserved. See [LICENSE](LICENSE).

---

## How It Works

```
Input (PDF / DOCX / EPUB)
        │
        ▼
  Calibre ebook-convert → HTMLZ → HTML → Markdown
        │
        ▼
  Split into chunks  (chunk0001.md, chunk0002.md, …)
  manifest.json tracks SHA-256 hashes
        │
        ▼
  Parallel sub-agents  (8 concurrent by default)
  each agent: read 1 chunk → translate → write output_chunk*.md
  glossary.json ensures consistent terminology across chunks
        │
        ▼
  Validate (manifest hash check, 1-to-1 source ↔ output)
        │
        ▼
  Merge → Pandoc → HTML → WeasyPrint PDF
  (6×9 inch, professional typography, running chapter headers)
```

---

## Installation

### Claude Code

```bash
claude skills install https://github.com/trananhtung/translate-book
```

Or clone manually:

```bash
git clone https://github.com/trananhtung/translate-book \
  ~/.claude/skills/translate-book
```

### Codex (OpenClaw)

```bash
codex skills install https://github.com/trananhtung/translate-book
```

Or clone manually:

```bash
git clone https://github.com/trananhtung/translate-book \
  ~/.codex/skills/translate-book
```

### System dependencies

```bash
# Calibre — EPUB/DOCX/PDF conversion (required for input parsing)
sudo apt install calibre        # Ubuntu / Debian
brew install --cask calibre     # macOS

# Pandoc — Markdown → HTML
sudo apt install pandoc

# WeasyPrint — high-quality PDF rendering
pip install weasyprint

# Optional Python helpers
pip install beautifulsoup4 markdown
```

---

## Usage

### In Claude Code

```
/translate-book translate this book to Vietnamese and create a beautiful PDF
```

Or with an explicit file path:

```
/translate-book path/to/book.epub
```

### In Codex

```
/translate-book path/to/book.pdf --lang vi
```

### Direct CLI

**Step 1 — Convert input to Markdown chunks:**
```bash
python3 scripts/convert.py path/to/book.epub --olang vi
```

**Step 2 — Translate chunks** (handled by the skill's parallel sub-agents)

**Step 3 — Merge and build PDF:**
```bash
python3 scripts/merge_and_build.py \
  --temp-dir "book_temp" \
  --title "Tên Sách Dịch" \
  --pdf-only \
  --cleanup
```

---

## PDF Output

The built-in `template_print.html` produces a 6×9 inch trade-paperback PDF via WeasyPrint:

| Property | Value |
|---|---|
| Page size | 6 × 9 inch |
| Body font | DejaVu Serif, 10.8pt, line-height 1.80 |
| Heading font | Lato / Liberation Sans |
| Accent color | Gold `#c8a96e` |
| Heading color | Navy `#1a1a2e` |
| Running header | Chapter title, italic, centered |
| Chapter opener | First line in small-caps |
| Blockquote style | Gold left border + large opening quote mark |

To use a custom template, replace `scripts/template_print.html` with any WeasyPrint-compatible HTML/CSS file that contains `$body$`, `$title$`, and `$lang$` placeholders.

---

## Key Features

- **Resumable** — interrupted runs continue from where they stopped via `run_state.json`
- **Glossary** — `glossary.json` keeps terminology consistent across all chunks
- **Manifest validation** — SHA-256 hashes verify chunk integrity before merging
- **Neighbor context** — sub-agents see the tail of the previous chunk and head of the next for pronoun and entity continuity
- **Meta observations** — sub-agents report new entities and terminology conflicts; merged into the glossary between batches
- **PDF-only mode** — `--pdf-only` skips DOCX/EPUB generation (faster, no Calibre dependency for final output)

---

## merge_and_build.py Options

| Flag | Default | Description |
|---|---|---|
| `--pdf-only` | off | Generate only PDF, skip DOCX and EPUB |
| `--cleanup` | off | Delete intermediate chunk files after a successful build |
| `--title` | from config | Override translated book title |
| `--author` | from config | Override author name |
| `--lang` | from config | Override language code (`vi`, `zh`, `fr`, …) |
| `--cover` | none | Cover image path (EPUB only) |
| `--export-name` | none | Filename stem for output alias copies |

---

## Supported Languages

Any language supported by Claude or Codex. The chunking pipeline and glossary are language-agnostic.

PDF rendering uses DejaVu Serif, which covers Latin, Cyrillic, Greek, and extended Unicode. For CJK output you may need to install additional system fonts (e.g. Noto Serif CJK).

---

## License

MIT — see [LICENSE](LICENSE).

Original work © 2025 Rainman — [deusyu/translate-book](https://github.com/deusyu/translate-book)  
Modifications © 2025 Tran Anh Tung — [github.com/trananhtung](https://github.com/trananhtung)
