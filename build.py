#!/usr/bin/env python3
"""Build the LoongArch instruction quick-reference PDF from content.yaml."""

from __future__ import annotations

import html
import json
import pathlib
import re
import subprocess

import yaml

try:
    from pypdf import PdfReader, PdfWriter
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "pypdf is required to rebuild the PDF outline; "
        "install it with `pip install -r requirements.txt`."
    ) from exc

ROOT = pathlib.Path(__file__).resolve().parent
BUILD_DIR = ROOT / "build"
HTML_PATH = BUILD_DIR / "manual.html"
PDF_PATH = ROOT / "loongarch-quickref.pdf"
PAGES_PATH = BUILD_DIR / "toc_pages.json"

def inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)


def anchor(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def validate_base(insn: dict) -> None:
    value = 0
    for field in insn["encoding"]:
        high, low = field["bits"]
        span = high - low + 1
        if field.get("kind") != "fixed":
            continue
        bits = str(field["value"])
        if len(bits) != span or set(bits) - {"0", "1"}:
            raise ValueError(
                f"{insn['mnemonic']}: fixed field {high}:{low} is not {span} binary digits"
            )
        value |= int(bits, 2) << low

    base = int(str(insn["base"]), 0)
    if value != base:
        raise ValueError(
            f"{insn['mnemonic']}: fixed fields form 0x{value:08x}, "
            f"but base is 0x{base:08x}"
        )


def render_encoding(fields: list[dict]) -> str:
    expected_high = 31
    for field in fields:
        high, low = field["bits"]
        if high != expected_high:
            raise ValueError(f"encoding fields are not contiguous at bit {expected_high}")
        if low > high:
            raise ValueError(f"invalid bit range {high}:{low}")
        expected_high = low - 1
    if expected_high != -1:
        raise ValueError("encoding fields do not cover bits 31:0")

    cols = "".join('<col style="width:3.125%">' for _ in range(32))
    heads = []
    cells = []
    for field in fields:
        high, low = field["bits"]
        span = high - low + 1
        heads.append(
            f'<th colspan="{span}">'
            f'<span class="hi">{high}</span><span class="lo">{low}</span>'
            f"</th>"
        )
        kind = field.get("kind", "reg")
        value = html.escape(str(field["value"]), quote=False)
        cells.append(f'<td colspan="{span}" class="{kind}">{value}</td>')

    return f"""
      <table class="bit-table">
        <colgroup>{cols}</colgroup>
        <thead><tr>{''.join(heads)}</tr></thead>
        <tbody><tr>{''.join(cells)}</tr></tbody>
      </table>
    """


def render_instruction(insn: dict) -> str:
    validate_base(insn)
    ident = anchor(insn["mnemonic"])
    isa = " / ".join(insn["isa"])
    note = ""
    if insn.get("note"):
        note = f'<div class="note">{inline(insn["note"])}</div>'

    extra_tags = ""
    for tag in insn.get("extra_tags", []):
        extra_tags += f'<span class="sep">·</span><span class="tag">{html.escape(tag)}</span>'

    example_comment = ""
    if insn.get("example_comment"):
        example_comment = (
            f'      <span class="comment">{html.escape(insn["example_comment"])}</span>'
        )

    pseudocode = html.escape(insn["pseudocode"].strip(), quote=False)
    formula = html.escape(insn["encoding_value"], quote=False)

    return f"""
    <section class="insn" id="{ident}">
      <header class="insn-head">
        <h2 class="insn-title"><span class="mnemonic">{html.escape(insn["mnemonic"])}</span> <span class="operands">{html.escape(insn["operands"])}</span></h2>
        <div class="equation"><code>{html.escape(insn["equation"])}</code></div>
      </header>

      <div class="insn-meta">
        <span class="cn-name">{html.escape(insn["cn_name"])}</span>
        <span class="en-name">（{html.escape(insn["en_name"])}）</span>
        <span class="sep">·</span><span class="tag">{html.escape(insn["format"])}</span>
        <span class="sep">·</span><span class="tag">{html.escape(isa)}</span>{extra_tags}
      </div>

      <p class="description">{inline(insn["description"])}</p>
      {note}

      <div class="detail">
        <div class="detail-label">编码</div>
        <div class="encoding">{render_encoding(insn["encoding"])}</div>

        <div class="detail-label">编码值</div>
        <div class="formula"><code>{formula}</code></div>

        <div class="detail-label">汇编示例</div>
        <pre>{html.escape(insn["example"])}{example_comment}</pre>

        <div class="detail-label">语义伪代码</div>
        <pre>{pseudocode}</pre>
      </div>
    </section>
    """


def render_chapter(chapter: dict) -> str:
    title = chapter["title"]
    note = ""
    if chapter.get("note"):
        note = f'<div class="chapter-note">{inline(chapter["note"])}</div>'

    parts = ['<section class="chapter">']
    parts.append(f'<h1 class="chapter-title">{html.escape(title)}</h1>')
    parts.append(note)

    for insn in chapter["instructions"]:
        note_block = chapter.get("section_notes", {}).get(insn["mnemonic"])
        if note_block:
            parts.append(
                '<div class="section-note">'
                f'<div class="section-note-title">{html.escape(note_block["title"])}</div>'
                f'<div class="section-note-body">{note_block["html"]}</div>'
                "</div>"
            )
        parts.append(render_instruction(insn))

    parts.append("</section>")
    return "\n".join(parts)


def render_toc(chapters: list[dict], pages: dict[str, int]) -> str:
    parts = ['<section class="toc">', '<h1 class="toc-title">目录</h1>', '<div class="toc-columns">']
    for chapter in chapters:
        letter = chapter["letter"]
        letter_page = pages.get(letter, "000")
        parts.append('<div class="toc-group">')
        parts.append(
            '<div class="toc-letter">'
            f'<span class="toc-letter-name">{html.escape(letter)}</span>'
            '<span class="toc-dots"></span>'
            f'<span class="toc-page">{letter_page}</span>'
            "</div>"
        )
        for insn in chapter["instructions"]:
            mnemonic = insn["mnemonic"]
            page = pages.get(mnemonic, "000")
            parts.append(
                f'<a class="toc-entry" href="#{anchor(mnemonic)}">'
                f'<span class="toc-name">{html.escape(mnemonic)}</span>'
                '<span class="toc-dots"></span>'
                f'<span class="toc-page">{page}</span>'
                "</a>"
            )
        parts.append("</div>")
    parts.extend(["</div>", "</section>"])
    return "\n".join(parts)


def render_cover(doc: dict, chapters: list[dict]) -> str:
    total = sum(len(chapter["instructions"]) for chapter in chapters)
    scope = doc.get("scope", "A – Z 字母")
    subtitle = doc.get("subtitle", "卷一 · 基础架构")
    cover_title = html.escape(doc.get("title", "龙芯架构指令速查表")).replace(
        "指令速查表", "<br>指令速查表"
    )
    return f"""
    <section class="cover">
      <div class="cover-kicker">LOONGARCH ISA REFERENCE</div>
      <div class="cover-main">
        <h1 class="cover-title">{cover_title}</h1>
        <div class="cover-subtitle">LoongArch Instruction Quick Reference</div>
        <div class="cover-rule"></div>
      </div>
      <div class="cover-meta">
        <div><strong>卷册</strong>　{html.escape(subtitle)}</div>
        <div><strong>范围</strong>　{html.escape(scope)}</div>
        <div><strong>条目</strong>　{total} 条</div>
        <div><strong>排序</strong>　助记符字典序</div>
      </div>
      <div class="cover-bottom">A4 · 按指令连续排列 · 含编码方框位图</div>
    </section>
    """


def build_html(content: dict, pages: dict[str, int]) -> str:
    doc = content["document"]
    chapters = content["chapters"]
    body = "\n".join(
        [
            render_cover(doc, chapters),
            render_toc(chapters, pages),
            *(render_chapter(chapter) for chapter in chapters),
        ]
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{html.escape(doc["title"])}</title>
<link rel="stylesheet" href="../style.css">
</head>
<body>
{body}
</body>
</html>
"""


def build_pdf(content: dict, pages: dict[str, int]) -> None:
    BUILD_DIR.mkdir(exist_ok=True)
    HTML_PATH.write_text(build_html(content, pages), encoding="utf-8")
    subprocess.run(
        [
            "chromium",
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--print-to-pdf-no-header",
            "--generate-pdf-document-outline",
            f"--print-to-pdf={PDF_PATH}",
            HTML_PATH.as_uri(),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def extract_outline_pages(pdf_path: pathlib.Path, chapters: list[dict]) -> dict[str, int]:
    raw = subprocess.run(
        ["qpdf", "--json", "--json-key=outlines", str(pdf_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    data = json.loads(raw)

    mnemonic_set = {
        insn["mnemonic"] for chapter in chapters for insn in chapter["instructions"]
    }
    chapter_titles = {chapter["title"]: chapter["letter"] for chapter in chapters}
    pages: dict[str, int] = {}

    def walk(nodes: list[dict]) -> None:
        for node in nodes:
            title = node.get("title", "")
            page = node.get("destpageposfrom1")
            if page:
                matched = None
                for chapter_title, letter in chapter_titles.items():
                    if title.startswith(chapter_title):
                        matched = letter
                        break
                if matched:
                    pages[matched] = page
                else:
                    token = title.split()[0] if title.split() else ""
                    if token in mnemonic_set:
                        pages[token] = page
            walk(node.get("kids", []))

    walk(data.get("outlines", []))
    return pages


def clean_outline(pdf_path: pathlib.Path, chapters: list[dict], pages: dict[str, int], doc_title: str) -> None:
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    writer.append(reader, import_outline=False)

    writer.add_outline_item("封面", 0, bold=True)
    writer.add_outline_item("目录", 1, bold=True)
    for chapter in chapters:
        letter = chapter["letter"]
        parent = writer.add_outline_item(
            chapter["title"], max(pages.get(letter, 1) - 1, 0), bold=True
        )
        for insn in chapter["instructions"]:
            page = max(pages.get(insn["mnemonic"], 1) - 1, 0)
            writer.add_outline_item(
                f'{insn["mnemonic"]} {insn["operands"]}', page, parent=parent
            )

    writer.add_metadata({"/Title": doc_title})
    tmp = pdf_path.with_suffix(".pdf.tmp")
    with open(tmp, "wb") as handle:
        writer.write(handle)
    tmp.replace(pdf_path)


def main() -> None:
    content = yaml.safe_load((ROOT / "content.yaml").read_text(encoding="utf-8"))
    chapters = content["chapters"]
    pages: dict[str, int] = {}
    BUILD_DIR.mkdir(exist_ok=True)
    if PAGES_PATH.exists():
        pages = json.loads(PAGES_PATH.read_text(encoding="utf-8"))

    for _ in range(6):
        build_pdf(content, pages)
        actual = extract_outline_pages(PDF_PATH, chapters)
        if actual == pages:
            break
        pages = actual
        PAGES_PATH.write_text(
            json.dumps(pages, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    else:
        raise SystemExit("TOC page numbers did not stabilize after 6 passes")

    if not pages:
        raise SystemExit("could not extract page numbers from the PDF outline")
    doc_title = content["document"]["title"]
    clean_outline(PDF_PATH, chapters, pages, doc_title)

    info = subprocess.run(
        ["pdfinfo", str(PDF_PATH)], check=True, capture_output=True, text=True
    ).stdout
    for line in info.splitlines():
        if line.startswith(("Pages:", "Page size:", "File size:")):
            print(line)
    print(f"wrote {PDF_PATH}")


if __name__ == "__main__":
    main()
