"""Draw the made-up receipt photos used in the demo (run locally; the PNGs are committed).

    python backend/demo/make_receipts.py

Each receipt is a thermal-paper strip on a table, slightly rotated, so the AI has to read
a photo rather than clean text. Fonts: Windows Consolas.
"""
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent / "receipts"
FONT = "C:/Windows/Fonts/consola.ttf"
FONT_BOLD = "C:/Windows/Fonts/consolab.ttf"

RECEIPTS = {
    "hualien-home-mart": {
        "header": ["HUALIEN HOME MART", "Ji'an Branch", "No. 88 Zhongshan Rd, Ji'an", "Hualien County"],
        "meta": ["2026-10-24 14:32   POS 03", "Cashier: Chen"],
        "items": [("Waterproof tarp 3x4m", 4, 8.00), ("Rice 10 kg", 2, 12.00),
                  ("Kids raincoat", 6, 3.60), ("Prepaid gift card", 1, 8.80)],
        "footer": ["Paid: CARD ****4417", "Thank you! Stay safe."],
    },
    "taipei-corner-store": {
        "header": ["CORNER 24 MARKET", "Daan Store", "No. 12 Xinyi Rd Sec 3", "Taipei City"],
        "meta": ["2026-10-25 21:07   POS 01", "Cashier: Wu"],
        "items": [("Bottled water 6pk", 3, 4.50), ("Instant noodles 5pk", 4, 3.20),
                  ("Beer 6-pack", 2, 9.90), ("Phone top-up card", 1, 15.00)],
        "footer": ["Paid: CASH", "See you again!"],
    },
}


def draw_receipt(spec: dict, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    f = ImageFont.truetype(FONT, 26)
    fb = ImageFont.truetype(FONT_BOLD, 30)
    width = 560
    lines: list[tuple[str, ImageFont.FreeTypeFont, str]] = []  # (text, font, align)
    for i, h in enumerate(spec["header"]):
        lines.append((h, fb if i == 0 else f, "center"))
    lines.append(("", f, "left"))
    for m in spec["meta"]:
        lines.append((m, f, "left"))
    lines.append(("-" * 34, f, "left"))
    total = 0.0
    for name, qty, unit in spec["items"]:
        line_total = round(qty * unit, 2)
        total += line_total
        lines.append((name, f, "left"))
        lines.append((f"  {qty} x {unit:>6.2f}{line_total:>17.2f}", f, "left"))
    lines.append(("-" * 34, f, "left"))
    lines.append((f"TOTAL USD{total:>20.2f}", fb, "left"))
    lines.append(("", f, "left"))
    for ft in spec["footer"]:
        lines.append((ft, f, "center"))

    height = 60 + 36 * len(lines) + 40
    paper = Image.new("RGB", (width, height), (252, 250, 244))
    d = ImageDraw.Draw(paper)
    y = 40
    for text, font, align in lines:
        w = d.textlength(text, font=font)
        x = (width - w) / 2 if align == "center" else 36
        ink = rnd.randint(40, 70)
        d.text((x, y), text, font=font, fill=(ink, ink - 6, ink - 2))
        y += 36
    # thermal paper: faint horizontal banding and a torn-ish bottom edge
    for yy in range(0, height, 7):
        d.line([(0, yy), (width, yy)], fill=(247, 245, 238), width=1)
    for x in range(0, width, 14):
        d.polygon([(x, height), (x + 7, height - rnd.randint(4, 10)), (x + 14, height)], fill=(214, 204, 196))

    canvas = Image.new("RGB", (width + 260, height + 220), (214, 204, 196))  # wooden-table beige
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle([140, 122, 140 + width, 122 + height], fill=(60, 40, 30, 90))
    canvas.paste(shadow.filter(ImageFilter.GaussianBlur(12)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(12)))
    canvas.paste(paper, (130, 110))
    canvas = canvas.rotate(rnd.uniform(-3.5, 3.5), resample=Image.BICUBIC, expand=False, fillcolor=(214, 204, 196))
    return canvas.filter(ImageFilter.GaussianBlur(0.6))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for i, (name, spec) in enumerate(RECEIPTS.items()):
        img = draw_receipt(spec, seed=42 + i)
        img.save(OUT / f"{name}.jpg", quality=86)
        print(OUT / f"{name}.jpg", img.size)


if __name__ == "__main__":
    main()
