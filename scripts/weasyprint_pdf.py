#!/usr/bin/env python3
"""
weasyprint_pdf.py — Generate a typographically refined PDF using WeasyPrint.

Takes the book's book_doc.html, wraps it in template_print.html,
and renders a print-quality PDF with proper page layout and typography.

Usage:
    python3 weasyprint_pdf.py <book_doc.html> -o <output.pdf>
"""

import os
import sys
import re
import argparse
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PRINT = os.path.join(SCRIPT_DIR, 'template_print.html')


def check_weasyprint():
    try:
        import weasyprint
        return weasyprint
    except ImportError:
        return None


def clean_html_body(body):
    """Remove EPUB artifacts that pollute the rendered output."""
    # [] placeholder anchors left by EPUB-to-HTML converters
    body = re.sub(r'\[\]', '', body)
    # Empty <a> and <span> tags (orphaned anchor shells)
    body = re.sub(r'<a\s+[^>]*>\s*</a>', '', body)
    body = re.sub(r'<span\s+[^>]*>\s*</span>', '', body)
    return body


def extract_from_html(html_path):
    """Extract title, lang, and body content from an HTML file."""
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()

    title_match = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else Path(html_path).stem

    lang_match = re.search(r'<html[^>]*\blang=["\']([^"\']*)["\']', content, re.IGNORECASE)
    lang = lang_match.group(1).strip() if lang_match else 'vi'

    body_match = re.search(r'<body[^>]*>(.*?)</body>', content, re.DOTALL | re.IGNORECASE)
    body = body_match.group(1).strip() if body_match else content
    body = clean_html_body(body)

    return title, lang, body


def apply_print_template(body, title, lang):
    """Wrap body content in the print template."""
    if not os.path.exists(TEMPLATE_PRINT):
        raise FileNotFoundError(f"Print template not found: {TEMPLATE_PRINT}")
    with open(TEMPLATE_PRINT, 'r', encoding='utf-8') as f:
        template = f.read()
    html = template.replace('$body$', body)
    html = html.replace('$title$', title)
    html = html.replace('$lang$', lang)
    return html


def generate_pdf(html_path, output_path, verbose=True):
    """Generate a print-quality PDF from an HTML file using WeasyPrint."""
    wp = check_weasyprint()
    if not wp:
        print("ERROR: WeasyPrint not installed. Run: pip install weasyprint")
        return False

    html_path = str(Path(html_path).resolve())
    output_path = str(Path(output_path).resolve())

    if verbose:
        print(f"Input  : {html_path}")
        print(f"Output : {output_path}")

    title, lang, body = extract_from_html(html_path)
    if verbose:
        print(f"Title  : {title}")
        print(f"Lang   : {lang}")

    final_html = apply_print_template(body, title, lang)
    base_url = str(Path(html_path).parent)

    if verbose:
        print(f"Base URL (images): {base_url}")
        print("Rendering PDF with WeasyPrint…")

    try:
        document = wp.HTML(string=final_html, base_url=base_url)
        document.write_pdf(output_path)
    except Exception as e:
        print(f"ERROR: WeasyPrint failed: {e}")
        return False

    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        if verbose:
            print(f"✓  PDF written: {output_path}  ({size:,} bytes, {size/1024/1024:.1f} MB)")
        return True
    else:
        print("ERROR: PDF file was not created.")
        return False


def generate_pdf_with_lang_override(html_path, output_path, lang_override=None, verbose=True):
    """Like generate_pdf() but allows overriding the lang attribute."""
    wp = check_weasyprint()
    if not wp:
        print("ERROR: WeasyPrint not installed. Run: pip install weasyprint")
        return False

    html_path = str(Path(html_path).resolve())
    output_path = str(Path(output_path).resolve())

    if verbose:
        print(f"Input  : {html_path}")
        print(f"Output : {output_path}")

    title, lang, body = extract_from_html(html_path)
    if lang_override:
        lang = lang_override
    if verbose:
        print(f"Title  : {title}")
        print(f"Lang   : {lang}")

    final_html = apply_print_template(body, title, lang)
    base_url = str(Path(html_path).parent)

    if verbose:
        print(f"Base URL (images): {base_url}")
        print("Rendering PDF with WeasyPrint…")

    try:
        document = wp.HTML(string=final_html, base_url=base_url)
        document.write_pdf(output_path)
    except Exception as e:
        print(f"ERROR: WeasyPrint failed: {e}")
        return False

    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        if verbose:
            print(f"✓  PDF written: {output_path}  ({size:,} bytes, {size/1024/1024:.1f} MB)")
        return True
    else:
        print("ERROR: PDF file was not created.")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Generate a beautiful print-quality PDF using WeasyPrint'
    )
    parser.add_argument('html_file', help='Input HTML file (book_doc.html or similar)')
    parser.add_argument('-o', '--output', required=True, help='Output PDF path')
    parser.add_argument('--lang', default=None, help='Override language code (e.g. vi, en, fr)')
    parser.add_argument('-q', '--quiet', action='store_true', help='Suppress progress output')
    args = parser.parse_args()

    if not os.path.exists(args.html_file):
        print(f"ERROR: Input file not found: {args.html_file}")
        sys.exit(1)

    if args.lang:
        ok = generate_pdf_with_lang_override(
            args.html_file, args.output, lang_override=args.lang, verbose=not args.quiet
        )
    else:
        ok = generate_pdf(args.html_file, args.output, verbose=not args.quiet)

    if not ok:
        sys.exit(1)


if __name__ == '__main__':
    main()
