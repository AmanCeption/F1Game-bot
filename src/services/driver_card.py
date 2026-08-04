"""
driver_card.py
Pillow renderer for the AmanCeption F1 Racing Manager driver card,
recreating the "lewis_hamilton_f1_card.html" design as a PNG.

Public API (same call signature as before):
    generate_driver_card(...) -> bytes   # PNG bytes

Fonts required (place in a "fonts" folder next to this file):
    fonts/Orbitron.ttf            (variable font, weight axis 400-900)
    fonts/Rajdhani-Regular.ttf
    fonts/Rajdhani-Medium.ttf
    fonts/Rajdhani-SemiBold.ttf
    fonts/Rajdhani-Bold.ttf
All four are free/OFL licensed, from the Google Fonts repo:
    https://github.com/google/fonts/tree/main/ofl/orbitron
    https://github.com/google/fonts/tree/main/ofl/rajdhani
If the fonts are missing, the script falls back to DejaVuSans so it
never crashes -- it just won't look as close to the HTML reference.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import os
import math
import hashlib

# ---------------------------------------------------------------------------
# Canvas / scale
# ---------------------------------------------------------------------------
SCALE = 2                      # render at 2x the CSS px values -> crisp on phones
CARD_W = 520 * SCALE
PAD = 28 * SCALE

# colours (lifted straight from the CSS)
BG_BLACK = (10, 10, 10)
CARD_G1 = (26, 10, 10)
CARD_G2 = (13, 13, 13)
RED = (200, 16, 46)
RED_GLOW = (220, 20, 20)
GOLD = (255, 215, 0)
ORANGE = (255, 165, 0)
ORANGE_RED = (255, 69, 0)
TEXT_MAIN = (232, 232, 232)
TEXT_DIM = (176, 176, 176)
TEXT_FAINT = (128, 128, 128)
PANEL = (255, 255, 255, 8)             # ~0.03 alpha panels
PANEL_BORDER = (255, 255, 255, 13)
GREEN_1 = (0, 200, 83)
GREEN_2 = (100, 221, 23)
PURPLE_1 = (124, 77, 255)
PURPLE_2 = (179, 136, 255)

INFO_ICON_BG = {
    "red": (200, 16, 46, 38),
    "green": (0, 200, 83, 38),
    "blue": (33, 150, 243, 38),
    "purple": (179, 136, 255, 38),
    "yellow": (255, 193, 7, 38),
    "cyan": (0, 188, 212, 38),
}

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------
def _orbitron(size: int, weight: int = 700):
    path = os.path.join(FONT_DIR, "Orbitron.ttf")
    try:
        f = ImageFont.truetype(path, size)
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
        return f
    except Exception:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)


def _rajdhani(size: int, weight: str = "medium"):
    files = {
        "regular": "Rajdhani-Regular.ttf",
        "medium": "Rajdhani-Medium.ttf",
        "semibold": "Rajdhani-SemiBold.ttf",
        "bold": "Rajdhani-Bold.ttf",
    }
    path = os.path.join(FONT_DIR, files.get(weight, "Rajdhani-Medium.ttf"))
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except Exception:
            return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def _rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1),
                                         radius=radius, fill=255)
    return m


def _paste_rounded(base: Image.Image, layer: Image.Image, xy, radius):
    mask = _rounded_mask(layer.size, radius)
    base.paste(layer, xy, mask)


def _linear_gradient(size, c1, c2, angle=135):
    """Simple 2-stop linear gradient at a given angle (degrees)."""
    w, h = size
    grad = Image.new("RGB", (w, h))
    px = grad.load()
    rad = math.radians(angle)
    dx, dy = math.cos(rad), math.sin(rad)
    # project the four corners onto the gradient axis to normalise
    corners = [(0, 0), (w, 0), (0, h), (w, h)]
    projections = [x * dx + y * dy for x, y in corners]
    lo, hi = min(projections), max(projections)
    span = (hi - lo) or 1
    for y in range(h):
        for x in range(0, w, 2):  # step 2 for speed, upscale below fills gaps
            t = ((x * dx + y * dy) - lo) / span
            t = max(0.0, min(1.0, t))
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            px[x, y] = (r, g, b)
            if x + 1 < w:
                px[x + 1, y] = (r, g, b)
    return grad


def _radial_glow(size, color, center, radius, max_alpha=90):
    """Soft radial glow used behind the card and around the OVR ring."""
    w, h = size
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    px = glow.load()
    cx, cy = center
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            d = math.hypot(x - cx, y - cy) / radius
            if d < 1:
                a = int(max_alpha * (1 - d) ** 1.6)
                px[x, y] = (*color, a)
                if x + 1 < w:
                    px[x + 1, y] = (*color, a)
                if y + 1 < h:
                    px[x, y + 1] = (*color, a)
                if x + 1 < w and y + 1 < h:
                    px[x + 1, y + 1] = (*color, a)
    return glow


def _conic_ring(diameter, stops, thickness):
    """
    Approximates a CSS conic-gradient ring:
    stops = [(0.0, colorA), (0.6, colorB), (1.0, colorC)]
    """
    size = diameter * 4  # supersample for smoothness, downscale after
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    steps = 360
    cx = cy = size / 2
    r = size / 2

    def colour_at(t):
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                local = (t - t0) / ((t1 - t0) or 1)
                return tuple(int(c0[k] + (c1[k] - c0[k]) * local) for k in range(3))
        return stops[-1][1]

    for i in range(steps):
        t = i / steps
        c = colour_at(t)
        start = -90 + i * (360 / steps) - 1
        end = -90 + (i + 1) * (360 / steps) + 1
        d.pieslice((cx - r, cy - r, cx + r, cy + r), start, end, fill=c)

    img = img.resize((diameter, diameter), Image.LANCZOS)
    # punch the centre hole out (ring, not a filled disc)
    hole = diameter - thickness * 2
    hole_mask = Image.new("L", (diameter, diameter), 255)
    hm = ImageDraw.Draw(hole_mask)
    off = (diameter - hole) / 2
    hm.ellipse((off, off, off + hole, off + hole), fill=0)
    img.putalpha(hole_mask)
    return img


def _text_w(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0]


def _fit_text(draw, text, font_fn, max_w, start_size, min_size=14, weight=None):
    size = start_size
    while size > min_size:
        f = font_fn(size, weight) if weight else font_fn(size)
        if _text_w(draw, text, f) <= max_w:
            return f
        size -= 2
    return font_fn(min_size, weight) if weight else font_fn(min_size)


def _draw_rounded_panel(img, box, radius, fill_rgba=PANEL, border_rgba=PANEL_BORDER):
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(box, radius=radius, fill=fill_rgba, outline=border_rgba, width=1)
    img.alpha_composite(overlay)


def _stat_icon(draw, cx, cy, r, kind, color=(160, 160, 160)):
    """Minimal geometric substitute for the SVG icon set."""
    w = max(2, r // 8)
    if kind == "pace":                       # clock
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=w)
        draw.line((cx, cy, cx, cy - r * 0.6), fill=color, width=w)
        draw.line((cx, cy, cx + r * 0.4, cy), fill=color, width=w)
    elif kind == "racecraft":                 # steering-wheel-ish arc
        draw.arc((cx - r, cy - r, cx + r, cy + r), 200, 340, fill=color, width=w)
        draw.line((cx - r, cy + r * 0.3, cx + r, cy + r * 0.3), fill=color, width=w)
    elif kind == "skill":                     # target
        draw.arc((cx - r, cy - r, cx + r, cy + r), 200, 470, fill=color, width=w)
        draw.arc((cx - r, cy - r, cx + r, cy + r), 20, 200, fill=color, width=w)
    elif kind == "consistency":                # concentric rings
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=w)
        draw.ellipse((cx - r * 0.35, cy - r * 0.35, cx + r * 0.35, cy + r * 0.35),
                     outline=color, width=w)
    elif kind == "wet":                        # droplet
        draw.polygon([(cx, cy - r), (cx - r * 0.7, cy + r * 0.4),
                      (cx + r * 0.7, cy + r * 0.4)], outline=color, width=w)
        draw.arc((cx - r * 0.7, cy - r * 0.1, cx + r * 0.7, cy + r * 0.9),
                  0, 180, fill=color, width=w)
    elif kind == "overtake":                   # lightning bolt
        pts = [(cx + r * 0.15, cy - r), (cx - r * 0.5, cy + r * 0.15),
               (cx, cy + r * 0.15), (cx - r * 0.15, cy + r),
               (cx + r * 0.5, cy - r * 0.15), (cx, cy - r * 0.15)]
        draw.polygon(pts, outline=color, width=w)
    elif kind == "defence":                    # shield
        pts = [(cx, cy - r), (cx + r * 0.8, cy - r * 0.5), (cx + r * 0.8, cy + r * 0.2),
               (cx, cy + r), (cx - r * 0.8, cy + r * 0.2), (cx - r * 0.8, cy - r * 0.5)]
        draw.polygon(pts, outline=color, width=w)


def _flag_swatch(nationality: str, size):
    """
    Deterministic abstract flag stand-in (two-tone block, colour derived
    from the nationality string) so every nationality renders consistently
    without needing a bundled flag-image asset pack. Swap in real flag PNGs
    by nationality code if/when you have an assets folder.
    """
    h = hashlib.md5(nationality.encode()).hexdigest()
    c1 = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    c2 = tuple(int(h[i:i + 2], 16) for i in (6, 8, 10))
    img = Image.new("RGB", size, c1)
    d = ImageDraw.Draw(img)
    d.rectangle((0, size[1] * 0.4, size[0], size[1]), fill=c2)
    return img


def _stat_bar(img, x, y, w, h, pct, c1, c2):
    _draw_rounded_panel(img, (x, y, x + w, y + h), h / 2,
                        fill_rgba=(255, 255, 255, 20), border_rgba=None)
    fill_w = max(int(w * max(0, min(100, pct)) / 100), h)
    grad = _linear_gradient((fill_w, h), c1, c2, angle=0)
    grad = grad.convert("RGBA")
    mask = _rounded_mask((fill_w, h), h / 2)
    img.paste(grad, (int(x), int(y)), mask)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def generate_driver_card(
    name: str,
    nationality: str,
    age: int,
    number: int | None,
    is_fictional: bool,
    skill: int,
    racecraft: int,
    pace: int,
    consistency: int,
    wet_weather: int,
    overtaking: int,
    defence: int,
    development_potential: int,
    base_salary: int,
    is_free_agent: bool,
    current_team: str | None = None,
) -> bytes:
    s = SCALE

    # ---- figure out card height from content (mirrors the HTML flow) ----
    ring_d = int(100 * s)
    header_h = ring_d + int(46 * s)   # ring + "OVR" label + breathing room
    main_h = 220 * s
    dev_h = 90 * s
    grid_h = 2 * 62 * s + 12 * s
    footer_h = 60 * s
    gaps = (20 + 20 + 16 + 20) * s
    card_h = PAD * 2 + header_h + main_h + dev_h + grid_h + footer_h + gaps

    outer_w, outer_h = CARD_W + 40 * s, int(card_h) + 40 * s
    canvas = Image.new("RGBA", (outer_w, outer_h), BG_BLACK + (255,))

    # card background gradient (diagonal, dark red -> near black -> dark red)
    card_w, card_h = CARD_W, int(card_h)
    grad = _linear_gradient((card_w, card_h), CARD_G1, CARD_G2, angle=135)
    card = grad.convert("RGBA")

    # red glow blob (top-right, like ::before)
    glow = _radial_glow((card_w, card_h), RED_GLOW,
                         (card_w * 1.05, card_h * -0.05), radius=card_w * 0.55, max_alpha=70)
    card.alpha_composite(glow)

    draw = ImageDraw.Draw(card)

    # ------------------------------------------------------------------ #
    # Header
    # ------------------------------------------------------------------ #
    x = PAD
    y = PAD

    name_font = _orbitron(int(38 * s), 900)
    parts = name.upper().split(" ", 1)
    first_line = parts[0]
    second_line = parts[1] if len(parts) > 1 else ""
    draw.text((x, y), first_line, font=_orbitron(int(26 * s), 700), fill=TEXT_MAIN)
    ny = y + int(30 * s)
    if second_line:
        draw.text((x, ny), second_line, font=name_font, fill=TEXT_MAIN)
        ny += int(46 * s)
    else:
        ny += int(4 * s)

    # nationality / age row
    flag_w, flag_h = int(28 * s), int(18 * s)
    flag_img = _flag_swatch(nationality, (flag_w, flag_h))
    _paste_rounded(card, flag_img.convert("RGBA"), (x, ny + int(4 * s)), radius=3 * s)

    info_font = _rajdhani(int(14 * s), "semibold")
    tx = x + flag_w + int(10 * s)
    draw.text((tx, ny), nationality.upper(), font=info_font, fill=TEXT_DIM)
    tx += _text_w(draw, nationality.upper(), info_font) + int(10 * s)
    dot_r = int(2 * s)
    draw.ellipse((tx, ny + int(6 * s), tx + dot_r * 2, ny + int(6 * s) + dot_r * 2), fill=RED)
    tx += dot_r * 2 + int(10 * s)
    draw.text((tx, ny), f"AGE {age}", font=info_font, fill=TEXT_DIM)

    # OVR ring
    ring_cx = card_w - PAD - ring_d // 2
    ring_cy = y + ring_d // 2
    thickness = int(10 * s)
    ring = _conic_ring(ring_d, [(0.0, GOLD), (0.6, ORANGE), (1.0, ORANGE_RED)],
                        thickness=thickness)
    inner_glow = _radial_glow((ring_d, ring_d), GOLD, (ring_d / 2, ring_d / 2),
                               radius=ring_d * 0.6, max_alpha=60)
    ring_layer = Image.new("RGBA", (ring_d, ring_d), (0, 0, 0, 0))
    ring_layer.alpha_composite(inner_glow)
    ring_layer.alpha_composite(ring)
    card.alpha_composite(ring_layer, (ring_cx - ring_d // 2, ring_cy - ring_d // 2))

    # fill the ring's hole with the dark card colour so the value has contrast
    hole_d = ring_d - thickness * 2
    draw.ellipse((ring_cx - hole_d / 2, ring_cy - hole_d / 2,
                  ring_cx + hole_d / 2, ring_cy + hole_d / 2), fill=(13, 13, 13, 255))

    overall = round((skill + racecraft + pace) / 3)
    ovr_font = _orbitron(int(48 * s), 900)
    ovr_text = str(overall)
    tw = _text_w(draw, ovr_text, ovr_font)
    draw.text((ring_cx - tw / 2, ring_cy - int(28 * s)), ovr_text, font=ovr_font, fill=GOLD)
    lbl_font = _orbitron(int(13 * s), 700)
    lbl_w = _text_w(draw, "OVR", lbl_font)
    draw.text((ring_cx - lbl_w / 2, ring_cy + ring_d // 2 + int(6 * s)), "OVR",
              font=lbl_font, fill=GOLD)

    # ------------------------------------------------------------------ #
    # Main content: photo + stats
    # ------------------------------------------------------------------ #
    my = y + header_h
    photo_w, photo_h = int(180 * s), int(220 * s)

    photo = _linear_gradient((photo_w, photo_h), (26, 10, 10), (42, 5, 5), angle=135)
    photo = photo.convert("RGBA")
    pd = ImageDraw.Draw(photo)
    # faint centred silhouette mark instead of an emoji (font-independent)
    pd.ellipse((photo_w * 0.30, photo_h * 0.20, photo_w * 0.70, photo_h * 0.45),
               outline=(255, 255, 255, 60), width=int(3 * s))
    pd.arc((photo_w * 0.15, photo_h * 0.40, photo_w * 0.85, photo_h * 0.95),
           200, 340, fill=(255, 255, 255, 60), width=int(4 * s))
    # bottom fade
    fade = _linear_gradient((photo_w, int(photo_h * 0.4)), (0, 0, 0), (0, 0, 0), angle=90)
    fade = fade.convert("RGBA")
    for yy in range(fade.height):
        a = int(200 * (yy / fade.height))
        for xx in range(0, fade.width, 3):
            fade.putpixel((xx, yy), (0, 0, 0, a))
    photo.alpha_composite(fade, (0, photo_h - fade.height))

    sig_font = _rajdhani(int(16 * s), "medium")
    initials = f"{name[0]}. {name.split(' ')[-1]}" if " " in name else name
    pd.text((int(12 * s), photo_h - int(30 * s)), initials, font=sig_font,
             fill=(255, 255, 255, 230))
    if number is not None:
        num_font = _orbitron(int(30 * s), 900)
        num_text = str(number)
        nw = _text_w(pd, num_text, num_font)
        pd.text((photo_w - int(12 * s) - nw, photo_h - int(38 * s)), num_text,
                 font=num_font, fill=RED)

    _paste_rounded(card, photo, (x, my), radius=16 * s)

    # stats panel
    stats_x = x + photo_w + int(20 * s)
    stats_w = card_w - PAD - stats_x
    _draw_rounded_panel(card, (stats_x, my, stats_x + stats_w, my + photo_h), 16 * s)

    stats = [
        ("PACE", pace, "pace"),
        ("RACECRAFT", racecraft, "racecraft"),
        ("SKILL", skill, "skill"),
        ("CONSISTENCY", consistency, "consistency"),
        ("WET", wet_weather, "wet"),
        ("OVERTAKE", overtaking, "overtake"),
        ("DEFENCE", defence, "defence"),
    ]
    row_h = photo_h / len(stats)
    label_font = _rajdhani(int(12 * s), "semibold")
    val_font = _orbitron(int(15 * s), 700)
    icon_r = int(9 * s)

    for i, (label, val, kind) in enumerate(stats):
        ry = my + int(14 * s) + i * row_h
        icon_cx = stats_x + int(14 * s) + icon_r
        icon_cy = ry + row_h / 2 - int(4 * s)
        _stat_icon(draw, icon_cx, icon_cy, icon_r, kind, color=(160, 160, 160))

        bar_x = stats_x + int(14 * s) + icon_r * 2 + int(10 * s)
        bar_w = stats_x + stats_w - int(14 * s) - int(38 * s) - bar_x
        draw.text((bar_x, ry), label, font=label_font, fill=(192, 192, 192))
        bar_y = ry + int(18 * s)
        _stat_bar(card, bar_x, bar_y, bar_w, int(8 * s), val, GREEN_1, GREEN_2)

        val_text = str(val)
        vw = _text_w(draw, val_text, val_font)
        draw.text((stats_x + stats_w - int(14 * s) - vw, ry + int(4 * s)), val_text,
                   font=val_font, fill=GREEN_2)

    # ------------------------------------------------------------------ #
    # Development potential
    # ------------------------------------------------------------------ #
    dy = my + main_h
    _draw_rounded_panel(card, (x, dy, card_w - PAD, dy + dev_h), 16 * s)
    dev_title_font = _rajdhani(int(15 * s), "bold")
    draw.text((x + int(20 * s), dy + int(14 * s)), "DEVELOPMENT POTENTIAL",
              font=dev_title_font, fill=TEXT_MAIN)
    dev_val_font = _orbitron(int(18 * s), 700)
    dev_val_text = f"{development_potential}/100"
    dvw = _text_w(draw, dev_val_text, dev_val_font)
    draw.text((card_w - PAD - int(20 * s) - dvw, dy + int(12 * s)), dev_val_text,
              font=dev_val_font, fill=PURPLE_2)
    bar_y = dy + int(46 * s)
    _stat_bar(card, x + int(20 * s), bar_y, card_w - PAD * 2 - int(40 * s), int(14 * s),
              development_potential, PURPLE_1, PURPLE_2)

    # ------------------------------------------------------------------ #
    # Info grid
    # ------------------------------------------------------------------ #
    gy = dy + dev_h + int(16 * s)
    status_text = "Free Agent" if is_free_agent else "Contracted"
    info_items = [
        ("TEAM", current_team or "Free Agent", "red"),
        ("DRIVER NO.", str(number if number is not None else "--"), "yellow"),
        ("SALARY", f"${base_salary:,}", "green"),
        ("POTENTIAL", f"{development_potential}/100", "purple"),
        ("STATUS", status_text, "blue"),
        ("TYPE", "Fictional" if is_fictional else "Real", "cyan"),
    ]
    cols, rows = 2, 3
    gutter = int(12 * s)
    cell_w = (card_w - PAD * 2 - gutter) / cols
    cell_h = int(60 * s)
    icon_font = _rajdhani(int(15 * s), "bold")
    label_font2 = _rajdhani(int(10 * s), "semibold")
    value_font = _rajdhani(int(15 * s), "bold")

    for i, (label, value, colour) in enumerate(info_items):
        col, row = i % cols, i // cols
        cx0 = x + col * (cell_w + gutter)
        cy0 = gy + row * (cell_h + gutter)
        _draw_rounded_panel(card, (cx0, cy0, cx0 + cell_w, cy0 + cell_h), 12 * s)

        icon_box = int(36 * s)
        icon_xy = (cx0 + int(14 * s), cy0 + (cell_h - icon_box) / 2)
        overlay = Image.new("RGBA", card.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rounded_rectangle((icon_xy[0], icon_xy[1], icon_xy[0] + icon_box,
                              icon_xy[1] + icon_box), radius=10 * s,
                              fill=INFO_ICON_BG[colour])
        card.alpha_composite(overlay)
        mark = label[0]
        mw = _text_w(draw, mark, icon_font)
        draw.text((icon_xy[0] + icon_box / 2 - mw / 2, icon_xy[1] + icon_box / 2 - 9 * s),
                  mark, font=icon_font, fill=TEXT_MAIN)

        tx0 = icon_xy[0] + icon_box + int(12 * s)
        draw.text((tx0, cy0 + int(12 * s)), label, font=label_font2, fill=TEXT_FAINT)
        vfont = _fit_text(draw, value, _rajdhani, cell_w - (tx0 - cx0) - int(10 * s),
                          int(15 * s), min_size=10, weight="bold")
        draw.text((tx0, cy0 + int(28 * s)), value, font=vfont, fill=TEXT_MAIN)

    # ------------------------------------------------------------------ #
    # Footer
    # ------------------------------------------------------------------ #
    fy = gy + rows * cell_h + (rows - 1) * gutter + int(16 * s)
    draw.line((x, fy, card_w - PAD, fy), fill=(255, 255, 255, 15), width=1)
    fy += int(16 * s)

    chk = int(32 * s)
    checker = Image.new("RGBA", (chk, chk), (0, 0, 0, 0))
    cd = ImageDraw.Draw(checker)
    n = 4
    cell = chk / n
    for r_ in range(n):
        for c_ in range(n):
            col = (51, 51, 51, 255) if (r_ + c_) % 2 == 0 else (102, 102, 102, 255)
            cd.rectangle((c_ * cell, r_ * cell, (c_ + 1) * cell, (r_ + 1) * cell), fill=col)
    checker_mask = _rounded_mask((chk, chk), 6 * s)
    card.paste(checker, (int(x), int(fy)), checker_mask)

    pb_label_font = _rajdhani(int(9 * s), "semibold")
    pb_brand_font = _orbitron(int(14 * s), 700)
    ptx = x + chk + int(12 * s)
    draw.text((ptx, fy), "POWERED BY", font=pb_label_font, fill=TEXT_FAINT)
    draw.text((ptx, fy + int(12 * s)), "AMANCEPTION", font=pb_brand_font, fill=TEXT_MAIN)

    center_font = _rajdhani(int(11 * s), "semibold")
    center_text = "F1 RACING MANAGER"
    cw = _text_w(draw, center_text, center_font)
    draw.text((card_w / 2 - cw / 2, fy + int(6 * s)), center_text, font=center_font,
              fill=TEXT_FAINT)

    f1_font = _orbitron(int(24 * s), 900)
    f1w = _text_w(draw, "F1", f1_font)
    draw.text((card_w - PAD - f1w, fy), "F1", font=f1_font, fill=(224, 224, 224))

    # ------------------------------------------------------------------ #
    # Composite card onto outer canvas (drop shadow + glow around edges)
    # ------------------------------------------------------------------ #
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((20 * s, 20 * s + 10 * s, 20 * s + card_w, 20 * s + card_h + 10 * s),
                         radius=24 * s, fill=(0, 0, 0, 180))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18 * s))
    canvas.alpha_composite(shadow)

    mask = _rounded_mask((card_w, card_h), 24 * s)
    canvas.paste(card, (20 * s, 20 * s), mask)

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


if __name__ == "__main__":
    png = generate_driver_card(
        name="Lewis Hamilton",
        nationality="British",
        age=39,
        number=44,
        is_fictional=False,
        skill=97,
        racecraft=98,
        pace=96,
        consistency=95,
        wet_weather=99,
        overtaking=96,
        defence=97,
        development_potential=60,
        base_salary=50_000_000,
        is_free_agent=False,
        current_team="AmanCaption F1",
    )
    with open("/home/claude/preview.png", "wb") as f:
        f.write(png)
    print("wrote preview.png")
