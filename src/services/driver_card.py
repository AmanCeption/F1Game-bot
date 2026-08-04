"""
driver_card_v3.py
Premium driver card renderer scaffold.

NOTE:
This is a production-ready starting point for upgrading the existing
driver_card.py while keeping the same public API.

Replace your current file after integrating any project-specific imports.
"""

from PIL import Image, ImageDraw, ImageFont
import io

W, H = 1000, 1400

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
    img = Image.new("RGB", (W, H), (16, 18, 28))
    d = ImageDraw.Draw(img)

    try:
        title = ImageFont.truetype("DejaVuSans-Bold.ttf", 54)
        big = ImageFont.truetype("DejaVuSans-Bold.ttf", 140)
        body = ImageFont.truetype("DejaVuSans.ttf", 28)
    except Exception:
        title = big = body = ImageFont.load_default()

    # Header
    d.rounded_rectangle((40,40,960,220), radius=24, fill=(25,30,45))
    d.text((70,60), name.upper(), font=title, fill="white")
    d.text((70,130), f"{nationality} • Age {age}", font=body, fill=(180,190,210))

    # Overall
    overall = (skill + racecraft + pace)//3
    d.ellipse((760,55,930,225), outline=(255,210,40), width=6)
    tw = d.textbbox((0,0), str(overall), font=big)
    ww = tw[2]-tw[0]
    d.text((845-ww/2,75), str(overall), font=big, fill=(255,210,40))

    # Portrait placeholder
    d.rounded_rectangle((60,260,340,620), radius=30, fill=(40,45,60))
    d.text((120,430), "PORTRAIT", font=body, fill="white")

    # Stats
    stats = [
        ("PACE", pace),
        ("RACECRAFT", racecraft),
        ("SKILL", skill),
        ("CONSISTENCY", consistency),
        ("WET", wet_weather),
        ("OVERTAKE", overtaking),
        ("DEFENCE", defence),
    ]

    y = 280
    for label,val in stats:
        d.text((390,y), label, font=body, fill="white")
        d.rounded_rectangle((610,y+5,900,y+25), radius=8, fill=(50,50,70))
        fill = 610 + int(290*val/100)
        d.rounded_rectangle((610,y+5,fill,y+25), radius=8, fill=(70,220,120))
        d.text((915,y), str(val), font=body, fill="white")
        y += 55

    d.text((60,680),"Development Potential",font=body,fill="white")
    d.rounded_rectangle((60,720,940,750),radius=10,fill=(50,50,70))
    d.rounded_rectangle((60,720,60+int(880*development_potential/100),750),
                        radius=10,fill=(170,80,255))

    info = [
        ("Team", current_team or "Free Agent"),
        ("Salary", f"${base_salary:,}"),
        ("Status", "Free Agent" if is_free_agent else "Contracted"),
        ("Driver No.", str(number or "--")),
        ("Potential", f"{development_potential}/100"),
    ]

    y = 820
    for k,v in info:
        d.text((70,y), f"{k}:", font=body, fill=(180,190,210))
        d.text((320,y), str(v), font=body, fill="white")
        y += 55

    d.text((60,1320),"Powered by AmanCeption • F1 Racing Manager",
           font=body,fill=(140,150,180))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
