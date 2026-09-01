#!/usr/bin/env python3
"""
Generate a one-page, print-ready worksheet for creating a dice-based
SeedSigner Bitcoin wallet with either a 50-roll 12-word seed or a 99-roll
24-word seed, plus an optional dice-generated hexadecimal BIP-39 passphrase.

The page has four numbered sections:
    1. Dice Rolls      - a 10x10 grid for recording d6 rolls, with support for
                          both 50-roll (12 words) and 99-roll (24 words) flows
    2. Seed Words      - numbered blank lines for the resulting BIP-39 words
    3. Seed QR         - blank 21x21, 25x25, and 29x29 QR templates to
                          transcribe SeedSigner's output QR onto
    4. Passphrase      - a dice-to-hex lookup table plus an 8x4 grid for
                          recording a 32-digit (128-bit) hex passphrase

Usage:
    python3 generate_worksheet.py [-o OUTPUT.pdf]

Requires: reportlab, Pillow (see requirements.txt)
"""
import argparse
from pathlib import Path

from PIL import Image, ImageOps
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ASSETS_DIR = Path(__file__).parent / "assets"
FINGERPRINT_IMG = ASSETS_DIR / "fingerprint.png"
SEED_QR_IMAGES = [
    ("21x21", ASSETS_DIR / "seed_qr_21x21.png"),
    ("25x25", ASSETS_DIR / "seed_qr_25x25.png"),
    ("29x29", ASSETS_DIR / "seed_qr_29x29.png"),
]

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
PAGE_W, PAGE_H = letter
MARGIN_X = 0.75 * inch

GREY = (0.70, 0.70, 0.70)          # grid lines, blank lines, dividers
WARNING_RED = (0.55, 0.1, 0.1)     # privacy notice
CAPTION_GREY = (0.6, 0.6, 0.6)     # "no/passphrase applied" captions

TITLE_TEXT = "SeedSigner Dice Wallet with Passphrase Worksheet"
SECTION_HEADING_SIZE = 12

PRIVACY_LINE_1 = "\u26a0 PRIVATE \u2014 contains sensitive wallet data. Store securely or destroy after use."
PRIVACY_LINE_2 = "Never share. Never make a digital copy. Never input into an internet connected device."

# The dice -> hex digit lookup table (2 dice: LEFT die selects row,
# RIGHT die selects column). '*' means reroll.
HEX_TABLE_ROWS = [
    ["0", "1", "2", "3", "4", "5"],
    ["6", "7", "8", "9", "a", "b"],
    ["c", "d", "e", "f", "0", "1"],
    ["2", "3", "4", "5", "6", "7"],
    ["8", "9", "a", "b", "c", "d"],
    ["e", "f", "*", "*", "*", "*"],
]
RIGHT_LETTERS = ["R", "I", "G", "H", "T"]      # over columns 2-6
LEFT_LETTERS = ["", "L", "E", "F", "T", ""]    # beside rows 2-5


# ---------------------------------------------------------------------------
# Small drawing helpers
# ---------------------------------------------------------------------------
def grid_lines(cnv, left, top, cell_w, cell_h, cols, rows, color=GREY, trim_last_row_and_col=False):
    """Draw a cols x rows grid of light lines with its top-left corner at (left, top).
    If trim_last_row_and_col is true, the outer right and bottom edges are shortened to the
    length of the first 9 cells so the last cell is effectively removed without deleting the
    frame entirely."""
    cnv.setStrokeColorRGB(*color)
    cnv.setLineWidth(1)
    for i in range(cols + 1):
        x = left + i * cell_w
        if trim_last_row_and_col and i == cols:
            cnv.line(x, top - (rows - 1) * cell_h, x, top)
        else:
            cnv.line(x, top - rows * cell_h, x, top)
    for i in range(rows + 1):
        y = top - i * cell_h
        if trim_last_row_and_col and i == rows:
            cnv.line(left, y, left + (cols - 1) * cell_w, y)
        else:
            cnv.line(left, y, left + cols * cell_w, y)
    cnv.setStrokeColorRGB(0, 0, 0)


def draw_fingerprint(cnv, x, y, h, aspect):
    """Draw the fingerprint reference image, bottom-left corner at (x, y), given height h.
    Returns the width it was drawn at."""
    w = h / aspect
    cnv.drawImage(str(FINGERPRINT_IMG), x, y, width=w, height=h,
                  preserveAspectRatio=True, mask=None)
    return w


def draw_dice_icon(cnv, x, y, size, stroke=GREY, fill=(1, 1, 1), pip_color=(0, 0, 0)):
    """Draw a small dice icon with pip marks so it reads as a real die."""
    cnv.setStrokeColorRGB(*stroke)
    cnv.setFillColorRGB(*fill)
    cnv.rect(x, y, size, size, fill=1, stroke=1)

    pip_r = size / 9
    offset = size / 4
    pip_positions = [
        (offset, offset),
        (3 * offset, offset),
        (2 * offset, 2 * offset),
        (offset, 3 * offset),
        (3 * offset, 3 * offset),
    ]

    cnv.setFillColorRGB(*pip_color)
    for px, py in pip_positions:
        cnv.circle(x + px, y + py, pip_r, fill=1, stroke=0)
    cnv.setFillColorRGB(0, 0, 0)


def fit_text_width(cnv, text, font, max_width, start_size=8, min_size=5):
    """Shrink font size in 0.5pt steps until text fits max_width."""
    size = start_size
    while size > min_size and cnv.stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def numbered_line(cnv, x, y, number, line_len, label_w=0.30 * inch, font_size=9, bold=False):
    """Draw '<number>.' followed by a blank grey line, e.g. for word/answer lists.
    The label sits in a fixed-width field so every number stays in its own column, but the
    line starts almost immediately after the period instead of leaving a visible spacer."""
    font_name = "Helvetica-Bold" if bold else "Helvetica"
    cnv.setFont(font_name, font_size)
    label_right = x + label_w
    cnv.drawRightString(label_right, y, f"{number}.")
    line_start = label_right + 0.015 * inch
    cnv.setStrokeColorRGB(*GREY)
    cnv.setLineWidth(1.0 if bold else 0.7)
    cnv.line(line_start, y - 1, line_start + line_len, y - 1)
    cnv.setStrokeColorRGB(0, 0, 0)


def fingerprint_confirmation_row(cnv, x, y_bottom, line_right, icon_h, aspect, caption):
    """Icon at the start of a blank grey line, with a small grey caption centered below.
    Returns the y used for the caption baseline (useful for laying out a box around it)."""
    icon_w = draw_fingerprint(cnv, x, y_bottom, icon_h, aspect)
    line_x = x + icon_w + 0.14 * inch
    cnv.setStrokeColorRGB(*GREY)
    cnv.setLineWidth(0.6)
    cnv.line(line_x, y_bottom, line_right, y_bottom)
    cnv.setStrokeColorRGB(0, 0, 0)

    cap_y = y_bottom - 10
    cnv.setFillColorRGB(*CAPTION_GREY)
    cap_maxw = line_right - line_x - 0.04 * inch
    cap_size = fit_text_width(cnv, caption, "Helvetica-Oblique", cap_maxw, start_size=8.5)
    cnv.setFont("Helvetica-Oblique", cap_size)
    cnv.drawCentredString((line_x + line_right) / 2, cap_y, caption)
    cnv.setFillColorRGB(0, 0, 0)
    return cap_y


# ---------------------------------------------------------------------------
# Section builders — each returns the y-coordinate (or dict) the next
# section needs to know about.
# ---------------------------------------------------------------------------
def draw_header(cnv):
    """Title, privacy notice, date field, divider. Returns the y of the divider."""
    title_y = PAGE_H - 0.60 * inch
    title_size = 21
    while cnv.stringWidth(TITLE_TEXT, "Helvetica-Bold", title_size) > PAGE_W - 1.0 * inch:
        title_size -= 0.5
    cnv.setFont("Helvetica-Bold", title_size)
    cnv.drawCentredString(PAGE_W / 2, title_y, TITLE_TEXT)

    notice_y = title_y - 0.24 * inch
    cnv.setFont("Helvetica-Bold", 8.5)
    cnv.setFillColorRGB(*WARNING_RED)
    cnv.drawString(MARGIN_X, notice_y, PRIVACY_LINE_1)

    notice2_y = notice_y - 0.16 * inch
    cnv.drawString(MARGIN_X, notice2_y, PRIVACY_LINE_2)
    cnv.setFillColorRGB(0, 0, 0)

    cnv.setFont("Helvetica", 8.5)
    cnv.drawRightString(PAGE_W - MARGIN_X, notice2_y, "Date: _______________")

    divider_y = notice2_y - 0.12 * inch
    cnv.setStrokeColorRGB(*GREY)
    cnv.setLineWidth(1)
    cnv.line(MARGIN_X, divider_y, PAGE_W - MARGIN_X, divider_y)
    cnv.setStrokeColorRGB(0, 0, 0)
    return divider_y


def draw_dice_grid(cnv, top_y):
    """Section 1: 10x10 dice-roll grid with the last cell removed by shortening the
    final right and bottom border segments. Returns (grid_left, grid_bottom, grid_size)."""
    cnv.setFont("Helvetica-Bold", SECTION_HEADING_SIZE)
    cnv.drawString(MARGIN_X, top_y, "1.")
    die_size = 0.10 * inch
    die_y = top_y + 0.006 * inch
    first_die_x = MARGIN_X + 0.30 * inch
    draw_dice_icon(cnv, first_die_x, die_y, die_size)
    text_x = first_die_x + die_size + 0.06 * inch
    cnv.setFont("Helvetica-Bold", SECTION_HEADING_SIZE)
    cnv.drawString(text_x, top_y, "50 → ")
    cnv.setFont("Helvetica-Bold", SECTION_HEADING_SIZE)
    cnv.drawString(text_x + cnv.stringWidth("50 → ", "Helvetica-Bold", SECTION_HEADING_SIZE), top_y, "12 words")
    cnv.setFont("Helvetica-Bold", SECTION_HEADING_SIZE)
    cnv.drawString(text_x + cnv.stringWidth("50 → 12 words ", "Helvetica-Bold", SECTION_HEADING_SIZE), top_y, "/")

    second_die_x = text_x + cnv.stringWidth("50 → 12 words /", "Helvetica-Bold", SECTION_HEADING_SIZE) + 0.12 * inch
    draw_dice_icon(cnv, second_die_x, die_y, die_size)
    cnv.setFont("Helvetica-Bold", SECTION_HEADING_SIZE)
    cnv.drawString(second_die_x + die_size + 0.06 * inch, top_y, "99 → 24 words")

    cell = 0.225 * inch
    grid_size = 10 * cell
    grid_top = top_y - 0.28 * inch
    grid_left = MARGIN_X + 0.22 * inch
    grid_bottom = grid_top - grid_size

    cnv.setFont("Helvetica", 7.5)
    for col in range(10):
        x_center = grid_left + col * cell + cell / 2
        cnv.drawCentredString(x_center, grid_top + 5.5, str(col + 1))
    for row in range(10):
        y_center = grid_top - row * cell - cell / 2
        cnv.drawRightString(grid_left - 4.5, y_center - 2.6, str(row + 1))

    grid_lines(cnv, grid_left, grid_top, cell, cell, 10, 10, trim_last_row_and_col=True)

    # Subtle midpoint marker for the actual 50th cell (row 5, column 10), positioned by
    # visual center rather than the font baseline so it sits in the middle of the square.
    cnv.setFillColorRGB(0.78, 0.78, 0.78)
    cnv.setFont("Helvetica-Bold", 12)
    fifty_x = grid_left + 9 * cell + cell / 2
    fifty_cell_top = grid_top - 5 * cell
    fifty_box_center_y = fifty_cell_top + cell / 2
    fifty_y = fifty_box_center_y - 4.5
    cnv.drawCentredString(fifty_x, fifty_y, "50")
    cnv.setFillColorRGB(0, 0, 0)

    return grid_left, grid_bottom, grid_size


def draw_seed_words(cnv, top_y, fp_aspect, left_x=MARGIN_X, max_right=None):
    """Section 2: 24 numbered blank lines (4 columns of 6) plus the seed
    fingerprint confirmation row. Returns (right_edge_x, bottom_y)."""
    cols = 4
    rows = 6
    if max_right is not None:
        usable_w = max_right - left_x
    else:
        usable_w = cols * 1.05 * inch

    cnv.setFont("Helvetica-Bold", SECTION_HEADING_SIZE)
    header_text = "2. Seed Words"
    header_center_x = left_x + usable_w / 2
    cnv.drawCentredString(header_center_x, top_y, header_text)

    col_gap = usable_w / cols
    label_w = 0.20 * inch
    line_len = col_gap - label_w - 0.002 * inch
    row_h = 0.31 * inch
    start_y = top_y - 0.42 * inch

    for i in range(24):
        col, row = divmod(i, rows)
        x = left_x + col * col_gap
        y = start_y - row * row_h
        numbered_line(cnv, x, y, i + 1, line_len, label_w=label_w, bold=(i + 1 == 12))

    bottom_y = start_y - (rows - 1) * row_h
    right_edge = left_x + cols * col_gap - 0.06 * inch
    if max_right is not None:
        right_edge = min(right_edge, max_right)

    fp_y = bottom_y - 0.24 * inch - 0.24 * inch
    fingerprint_confirmation_row(
        cnv, left_x, fp_y, right_edge, icon_h=0.24 * inch,
        aspect=fp_aspect, caption="no passphrase applied",
    )

    return right_edge, fp_y - 0.05 * inch


def draw_seed_qr(cnv, top_y, left_x, max_width=None):
    """Section 3: three blank Seed QR templates (21x21, 25x25, 29x29)
    arranged horizontally across the page beneath Sections 1 and 2."""
    avail_right = PAGE_W - MARGIN_X
    avail_width = avail_right - left_x
    center_x = (left_x + avail_right) / 2

    cnv.setFont("Helvetica-Bold", SECTION_HEADING_SIZE)
    cnv.drawCentredString(center_x, top_y, "3. Seed QR")

    label_w = 0.18 * inch
    gap = 0.12 * inch
    qr_w = (avail_width - 2 * gap - 3 * label_w) / 3
    qr_w *= 1.20
    if max_width is not None:
        qr_w = min(max_width, qr_w)

    total_w = 3 * qr_w + 2 * gap + 3 * label_w
    start_x = center_x - total_w / 2
    row_top = top_y - 0.06 * inch

    def draw_template(label, img_path, x, y_top):
        with Image.open(img_path) as img:
            aspect = img.height / img.width
            grayscale = ImageOps.autocontrast(img.convert("L"))
            qr_img = grayscale.point(
                lambda p: int(p * 0.52) if p < 220 else 255,
                mode="L",
            ).convert("RGBA")

        qr_h = qr_w * aspect
        template_left = x + label_w
        image_bottom = y_top - 0.02 * inch - qr_h

        cnv.saveState()
        cnv.translate(x + 0.16 * inch, image_bottom + qr_h / 2)
        cnv.rotate(90)
        cnv.setFont("Helvetica-Bold", 9)
        cnv.setFillColorRGB(0, 0, 0)
        cnv.drawCentredString(0, 0, label)
        cnv.restoreState()

        cnv.drawImage(
            ImageReader(qr_img), template_left, image_bottom, width=qr_w, height=qr_h,
            preserveAspectRatio=True, mask=None,
        )
        return image_bottom

    bottoms = []
    for idx, (label, img_path) in enumerate(SEED_QR_IMAGES):
        x = start_x + idx * (qr_w + gap + label_w)
        bottoms.append(draw_template(label, img_path, x, row_top))

    return min(bottoms)


def draw_hex_table(cnv, top_y):
    """Left half of section 4: the dice-to-hex lookup table (6x6 grid).
    Returns (t_grid_right, t_grid_top, footer_bottom_y)."""
    table_title_y = top_y - 0.10 * inch
    t_cell = 0.20 * inch

    right_letters_y = table_title_y - 0.28 * inch
    colnum_y = right_letters_y - 0.24 * inch
    t_grid_top = colnum_y - 0.18 * inch
    t_grid_bottom = t_grid_top - 6 * t_cell

    section_center_x = PAGE_W / 2
    left_table_w = 1.65 * inch
    passphrase_w = 3.20 * inch
    gap = 0.42 * inch
    section_left = section_center_x - (left_table_w + gap + passphrase_w) / 2
    top_y = top_y + 0.06 * inch

    rownum_x = section_left + 0.20 * inch
    t_grid_left = rownum_x + 0.26 * inch
    t_grid_right = t_grid_left + 6 * t_cell

    cnv.setFont("Helvetica-Bold", 12)
    cnv.drawCentredString((t_grid_left + t_grid_right) / 2, right_letters_y, "RIGHT")

    cnv.setFont("Helvetica", 9)
    for col in range(6):
        x_center = t_grid_left + col * t_cell + t_cell / 2
        cnv.drawCentredString(x_center, colnum_y, str(col + 1))

    for row in range(6):
        y_center = t_grid_top - row * t_cell - t_cell / 2
        cnv.setFont("Helvetica", 9)
        cnv.drawCentredString(rownum_x, y_center - 3, str(row + 1))

    cnv.setFont("Helvetica-Bold", 12)
    left_label_x = t_grid_left - 0.57 * inch
    left_label_y = (t_grid_top + t_grid_bottom) / 2 + 0.06 * inch
    cnv.saveState()
    cnv.translate(left_label_x, left_label_y)
    cnv.rotate(90)
    cnv.drawCentredString(0, 0, "LEFT")
    cnv.restoreState()

    grid_lines(cnv, t_grid_left, t_grid_top, t_cell, t_cell, 6, 6)

    cnv.setFont("Helvetica", 10)
    for r, row_vals in enumerate(HEX_TABLE_ROWS):
        y_center = t_grid_top - r * t_cell - t_cell / 2
        for cidx, val in enumerate(row_vals):
            x_center = t_grid_left + cidx * t_cell + t_cell / 2
            cnv.drawCentredString(x_center, y_center - 3.5, val)

    footer_y = t_grid_bottom - 0.20 * inch
    footer_x = rownum_x - 0.12 * inch
    cnv.setFont("Helvetica", 8.5)
    cnv.drawString(footer_x, footer_y, "* = roll again")
    cnv.drawString(footer_x, footer_y - 12, "Entropy: 4.00 bits per hex digit.")

    return t_grid_right, t_grid_top, footer_y - 26


def draw_passphrase_grid_and_fingerprint(cnv, top_y, avail_left, fp_aspect):
    """Right half of section 4: 8x4 grid for the 32-digit hex passphrase,
    plus the emphasized, boxed final-wallet-fingerprint confirmation.
    Returns the bottom y of the box."""
    cols, rows = 8, 4
    cell_w, cell_h = 0.40 * inch, 0.26 * inch
    grid_w, grid_h = cols * cell_w, rows * cell_h
    top_y += 0.09 * inch

    avail_right = PAGE_W - MARGIN_X
    grid_left = avail_left + (avail_right - avail_left - grid_w) / 2 - 0.06 * inch
    grid_bottom = top_y - grid_h

    cnv.setFont("Helvetica", 9.5)
    for col in range(cols):
        x_center = grid_left + col * cell_w + cell_w / 2
        cnv.drawCentredString(x_center, top_y + 6, str(col + 1))
    for row in range(rows):
        y_center = top_y - row * cell_h - cell_h / 2
        cnv.drawRightString(grid_left - 6, y_center - 3, str(row + 1))

    grid_lines(cnv, grid_left, top_y, cell_w, cell_h, cols, rows)

    # --- Final Wallet Fingerprint: icon at the start of a blank line, boxed ---
    icon_h = 0.34 * inch
    fp_y = grid_bottom - 0.26 * inch - icon_h
    cap_y = fingerprint_confirmation_row(
        cnv, grid_left, fp_y, grid_left + grid_w, icon_h=icon_h,
        aspect=fp_aspect, caption="passphrase applied",
    )

    box_pad = 0.15 * inch
    box_top = fp_y + icon_h + 0.15 * inch
    box_bottom = cap_y - 0.12 * inch
    cnv.setStrokeColorRGB(0.15, 0.15, 0.15)
    cnv.setLineWidth(1.1)
    cnv.roundRect(grid_left - box_pad, box_bottom, grid_w + 2 * box_pad,
                  box_top - box_bottom, 0.08 * inch, stroke=1, fill=0)
    cnv.setStrokeColorRGB(0, 0, 0)

    return box_bottom


def draw_notes(cnv, top_y, bottom_y=0.42 * inch):
    """A notes box that expands to fill the remaining space at the bottom
    of the page."""
    title_y = top_y - 0.22 * inch
    cnv.setFont("Helvetica-Bold", 11)
    cnv.drawString(MARGIN_X, title_y, "Notes")

    box_top = title_y - 0.08 * inch
    box_h = box_top - bottom_y
    cnv.setStrokeColorRGB(*GREY)
    cnv.setLineWidth(1.2)

    n_lines = max(3, int(box_h / (0.22 * inch)) + 1)
    for i in range(1, n_lines + 1):
        ly = box_top - box_h * i / (n_lines + 1)
        cnv.line(MARGIN_X, ly, PAGE_W - MARGIN_X, ly)
    cnv.setStrokeColorRGB(0, 0, 0)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def build(output_path: str):
    fp_aspect = Image.open(FINGERPRINT_IMG).height / Image.open(FINGERPRINT_IMG).width
    cnv = canvas.Canvas(output_path, pagesize=letter)

    divider1_y = draw_header(cnv)
    sec1_title_y = divider1_y - 0.24 * inch

    # Sections 1 and 2 share the top row: dice rolls on the left,
    # 24 seed words on the right. The three QR templates then span
    # the full page width in one row beneath them.
    grid_left, grid_bottom, _ = draw_dice_grid(cnv, sec1_title_y)

    words_left = MARGIN_X + 2.70 * inch
    words_right_edge, words_col_bottom = draw_seed_words(
        cnv, sec1_title_y, fp_aspect, left_x=words_left,
        max_right=PAGE_W - MARGIN_X,
    )

    top_row_bottom = min(grid_bottom, words_col_bottom)
    qr_title_y = top_row_bottom - 0.34 * inch
    qr_bottom = draw_seed_qr(cnv, qr_title_y, MARGIN_X, max_width=2.10 * inch)

    sec1_bottom = qr_bottom

    divider2_y = sec1_bottom - 0.16 * inch
    cnv.setStrokeColorRGB(*GREY)
    cnv.setLineWidth(1)
    cnv.line(MARGIN_X, divider2_y, PAGE_W - MARGIN_X, divider2_y)
    cnv.setStrokeColorRGB(0, 0, 0)

    sec2_title_y = divider2_y - 0.22 * inch
    cnv.setFont("Helvetica-Bold", SECTION_HEADING_SIZE)
    cnv.drawString(MARGIN_X, sec2_title_y, "4. Dice Generated Hexadecimal Passphrase")

    t_grid_right, t_grid_top, footer_bottom = draw_hex_table(cnv, sec2_title_y)
    box_left = t_grid_right + 0.34 * inch
    box_bottom = draw_passphrase_grid_and_fingerprint(cnv, t_grid_top, box_left, fp_aspect)

    sec2_bottom = min(footer_bottom, box_bottom - 0.1 * inch)
    draw_notes(cnv, sec2_bottom)

    cnv.setFont("Helvetica-Bold", 8)
    cnv.drawRightString(PAGE_W - MARGIN_X, 0.22 * inch, "v1.0")

    cnv.showPage()
    cnv.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o", "--output", default="output/dice_wallet_worksheet.pdf",
        help="Output PDF path (default: output/dice_wallet_worksheet.pdf)",
    )
    args = parser.parse_args()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    build(args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
