#!/usr/bin/env python3
"""
pdf_qa.py — Render a built book PDF to page images and run cheap layout checks,
so a QA sub-agent (with vision) can inspect the pages for presentation errors.

This backs the SKILL.md "QA Visual Check Loop" step. It does two jobs:

  render  Pick a smart sample of pages, run text-based (programmatic) checks on
          every page, render the sampled pages to PNG, and write qa_report.json.
  clean   Delete the cached build artifacts (book.html, book_doc.html, book.pdf)
          so the next merge_and_build.py run regenerates them from the current
          template and output.md. Required because the build skip-logic is
          mtime-based and will NOT regenerate on a template-only edit.

Only depends on the poppler-utils CLIs (pdfinfo, pdftotext, pdftoppm) that the
skill already requires, plus optional mutool for chapter detection. No extra
Python packages.

Usage:
    python3 pdf_qa.py render <temp_dir> [--iteration N] [--max-pages M]
                                        [--dpi D] [--pdf PATH]
    python3 pdf_qa.py clean  <temp_dir>
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

# Build artifacts that must be removed to force a clean rebuild (see module docstring).
BUILD_ARTIFACTS = ["book.html", "book_doc.html", "book.pdf"]

# --- programmatic check thresholds -------------------------------------------
NEAR_BLANK_CHARS = 20      # stripped text shorter than this -> near-blank page
OVERLONG_TOKEN = 40        # a single whitespace-free run longer than this -> overflow risk
DEFAULT_MAX_PAGES = 24     # per-iteration render budget (cost ceiling)
DEFAULT_DPI = 150

# Markdown that leaked into the rendered text (should have become formatting).
# High-signal patterns only, to avoid flagging legitimate prose.
_MD_LEAK_PATTERNS = [
    (re.compile(r'(?m)^\s{0,3}#{1,6}\s+\S'), 'heading_hash'),   # "## Title"
    (re.compile(r'\*\*\S'), 'bold_asterisks'),                  # "**bold"
    (re.compile(r'\]\(https?://'), 'inline_link'),              # "](http..."
    (re.compile(r'!\[[^\]]*\]\('), 'image_markdown'),           # "![alt]("
    (re.compile(r'(?m)^\s*```'), 'code_fence'),                 # code fence
]
_OVERLONG_RE = re.compile(r'\S{%d,}' % OVERLONG_TOKEN)


def _require(bin_name):
    if shutil.which(bin_name) is None:
        sys.stderr.write(
            f"ERROR: required tool '{bin_name}' not found on PATH "
            f"(install poppler-utils).\n")
        sys.exit(2)


def _run(cmd, capture=True):
    return subprocess.run(cmd, capture_output=capture, text=True)


def get_page_count(pdf):
    _require("pdfinfo")
    res = _run(["pdfinfo", pdf])
    if res.returncode != 0:
        sys.stderr.write(f"ERROR: pdfinfo failed: {res.stderr.strip()}\n")
        sys.exit(2)
    m = re.search(r'^Pages:\s+(\d+)', res.stdout, re.MULTILINE)
    if not m:
        sys.stderr.write("ERROR: could not read page count from pdfinfo.\n")
        sys.exit(2)
    return int(m.group(1))


def extract_page_texts(pdf, page_count):
    """Return a list of per-page text, indexed 0..page_count-1.

    One pdftotext call; pages are separated by form-feed (\\x0c)."""
    _require("pdftotext")
    res = _run(["pdftotext", pdf, "-"])
    if res.returncode != 0:
        sys.stderr.write(f"WARNING: pdftotext failed: {res.stderr.strip()}\n")
        return ["" for _ in range(page_count)]
    parts = res.stdout.split("\x0c")
    # Trailing form-feed yields an extra empty segment; normalize length.
    if len(parts) > page_count:
        parts = parts[:page_count]
    while len(parts) < page_count:
        parts.append("")
    return parts


def get_chapter_pages(pdf):
    """Best-effort chapter-start page numbers from the PDF outline via mutool.

    Returns [] if mutool is absent or the PDF has no outline."""
    if shutil.which("mutool") is None:
        return []
    res = _run(["mutool", "show", pdf, "outline"])
    if res.returncode != 0 or not res.stdout.strip():
        return []
    pages = []
    for line in res.stdout.splitlines():
        # mutool outline lines reference a page as "#<page>" or "#<page>,...".
        m = re.search(r'#(\d+)', line)
        if m:
            pages.append(int(m.group(1)))
    return sorted(set(pages))


def check_page_text(text):
    """Return a list of programmatic flag strings for one page's text."""
    flags = []
    stripped = text.strip()
    if len(stripped) < NEAR_BLANK_CHARS:
        flags.append("near_blank")
    if "�" in text:
        flags.append("replacement_char")
    for pat, name in _MD_LEAK_PATTERNS:
        if pat.search(text):
            flags.append("md_leak:" + name)
    if _OVERLONG_RE.search(text):
        flags.append("overlong_token")
    return flags


def select_pages(page_count, page_flags, chapter_pages, max_pages):
    """Priority-ordered page selection. Returns (selected_sorted, dropped_count, reasons).

    Priority: anomaly (flagged) pages > structural (front/back/chapter) > even spread.
    """
    ordered = []          # (page, reason) in priority order, may contain dups
    # 1. anomalies first — these are the whole point of QA
    for p in range(1, page_count + 1):
        if page_flags.get(p):
            ordered.append((p, "anomaly:" + ",".join(page_flags[p])))
    # 2. structural landmarks
    for p in (1, 2, 3):
        if p <= page_count:
            ordered.append((p, "front_matter"))
    for p in (page_count - 1, page_count):
        if p >= 1:
            ordered.append((p, "back_matter"))
    for p in chapter_pages:
        if 1 <= p <= page_count:
            ordered.append((p, "chapter_start"))
    # 3. even spread across the book
    step = max(1, page_count // 12)
    for p in range(1, page_count + 1, step):
        ordered.append((p, "even_sample"))

    selected = []
    reasons = {}
    for p, reason in ordered:
        if p not in reasons:
            reasons[p] = reason
            selected.append(p)
    dropped = 0
    if len(selected) > max_pages:
        dropped = len(selected) - max_pages
        selected = selected[:max_pages]
    return sorted(selected), dropped, reasons


def render_pages(pdf, pages, out_dir, dpi):
    """Render each page to <out_dir>/pageNNNN.png. Returns {page: path}."""
    _require("pdftoppm")
    os.makedirs(out_dir, exist_ok=True)
    result = {}
    for p in pages:
        stem = os.path.join(out_dir, f"page{p:04d}")
        res = _run([
            "pdftoppm", "-png", "-r", str(dpi),
            "-f", str(p), "-l", str(p), "-singlefile", pdf, stem,
        ])
        png = stem + ".png"
        if res.returncode == 0 and os.path.exists(png):
            result[p] = png
        else:
            sys.stderr.write(
                f"WARNING: failed to render page {p}: {res.stderr.strip()}\n")
    return result


def cmd_render(args):
    temp_dir = args.temp_dir
    pdf = args.pdf or os.path.join(temp_dir, "book.pdf")
    if not os.path.exists(pdf):
        sys.stderr.write(f"ERROR: PDF not found: {pdf}\n")
        sys.exit(2)

    page_count = get_page_count(pdf)
    if page_count < 1:
        sys.stderr.write("ERROR: PDF has no pages.\n")
        sys.exit(2)

    texts = extract_page_texts(pdf, page_count)
    page_flags = {}
    programmatic_findings = []
    for i, text in enumerate(texts):
        p = i + 1
        flags = check_page_text(text)
        if flags:
            page_flags[p] = flags
            programmatic_findings.append({
                "page": p,
                "flags": flags,
                "text_len": len(text.strip()),
            })

    chapter_pages = get_chapter_pages(pdf)
    selected, dropped, reasons = select_pages(
        page_count, page_flags, chapter_pages, args.max_pages)

    out_dir = os.path.join(temp_dir, "qa_images", f"iter{args.iteration}")
    # Fresh directory per iteration so stale images never mislead the QA agent.
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    rendered = render_pages(pdf, selected, out_dir, args.dpi)

    report = {
        "pdf": os.path.abspath(pdf),
        "iteration": args.iteration,
        "page_count": page_count,
        "dpi": args.dpi,
        "max_pages": args.max_pages,
        "dropped_pages": dropped,
        "images_dir": os.path.abspath(out_dir),
        "rendered_pages": [
            {"page": p, "path": rendered[p], "reason": reasons[p],
             "flags": page_flags.get(p, [])}
            for p in selected if p in rendered
        ],
        "programmatic_findings": programmatic_findings,
    }
    report_path = os.path.join(temp_dir, "qa_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Human/orchestrator-friendly summary.
    print(f"QA render — iteration {args.iteration}")
    print(f"  PDF: {pdf} ({page_count} pages)")
    print(f"  Programmatic findings: {len(programmatic_findings)} page(s) flagged")
    for f in programmatic_findings[:20]:
        print(f"    page {f['page']}: {', '.join(f['flags'])}")
    if len(programmatic_findings) > 20:
        print(f"    ... and {len(programmatic_findings) - 20} more")
    print(f"  Rendered {len(rendered)} page(s) -> {out_dir}")
    if dropped:
        print(f"  NOTE: {dropped} candidate page(s) dropped by --max-pages "
              f"budget ({args.max_pages}).")
    print(f"  Report: {report_path}")
    print("  Image files to inspect:")
    for p in selected:
        if p in rendered:
            print(f"    {rendered[p]}")


def cmd_clean(args):
    temp_dir = args.temp_dir
    removed = []
    for name in BUILD_ARTIFACTS:
        path = os.path.join(temp_dir, name)
        if os.path.exists(path):
            os.remove(path)
            removed.append(name)
    if removed:
        print(f"Removed cached build artifacts: {', '.join(removed)}")
    else:
        print("No cached build artifacts to remove.")


def main():
    parser = argparse.ArgumentParser(
        description="Render a book PDF to page images and run layout QA checks.")
    sub = parser.add_subparsers(dest="command", required=True)

    pr = sub.add_parser("render", help="Sample + render pages and write qa_report.json")
    pr.add_argument("temp_dir", help="Temp directory containing book.pdf")
    pr.add_argument("--iteration", type=int, default=1, help="QA loop iteration number")
    pr.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES,
                    help=f"Max pages to render per iteration (default {DEFAULT_MAX_PAGES})")
    pr.add_argument("--dpi", type=int, default=DEFAULT_DPI,
                    help=f"Render resolution (default {DEFAULT_DPI})")
    pr.add_argument("--pdf", default=None, help="Override PDF path (default <temp_dir>/book.pdf)")
    pr.set_defaults(func=cmd_render)

    pc = sub.add_parser("clean", help="Delete cached build artifacts to force rebuild")
    pc.add_argument("temp_dir", help="Temp directory")
    pc.set_defaults(func=cmd_clean)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
