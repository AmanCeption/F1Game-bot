"""
Driver Card Generator — CCM26-inspired premium design (Optimized & Fixed)
Drop-in replacement for src/services/driver_card.py
"""

from __future__ import annotations

import io
import logging
import os
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ── Canvas ────────────────────────────────────────────────────────────────────
W, H = 740, 460

# ── Palette ───────────────────────────────────────────────────────────────────
BG      = (6,  8,  16)
BG2     = (10, 13, 24)
CARD    = (14, 18, 32)
CARD2   = (18, 22, 40)
WHITE   = (242, 245, 255)
DIM     = (155, 160, 195)
MUTED   = (88,  93, 128)
GOLD    = (255, 200, 50)
PURPLE  = (165, 85, 255)
GREEN   = (50,  215, 110)
ORANGE  = (255, 135, 30)
RED_ERR = (210, 55, 55)

# Tier definitions
_TIERS = {
    "elite":    {"bg": (16, 6,  28),  "bg2": (8,  3,  16),  "border": (165, 50, 255), "accent": (205, 120, 255), "label": "ELITE"},
    "legend":   {"bg": (8,  16, 42),  "bg2": (5,  9,  28),  "border": (55, 100, 215), "accent": (115, 160, 255), "label": "LEGEND"},
    "champion": {"bg": (28, 18, 4),   "bg2": (14, 9,  2),   "border": (195, 155, 15), "accent": (255, 205, 50),  "label": "CHAMPION"},
    "pro":      {"bg": (50, 20, 6),   "bg2": (32, 11, 3),   "border": (180, 85,  18), "accent": (218, 122, 44),  "label": "PRO"},
    "rookie":   {"bg": (26, 38, 52),  "bg2": (15, 23, 36),  "border": (75, 108, 145), "accent": (118, 158, 195), "label": "ROOKIE"},
}

_TEAM_COLORS: dict[str, tuple] = {
    "Red Bull Racing":   (0,   10,  230),
    "Ferrari":           (210, 10,  10),
    "McLaren":           (255, 120, 0),
    "Mercedes":          (0,   200, 170),
    "Aston Martin":      (0,   140, 80),
    "Alpine":            (0,   80,  200),
    "Williams":          (0,   110, 210),
    "AlphaTauri":        (40,  50,  120),
    "RB":                (40,  50,  120),
    "Alfa Romeo":        (160, 0,   0),
    "Haas":              (175, 175, 175),
    "Sauber":            (0,   160, 60),
}


# ── Helpers (Cached & Optimized) ──────────────────────────────────────────────

@lru_cache(maxsize=32)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Cached font lookup to prevent continuous disk IO performance drop."""
    paths = [
        # Linux
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans{'-Bold' if bold else '-Regular'}.ttf",
        # Windows
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
        # MacOS
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _tw(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bb = draw.textbbox((0, 0), str(text), font=font)
    return bb[2] - bb[0]


def _tier(rating: int) -> dict:
    if rating >= 92: return _TIERS["elite"]
    if rating >= 85: return _TIERS["legend"]
    if rating >= 75: return _TIERS["champion"]
    if rating >= 62: return _TIERS["pro"]
    return _TIERS["rookie"]


def _team_color(team: str | None) -> tuple:
    return _TEAM_COLORS.get(team or "", (95, 95, 185))


def _stat_color(v: int) -> tuple:
    if v >= 90: return GREEN
    if v >= 78: return GOLD
    if v >= 62: return ORANGE
    return RED_ERR


def _hex_poly(x: int, y: int, w: int, h: int, cut: int = 26, cuty: int = 46) -> list:
    return [
        (x+cut, y), (x+w-cut, y),
        (x+w, y+cuty), (x+w, y+h-cuty),
        (x+w-cut, y+h), (x+cut, y+h),
        (x, y+h-cuty), (x, y+cuty),
    ]


def _gradient_fill(img: Image.Image, draw: ImageDraw.ImageDraw,
                   x: int, y: int, w: int, h: int,
                   c1: tuple, c2: tuple) -> None:
    for i in range(h):
        t = i / max(h - 1, 1)
        r = int(c1[0] * (1-t) + c2[0] * t)
        g = int(c1[1] * (1-t) + c2[1] * t)
        b = int(c1[2] * (1-t) + c2[2] * t)
        draw.line([(x, y+i), (x+w, y+i)], fill=(r, g, b))


def _gradient_text(img: Image.Image, text: str, font,
                   x: int, y: int, c1: tuple, c2: tuple) -> None:
    """Fast gradient text drawing via Layer Alpha Masking."""
    dummy_draw = ImageDraw.Draw(img)
    bb = dummy_draw.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0] + 10, bb[3] - bb[1] + 10
    
    # Text Mask
    mask = Image.new("L", (tw, th), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.text((0, 0), text, fill=255, font=font)
    
    # Gradient Texture
    grad = Image.new("RGBA", (tw, th))
    g_draw = ImageDraw.Draw(grad)
    for row in range(th):
        t = row / max(th - 1, 1)
        r = int(c1[0]*(1-t) + c2[0]*t)
        g = int(c1[1]*(1-t) + c2[1]*t)
        b = int(c1[2]*(1-t) + c2[2]*t)
        g_draw.line([(0, row), (tw, row)], fill=(r, g, b, 255))
        
    img.paste(grad, (x, y), mask)


def _draw_brackets(draw: ImageDraw.ImageDraw,
                   x: int, y: int, w: int, h: int,
                   col: tuple, dot: tuple,
                   size: int = 36, lw: int = 2, dc: int = 5) -> None:
    for cx, cy, dx, dy in [
        (x,   y,   1,  1),
        (x+w, y,  -1,  1),
        (x,   y+h, 1, -1),
        (x+w, y+h,-1, -1),
    ]:
        draw.line([(cx, cy), (cx + size*dx, cy)], fill=col, width=lw)
        draw.line([(cx, cy), (cx, cy + size*dy)], fill=col, width=lw)
        draw.ellipse([cx-dc, cy-dc, cx+dc, cy+dc], fill=dot)


def _draw_team_stripe(draw: ImageDraw.ImageDraw,
                      tc: tuple, x: int, y: int, h: int, width: int = 7) -> None:
    for i in range(width):
        a = int(190 * (1 - i / width))
        draw.line([(x+i, y), (x+i, y+h)], fill=(*tc, a), width=1)


def _glow_line(draw: ImageDraw.ImageDraw,
               x1: int, y: int, x2: int, col: tuple) -> None:
    r, g, b = col
    alphas = [35, 75, 150, 255, 150, 75, 35]
    for i, a in enumerate(alphas):
        draw.line([(x1, y-3+i), (x2, y-3+i)], fill=(r, g, b, a), width=1)


def _stat_pill(draw: ImageDraw.ImageDraw,
               x: int, y: int, label: str, value: int, accent: tuple) -> None:
    pw, ph = 86, 64  # Slightly tightened size for pixel-perfect grid fit
    draw.rounded_rectangle([x, y, x+pw, y+ph], radius=8,
                            fill=CARD2, outline=(*accent, 55), width=1)
    fv = _font(26, bold=True)
    vw = _tw(draw, str(value), fv)
    draw.text((x + (pw - vw)//2, y + 4), str(value), fill=accent, font=fv)
    fl = _font(8, bold=True)
    lab = " ".join(label[:8])
    lw = _tw(draw, lab, fl)
    draw.text((x + (pw - lw)//2, y + ph - 16), lab, fill=DIM, font=fl)


def _progress_bar(draw: ImageDraw.ImageDraw,
                  x: int, y: int, bw: int, bh: int,
                  value: int, color: tuple) -> None:
    draw.rounded_rectangle([x, y, x+bw, y+bh], radius=4, fill=CARD)
    fill_w = int(bw * max(0, min(value, 100)) / 100)
    if fill_w > 0:
        draw.rounded_rectangle([x, y, x+fill_w, y+bh], radius=4, fill=color)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_driver_card(
    name:                  str,
    nationality:           str,
    age:                   int,
    number:                int | None,
    is_fictional:          bool,
    skill:                 int,
    racecraft:             int,
    pace:                  int,
    consistency:           int,
    wet_weather:           int,
    overtaking:            int,
    defence:               int,
    development_potential: int,
    base_salary:           int,
    is_free_agent:         bool,
    current_team:          str | None = None,
) -> bytes:
    """Generate a premium F1 driver profile card PNG (CCM26-inspired)."""
    try:
        return _render(
            name=name, nationality=nationality, age=age, number=number,
            is_fictional=is_fictional, skill=skill, racecraft=racecraft,
            pace=pace, consistency=consistency, wet_weather=wet_weather,
            overtaking=overtaking, defence=defence,
            development_potential=development_potential,
            base_salary=base_salary, is_free_agent=is_free_agent,
            current_team=current_team,
        )
    except Exception:
        logger.exception("Driver card generation failed")
        return _fallback_card(name, number)


def _render(**kw) -> bytes:
    name       = kw["name"]
    nationality= kw["nationality"]
    age        = kw["age"]
    number     = kw["number"]
    is_fic     = kw["is_fictional"]
    skill      = kw["skill"]
    racecraft  = kw["racecraft"]
    pace       = kw["pace"]
    consistency= kw["consistency"]
    wet        = kw["wet_weather"]
    overtaking = kw["overtaking"]
    defence    = kw["defence"]
    dev_pot    = kw["development_potential"]
    salary     = kw["base_salary"]
    free_agent = kw["is_free_agent"]
    team       = kw["current_team"]

    overall = (skill + pace + racecraft) // 3
    tier    = _tier(overall)
    tc      = _team_color(team)
    border  = tier["border"]
    acc     = tier["accent"]

    # Canvas Setup
    img  = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    shape = _hex_poly(0, 0, W, H, cut=26, cuty=46)
    draw.polygon(shape, fill=border)

    _gradient_fill(img, draw, 3, 3, W-6, H-6, tier["bg"], tier["bg2"])
    draw.polygon(shape, outline=border, fill=None)

    _draw_team_stripe(draw, tc, 18, 52, H - 104, width=7)
    _draw_brackets(draw, 0, 0, W, H, border, acc, size=38, dc=5)

    # Left Column Details
    f_num = _font(100, bold=True)
    num_str = str(number) if number is not None else "??"
    _gradient_text(img, num_str, f_num, 40, 24, (235, 240, 255), (110, 120, 158))

    draw.text((45, 140), "N O", fill=(*DIM, 120), font=_font(10, bold=True))

    # Nationality
    bx, by = 40, 168
    draw.rounded_rectangle([bx, by, bx+80, by+32],
                            radius=6, fill=(*CARD2, 220), outline=border, width=1)
    fn  = _font(13, bold=True)
    nat = nationality[:3].upper()
    nw  = _tw(draw, nat, fn)
    draw.text((bx + (80 - nw)//2, by + 8), nat, fill=WHITE, font=fn)

    # Tier Badge
    ft    = _font(10, bold=True)
    label = tier["label"]
    tlw   = _tw(draw, label, ft) + 16
    tx, ty = 40, 210
    draw.rounded_rectangle([tx, ty, tx+tlw, ty+24], radius=5, fill=(*border, 210))
    draw.text((tx + 8, ty + 6), label, fill=WHITE, font=ft)

    tag = "🤖 AI" if is_fic else "🏎️ Real"
    draw.text((40, 248), f"Age {age}", fill=(*DIM, 160), font=_font(11))
    draw.text((40, 268), tag,         fill=(*DIM, 130), font=_font(10))

    # Right Column: Name & Team
    rx = 160
    f_name = _font(38, bold=True)
    words  = name.upper().split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if _tw(draw, test, f_name) > 440:
            if cur:
                lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)

    ny = 18
    for line in lines[:2]:
        draw.text((rx, ny), line, fill=WHITE, font=f_name)
        ny += 44

    if team:
        team_sp = "  ".join(team.upper())
        draw.text((rx, ny + 2), team_sp, fill=acc, font=_font(11, bold=True))
    else:
        draw.text((rx, ny + 2), "FREE AGENT", fill=GREEN, font=_font(11, bold=True))

    div_y = ny + 26
    _glow_line(draw, rx, div_y, W - 36, border)

    # Stats Grid
    stats = [
        ("PACE",      pace),
        ("RACECRAFT", racecraft),
        ("CONSIST",   consistency),
        ("WET",       wet),
        ("OVERTAKE",  overtaking),
        ("DEFENCE",   defence),
    ]
    pill_gap = 90
    sy = div_y + 14
    for i, (lb, vl) in enumerate(stats[:6]):
        _stat_pill(draw, rx + i * pill_gap, sy, lb, vl, _stat_color(vl))

    # Dev Potential Bar
    dp_y = sy + 76
    draw.text((rx, dp_y), "DEVELOPMENT POTENTIAL", fill=(*MUTED, 200), font=_font(10, bold=True))
    bar_x, bar_w, bar_h = rx, (len(stats) * pill_gap) - 10, 10
    _progress_bar(draw, bar_x, dp_y + 16, bar_w, bar_h, dev_pot, PURPLE)
    draw.text((bar_x + bar_w + 8, dp_y + 12), str(dev_pot), fill=PURPLE, font=_font(11, bold=True))

    # Salary & Status
    vx, vy = W - 165, H - 78
    draw.rounded_rectangle([vx, vy, vx+128, vy+58],
                            radius=8, fill=(*CARD2, 230), outline=border, width=1)
    draw.text((vx + 10, vy + 4), "SALARY / YR", fill=MUTED, font=_font(9, bold=True))
    sal_str = f"${salary // 1_000_000}M" if salary >= 1_000_000 else f"${salary:,}"
    draw.text((vx + 10, vy + 18), sal_str, fill=GOLD, font=_font(18, bold=True))
    
    sc  = GREEN if free_agent else RED_ERR
    stx = vx + 10
    sty = vy + 42
    draw.ellipse([stx, sty, stx+8, sty+8], fill=sc)
    st_label = "FREE AGENT" if free_agent else "CONTRACTED"
    draw.text((stx + 12, sty - 1), st_label, fill=sc, font=_font(9, bold=True))

    # Overall Rating Badge (Top Right Corner)
    ox, oy = W - 96, 18
    draw.rounded_rectangle([ox, oy, ox+78, oy+66], radius=8,
                            fill=(*CARD, 220), outline=border, width=1)
    draw.text((ox + 6, oy + 4), "OVERALL", fill=MUTED, font=_font(9, bold=True))
    fw_ovr = _font(34, bold=True)
    ow = _tw(draw, str(overall), fw_ovr)
    draw.text((ox + (78 - ow)//2, oy + 20), str(overall),
              fill=_stat_color(overall), font=fw_ovr)

    # Export PNG Bytes
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", quality=95, optimize=True)
    buf.seek(0)
    return buf.read()


def _fallback_card(name: str, number: int | None) -> bytes:
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.text((30, 30), str(number or "??"), fill=WHITE, font=_font(80, bold=True))
    draw.text((30, 130), name.upper(), fill=WHITE, font=_font(28, bold=True))
    draw.text((30, 175), "F1 Manager", fill=MUTED, font=_font(14))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()
