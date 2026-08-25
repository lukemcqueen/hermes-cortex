#!/usr/bin/env python3
"""JASRAC international work report template — reproduces the reference
format (doc_ac6bcfe54d4c_260326_260290.pdf) with reportlab.

Measured layout facts (from pixel-scanning the reference render):
  - A4 portrait 595.32 x 841.92pt, monospace (DejaVu Sans Mono), pure B/W
  - 12 full-width horizontal rules x=52..545pt at y:
    162, 188, 207, 232, 251, 276, 295, 315, 334, 354, 374, 394
  - Row baselines: row1=176 sub1=197 row2=220 sub2=241 row3=264 sub3=285
    bottom=386; bands: main 25pt, sub 19pt, 4 empty rows, bottom 20pt
  - Right-aligned numeric columns: EX=319 FRAC=363 MEC=409 PCT=501
  - Column headers DR.EX. / DR.MEC. right-aligned at 363 / 501
  - Bottom-right date right-aligned at 531; participant x=56, code x=91
  - Header right keeps the format 【id】 [title] — Japanese removed per
    fleet preference (renders without a CJK font requirement)

Usage:
    python3 jasrac_work_report.py -o out.pdf
    python3 jasrac_work_report.py -o out.pdf --json data.json
"""
import argparse
import json

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

PAGE_W, PAGE_H = A4

# Fonts — mono family only (reference is a terminal-style printout).
MONO = "DejaVuMono"
MONO_BOLD = "DejaVuMono-Bold"
pdfmetrics.registerFont(TTFont(MONO, "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"))
pdfmetrics.registerFont(TTFont(MONO_BOLD, "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"))

RULE_X0, RULE_X1 = 52.0, 545.0
RULE_YS = [162, 188, 207, 232, 251, 276, 295, 315, 334, 354, 374, 394]
EX_R, FRAC_R, MEC_R, PCT_R = 319, 363, 409, 501
BOTTOM_RIGHT_R = 531
PARTICIPANT_X, CODE_X = 56.0, 91.0

DEFAULT_DATA = {
    "header_left": "2026/07/08 9:46",
    "header_right": "【1T132148】 [WORK TITLE]",
    "title": "T:WORK TITLE",
    "subtitle": "ST:*WORK TITLE VERSION",
    "work_id": "1T1-XXXX-X",
    "col_headers": ["DR.EX.,", "DR.MEC.,"],
    "rows": [
        {"participant": "1  A  1  PARTICIPANT ONE", "dr_ex": "099", "frac": "3/12", "dr_mec": "099", "pct": "0,00%", "code": "CODE-0001"},
        {"participant": "2  C  PARTICIPANT TWO", "dr_ex": "336", "frac": "6/12", "dr_mec": "336", "pct": "50,00%", "code": "CODE-0002"},
        {"participant": "3  E  1  PARTICIPANT THREE", "dr_ex": "038", "frac": "3/12", "dr_mec": "038", "pct": "50,00%", "code": "CODE-0003"},
    ],
    "empty_rows_after": 4,
    "bottom_left": "JASRAC:JASRAC",
    "bottom_right": "2026/07/08 ******",
    "footer_left": "https://example.com/app/kokusai1/1T132148",
    "footer_right": "1/1",
}

ROW_YS = [176, 220, 264]
SUB_YS = [197, 241, 285]
BOTTOM_Y = 386


def draw_text(c, x, y_top, text, size=10, bold=False, right=False):
    fn = MONO_BOLD if bold else MONO
    c.setFont(fn, size)
    if right:
        c.drawRightString(x, PAGE_H - y_top, text)
    else:
        c.drawString(x, PAGE_H - y_top, text)


def draw_rules(c):
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.7)
    for y in RULE_YS:
        c.line(RULE_X0, PAGE_H - y, RULE_X1, PAGE_H - y)


def build(data, out_path):
    c = canvas.Canvas(out_path, pagesize=A4)
    c.setTitle(data["header_right"])

    draw_text(c, 30, 14, data["header_left"], size=9)
    draw_text(c, PAGE_W - 30, 14, data["header_right"], size=9, right=True)

    draw_text(c, 62, 78, data["title"], size=13, bold=True)
    draw_text(c, PAGE_W - 62, 78, data["work_id"], size=13, bold=True, right=True)
    draw_text(c, 62, 96, data["subtitle"], size=11, bold=True)

    draw_text(c, FRAC_R, 150, data["col_headers"][0], size=10, right=True)
    draw_text(c, PCT_R, 150, data["col_headers"][1], size=10, right=True)

    for i, row in enumerate(data["rows"]):
        y = ROW_YS[i]
        draw_text(c, PARTICIPANT_X, y, row["participant"], size=10)
        draw_text(c, EX_R, y, row["dr_ex"], size=10, right=True)
        draw_text(c, FRAC_R, y, row["frac"], size=10, right=True)
        draw_text(c, MEC_R, y, row["dr_mec"], size=10, right=True)
        draw_text(c, PCT_R, y, row["pct"], size=10, right=True)
        draw_text(c, CODE_X, SUB_YS[i], row["code"], size=10)

    draw_text(c, PARTICIPANT_X, BOTTOM_Y, data["bottom_left"], size=10, bold=True)
    draw_text(c, BOTTOM_RIGHT_R, BOTTOM_Y, data["bottom_right"], size=10, right=True)

    draw_rules(c)

    draw_text(c, 30, PAGE_H - 22, data["footer_left"], size=8.5)
    draw_text(c, PAGE_W - 30, PAGE_H - 22, data["footer_right"], size=8.5, right=True)

    c.showPage()
    c.save()
    print(f"OK: {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="/tmp/jasrac_work_report_out.pdf")
    ap.add_argument("--json", help="optional JSON data file (same shape as DEFAULT_DATA)")
    args = ap.parse_args()
    data = DEFAULT_DATA
    if args.json:
        with open(args.json, encoding="utf-8") as f:
            data = {**DEFAULT_DATA, **json.load(f)}
    build(data, args.out)


if __name__ == "__main__":
    main()
