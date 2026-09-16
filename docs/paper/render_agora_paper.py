#!/usr/bin/env python3
"""Render the AGORA research preprint as a publication-quality PDF."""

from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parents[2]

# The canonical manuscript is English (arXiv cs.MA); `es` is the Spanish mirror.
LOCALES = {
    "en": {
        "source": ROOT / "docs/paper/AGORA_PROOF_OF_USEFUL_RESEARCH.md",
        "output": ROOT / "output/pdf/AGORA_PROOF_OF_USEFUL_RESEARCH_MERARI_ACERO.pdf",
        "abstract_heading": "## Abstract",
        "cover_title": "AGORA: proof of<br/>useful research",
        "cover_subtitle": (
            "An experimental protocol for turning agentic work into traceable "
            "knowledge and TOKOIN rewards"
        ),
        "thesis_label": "CORE THESIS",
        "thesis_body": (
            "The network does not reward votes or empty activity. It rewards traceable "
            "knowledge objects; consensus orders and selects, but it does not turn a "
            "claim into truth."
        ),
        "meta": "Technical preprint · Version 0.2 · 16 September 2026",
        "toc_label": "Contents",
        "reading_label": "HOW TO READ THIS",
        "reading_body": (
            "This document separates scientific protocol, distributed consensus and "
            "economic asset. Evidence for one does not automatically transfer to the "
            "others."
        ),
        "doc_title": "AGORA: proof of useful research for societies of autonomous agents",
        "doc_subject": "Experimental research protocol, knowledge genealogy and TOKOIN",
    },
    "es": {
        "source": ROOT / "docs/paper/AGORA_PROOF_OF_USEFUL_RESEARCH.es.md",
        "output": ROOT / "output/pdf/AGORA_PROOF_OF_USEFUL_RESEARCH_MERARI_ACERO_ES.pdf",
        "abstract_heading": "## Resumen",
        "cover_title": "AGORA: prueba de<br/>investigación útil",
        "cover_subtitle": (
            "Un protocolo experimental para convertir trabajo agéntico en conocimiento "
            "trazable y recompensas TOKOIN"
        ),
        "thesis_label": "TESIS CENTRAL",
        "thesis_body": (
            "La red no recompensa votos ni actividad vacía. Recompensa objetos "
            "de conocimiento trazables; el consenso ordena y selecciona, pero no "
            "convierte una afirmación en verdad."
        ),
        "meta": "Preprint técnico · Versión 0.2 · 16 de septiembre de 2026",
        "toc_label": "Contenido",
        "reading_label": "LECTURA CORRECTA",
        "reading_body": (
            "Este documento separa protocolo científico, consenso distribuido y "
            "activo económico. Las pruebas de uno no se transfieren automáticamente "
            "a los otros."
        ),
        "doc_title": "AGORA: prueba de investigación útil para sociedades de agentes autónomos",
        "doc_subject": "Protocolo experimental de investigación, genealogía y TOKOIN",
    },
}

INK = colors.HexColor("#101820")
MUTED = colors.HexColor("#55606A")
GOLD = colors.HexColor("#E2A93B")
TEAL = colors.HexColor("#0B8F87")
PALE = colors.HexColor("#F2F5F4")
BLUE = colors.HexColor("#275D78")
RED = colors.HexColor("#A33A3A")


def register_fonts() -> tuple[str, str, str]:
    regular = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    bold = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    mono = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
    if regular.exists() and bold.exists() and mono.exists():
        pdfmetrics.registerFont(TTFont("AgoraSans", regular))
        pdfmetrics.registerFont(TTFont("AgoraSans-Bold", bold))
        pdfmetrics.registerFont(TTFont("AgoraMono", mono))
        return "AgoraSans", "AgoraSans-Bold", "AgoraMono"
    return "Helvetica", "Helvetica-Bold", "Courier"


FONT, FONT_BOLD, FONT_MONO = register_fonts()


class PaperDoc(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            style = flowable.style.name
            if style in {"H1", "H2"}:
                level = 0 if style == "H1" else 1
                text = flowable.getPlainText()
                key = f"section-{level}-{self.page}-{abs(hash(text))}"
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=level, closed=False)
                self.notify("TOCEntry", (level, text, self.page, key))


def inline_markup(value: str) -> str:
    links: list[tuple[str, str]] = []
    codes: list[str] = []

    def save_link(match: re.Match[str]) -> str:
        links.append((match.group(1), match.group(2)))
        return f"@@LINK{len(links) - 1}@@"

    def save_code(match: re.Match[str]) -> str:
        codes.append(match.group(1))
        return f"@@CODE{len(codes) - 1}@@"

    value = re.sub(r"\[([^]]+)]\((https?://[^)]+)\)", save_link, value)
    value = re.sub(r"`([^`]+)`", save_code, value)
    value = html.escape(value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    for index, code in enumerate(codes):
        safe = html.escape(code)
        value = value.replace(
            f"@@CODE{index}@@", f'<font name="{FONT_MONO}" color="#275D78">{safe}</font>'
        )
    for index, (label, url) in enumerate(links):
        value = value.replace(
            f"@@LINK{index}@@",
            f'<link href="{html.escape(url)}" color="#0B8F87">{html.escape(label)}</link>',
        )
    if re.fullmatch(r"https?://\S+", html.unescape(value)):
        url = html.unescape(value)
        value = f'<link href="{url}" color="#0B8F87">{url}</link>'
    return value


def styles():
    base = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=9.2,
            leading=13.6,
            textColor=INK,
            alignment=TA_JUSTIFY,
            spaceAfter=7,
            allowWidows=0,
            allowOrphans=0,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName=FONT_BOLD,
            fontSize=17,
            leading=21,
            textColor=INK,
            spaceBefore=4,
            spaceAfter=10,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName=FONT_BOLD,
            fontSize=12.5,
            leading=16,
            textColor=BLUE,
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "H3",
            parent=base["Heading3"],
            fontName=FONT_BOLD,
            fontSize=10.5,
            leading=14,
            textColor=TEAL,
            spaceBefore=8,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=9,
            leading=13,
            leftIndent=12,
            firstLineIndent=-7,
            textColor=INK,
            spaceAfter=4,
        ),
        "quote": ParagraphStyle(
            "Quote",
            parent=base["BodyText"],
            fontName=FONT,
            fontSize=9.2,
            leading=13.5,
            leftIndent=12,
            rightIndent=8,
            borderColor=GOLD,
            borderWidth=1.2,
            borderPadding=(6, 8, 6, 10),
            backColor=colors.HexColor("#FFF9EB"),
            textColor=INK,
            spaceAfter=10,
        ),
        "code": ParagraphStyle(
            "Code",
            fontName=FONT_MONO,
            fontSize=7.2,
            leading=10,
            leftIndent=8,
            rightIndent=8,
            borderColor=colors.HexColor("#CBD5D8"),
            borderWidth=0.5,
            borderPadding=7,
            backColor=colors.HexColor("#F5F7F8"),
            textColor=colors.HexColor("#263238"),
            spaceAfter=9,
        ),
        "table": ParagraphStyle(
            "TableCell",
            fontName=FONT,
            fontSize=7.5,
            leading=10,
            textColor=INK,
        ),
        "table_head": ParagraphStyle(
            "TableHead",
            fontName=FONT_BOLD,
            fontSize=7.5,
            leading=10,
            textColor=colors.white,
        ),
        "toc": ParagraphStyle(
            "TOC",
            fontName=FONT,
            fontSize=9,
            leading=13,
            textColor=INK,
        ),
    }


S = styles()


def page_chrome(canvas, doc):
    canvas.saveState()
    page = canvas.getPageNumber()
    width, height = A4
    if page > 1:
        canvas.setStrokeColor(colors.HexColor("#D7DEDF"))
        canvas.setLineWidth(0.5)
        canvas.line(22 * mm, height - 15 * mm, width - 22 * mm, height - 15 * mm)
        canvas.setFont(FONT_BOLD, 7.3)
        canvas.setFillColor(INK)
        canvas.drawString(22 * mm, height - 11.5 * mm, "AGORA / PROOF OF USEFUL RESEARCH")
        canvas.setFont(FONT, 7)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(width - 22 * mm, height - 11.5 * mm, "PREPRINT 0.1")
        canvas.setStrokeColor(GOLD)
        canvas.setLineWidth(2)
        canvas.line(22 * mm, 14 * mm, 47 * mm, 14 * mm)
        canvas.setFont(FONT, 7.2)
        canvas.setFillColor(MUTED)
        canvas.drawString(51 * mm, 11.8 * mm, "Merari Acero · 14 septiembre 2026")
        canvas.drawRightString(width - 22 * mm, 11.8 * mm, str(page))
    canvas.restoreState()


def cover_story(text: dict):
    return [
        Spacer(1, 18 * mm),
        Paragraph(
            "A G O R A",
            ParagraphStyle(
                "Brand",
                fontName=FONT_BOLD,
                fontSize=12,
                leading=14,
                textColor=GOLD,
                alignment=TA_LEFT,
                spaceAfter=13 * mm,
            ),
        ),
        HRFlowable(width="28%", thickness=4, color=TEAL, hAlign="LEFT", spaceAfter=10 * mm),
        Paragraph(
            text["cover_title"],
            ParagraphStyle(
                "CoverTitle",
                fontName=FONT_BOLD,
                fontSize=31,
                leading=36,
                textColor=INK,
                alignment=TA_LEFT,
                spaceAfter=7 * mm,
            ),
        ),
        Paragraph(
            text["cover_subtitle"],
            ParagraphStyle(
                "CoverSub",
                fontName=FONT,
                fontSize=15,
                leading=21,
                textColor=BLUE,
                alignment=TA_LEFT,
                spaceAfter=16 * mm,
            ),
        ),
        Table(
            [
                [Paragraph(text["thesis_label"], S["table_head"])],
                [
                    Paragraph(
                        text["thesis_body"],
                        ParagraphStyle(
                            "CoverThesis",
                            parent=S["body"],
                            fontSize=11,
                            leading=16,
                            spaceAfter=0,
                        ),
                    )
                ],
            ],
            colWidths=[155 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("BACKGROUND", (0, 1), (-1, 1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#C9D3D5")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]),
        ),
        Spacer(1, 20 * mm),
        Paragraph(
            "Merari Acero",
            ParagraphStyle("Author", fontName=FONT_BOLD, fontSize=13, leading=16, textColor=INK),
        ),
        Paragraph(
            text["meta"],
            ParagraphStyle("Meta", fontName=FONT, fontSize=9, leading=13, textColor=MUTED),
        ),
        Paragraph(
            '<link href="https://github.com/MerariJafet/agora" color="#0B8F87">'
            "github.com/MerariJafet/agora</link>",
            ParagraphStyle("URL", fontName=FONT, fontSize=9, leading=13, textColor=TEAL),
        ),
        Spacer(1, 9 * mm),
        Paragraph(
            "RESEARCH ALPHA · TEST_NON_RECOGNIZABLE · NO MAINNET · NO MARKET CLAIM",
            ParagraphStyle("Badge", fontName=FONT_BOLD, fontSize=7.5, leading=10, textColor=RED),
        ),
        PageBreak(),
    ]


def toc_story(text: dict):
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            "TOC0", fontName=FONT_BOLD, fontSize=9.5, leading=15, leftIndent=0,
            firstLineIndent=0, textColor=INK, spaceBefore=2,
        ),
        ParagraphStyle(
            "TOC1", fontName=FONT, fontSize=8.5, leading=13, leftIndent=12,
            firstLineIndent=0, textColor=MUTED,
        ),
    ]
    return [
        Paragraph(text["toc_label"], S["h1"]),
        Spacer(1, 3 * mm),
        toc,
        Spacer(1, 8 * mm),
        Table(
            [
                [Paragraph(text["reading_label"], S["table_head"])],
                [Paragraph(text["reading_body"], S["body"])],
            ],
            colWidths=[155 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                ("BACKGROUND", (0, 1), (-1, 1), PALE),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#C9D3D5")),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]),
        ),
        PageBreak(),
    ]


def table_flow(rows: list[list[str]]) -> Table:
    columns = max(len(row) for row in rows)
    normalized = [row + [""] * (columns - len(row)) for row in rows]
    data = []
    for row_index, row in enumerate(normalized):
        style = S["table_head"] if row_index == 0 else S["table"]
        data.append([Paragraph(inline_markup(cell), style) for cell in row])
    usable = 155 * mm
    widths = [usable / columns] * columns
    if columns == 2:
        widths = [usable * 0.36, usable * 0.64]
    elif columns == 3:
        widths = [usable * 0.25, usable * 0.16, usable * 0.59]
    return Table(
        data,
        colWidths=widths,
        repeatRows=1,
        hAlign="LEFT",
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), INK),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD4D6")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]),
    )


def parse_markdown(text: str, abstract_heading: str):
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == abstract_heading)
    lines = lines[start:]
    story = []
    i = 0
    first_major = True
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("```"):
            language = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1
            label = f"[{language}]\n" if language else ""
            story.append(Preformatted(label + "\n".join(code_lines), S["code"]))
            continue
        if stripped.startswith("## "):
            title = stripped[3:]
            if re.match(r"\d+\.", title) and not first_major:
                story.append(PageBreak())
            first_major = False
            story.append(Paragraph(inline_markup(title), S["h1"]))
            i += 1
            continue
        if stripped.startswith("### "):
            story.append(Paragraph(inline_markup(stripped[4:]), S["h2"]))
            i += 1
            continue
        if stripped.startswith("#### "):
            story.append(Paragraph(inline_markup(stripped[5:]), S["h3"]))
            i += 1
            continue
        if stripped.startswith("> "):
            quote = []
            while i < len(lines) and lines[i].strip().startswith("> "):
                quote.append(lines[i].strip()[2:])
                i += 1
            story.append(Paragraph(inline_markup(" ".join(quote)), S["quote"]))
            continue
        if (
            stripped.startswith("|")
            and i + 1 < len(lines)
            and re.match(r"^\|?\s*:?-+", lines[i + 1].strip())
        ):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [cell.strip() for cell in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", cell.replace(" ", "")) for cell in cells):
                    rows.append(cells)
                i += 1
            story.extend([table_flow(rows), Spacer(1, 3 * mm)])
            continue
        if stripped.startswith("- "):
            bullets = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                bullets.append(Paragraph("• " + inline_markup(lines[i].strip()[2:]), S["bullet"]))
                i += 1
            story.append(KeepTogether(bullets[:2]) if len(bullets) <= 2 else bullets[0])
            if len(bullets) > 2:
                story.extend(bullets[1:])
            continue
        if re.match(r"^\d+\.\s", stripped):
            number = re.match(r"^(\d+)\.\s+(.*)", stripped)
            assert number
            story.append(
                Paragraph(
                    f"<b>{number.group(1)}.</b> {inline_markup(number.group(2))}",
                    S["bullet"],
                )
            )
            i += 1
            continue
        paragraph = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if (
                not nxt
                or nxt.startswith(("#", ">", "```", "|", "- "))
                or re.match(r"^\d+\.\s", nxt)
            ):
                break
            paragraph.append(nxt)
            i += 1
        story.append(Paragraph(inline_markup(" ".join(paragraph)), S["body"]))
    return story


def build(locale: str = "en"):
    text = LOCALES[locale]
    source: Path = text["source"]
    output: Path = text["output"]
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = PaperDoc(
        str(output),
        pagesize=A4,
        rightMargin=25 * mm,
        leftMargin=30 * mm,
        topMargin=22 * mm,
        bottomMargin=20 * mm,
        title=text["doc_title"],
        author="Merari Acero",
        subject=text["doc_subject"],
    )
    story = (
        cover_story(text)
        + toc_story(text)
        + parse_markdown(source.read_text(encoding="utf-8"), text["abstract_heading"])
    )
    doc.multiBuild(story, onFirstPage=page_chrome, onLaterPages=page_chrome)
    print(f"created {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    import sys

    requested = [arg.lstrip("-") for arg in sys.argv[1:]] or ["en"]
    if requested == ["all"]:
        requested = list(LOCALES)
    for name in requested:
        if name not in LOCALES:
            raise SystemExit(f"unknown locale {name!r}; expected one of {sorted(LOCALES)} or 'all'")
        build(name)
