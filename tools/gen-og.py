#!/usr/bin/env python3
"""產生 LINE／FB 分享預覽圖 og.jpg（1200×630，版型沿用 ../forever-vows 文定喜帖的 og-cover.jpg），
以及 iOS 主畫面圖示 apple-touch-icon.png（180×180，favicon 的香檳金愛心）。

    python3 tools/gen-og.py                  # → og.jpg、apple-touch-icon.png
    python3 tools/gen-og.py /tmp/preview.jpg # 預覽圖輸出到別的路徑

底圖、手寫字型取自 ../forever-vows/public（cover.webp、chenyuluoyan-thin.woff2，子集已含新人名字）；
Fraunces 從 Google Fonts 的 GitHub 下載一次後快取。
置中三行白字，間距 26px、下緣留 56px：— SEATING CHART — ／ 林文瑜 ♥ 周杰鋐 ／ 2026.10.25
名字或日期改了就重跑；LINE 會快取舊圖，換圖後分享時網址加 ?v=N。
"""
import math, sys, tempfile, urllib.request
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
VOWS = ROOT.parent / "forever-vows" / "public"
CACHE = Path(tempfile.gettempdir())
W, H = 1200, 630
WHITE = (255, 255, 255)
CORAL = (223, 140, 114)   # #df8c72，和喜帖的愛心同色
TITLE, LEFT, RIGHT, DATE = "SEATING CHART", "林文瑜", "周杰鋐", "2026.10.25"
FRAUNCES = ("https://raw.githubusercontent.com/google/fonts/main/ofl/fraunces/"
            "Fraunces%5BSOFT%2CWONK%2Copsz%2Cwght%5D.ttf")

def fonts():
    cy = TTFont(VOWS / "chenyuluoyan-thin.woff2"); cy.flavor = None
    cy_path = CACHE / "_cy.ttf"; cy.save(cy_path)
    fr_var = CACHE / "_fr_var.ttf"
    if not fr_var.exists():
        urllib.request.urlretrieve(FRAUNCES, fr_var)
    fr = TTFont(fr_var)
    instancer.instantiateVariableFont(fr, {"SOFT": 0, "WONK": 0, "opsz": 48, "wght": 540}, inplace=True)
    fr_path = CACHE / "_fr.ttf"; fr.save(fr_path)
    return str(cy_path), str(fr_path)

def tracked_width(font, text, tracking):
    return sum(font.getbbox(ch)[2] + tracking for ch in text) - tracking if text else 0

def draw_tracked(draw, cx, y, text, font, tracking):
    x = cx - tracked_width(font, text, tracking) / 2
    for ch in text:
        draw.text((x, y), ch, font=font, fill=WHITE)
        x += font.getbbox(ch)[2] + tracking

def heart(draw, cx, cy, width):
    # 參數式愛心：x ∈ [-16, 16]，縮放到指定寬度
    s, pts, t = width / 32, [], 0.0
    while t < 2 * math.pi:
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * s, cy - y * s))
        t += 0.02
    draw.polygon(pts, fill=CORAL)

def bezier(p0, p1, p2, p3, n=24):
    return [tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t ** 2 * c + t ** 3 * e
                  for a, b, c, e in zip(p0, p1, p2, p3)) for t in (i / n for i in range(1, n + 1))]

def touch_icon(out, size=180, ss=4):
    # 和 index.html 的 favicon 同一條路徑（viewBox 32×32），放在紙色底上，四倍取樣再縮小讓邊緣平滑
    segs = [((14.9, 27.6), (2.5, 19.6), (2.5, 10.9)), ((2.5, 6.9), (5.5, 4), (9.2, 4)),
            ((12, 4), (14.4, 5.6), (16, 8)), ((17.6, 5.6), (20, 4), (22.8, 4)),
            ((26.5, 4), (29.5, 6.9), (29.5, 10.9)), ((29.5, 19.6), (17.1, 27.6), (16, 28.5))]
    pts, cur = [(16, 28.5)], (16, 28.5)
    for a, b, c in segs:
        pts += bezier(cur, a, b, c); cur = c
    big, k = size * ss, size * ss * 0.62 / 27   # 愛心寬 27 單位 → 佔圖示寬 62%
    ox, oy = big / 2 - 16 * k, big / 2 - 16.25 * k
    img = Image.new("RGB", (big, big), (255, 253, 249))   # --paper
    ImageDraw.Draw(img).polygon([(ox + x * k, oy + y * k) for x, y in pts], fill=(168, 135, 90))   # --accent
    img.resize((size, size), Image.LANCZOS).save(out)
    print("wrote", out)

def render(out):
    cy_ttf, fr_ttf = fonts()
    cover = Image.open(VOWS / "cover.webp").convert("RGB")
    img = cover.crop((0, 290, cover.width, 720)).resize((W, H), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    f_title, f_name, f_date = ImageFont.truetype(fr_ttf, 30), ImageFont.truetype(cy_ttf, 66), ImageFont.truetype(fr_ttf, 34)

    th, nh, dh = f_title.getbbox(TITLE)[3], f_name.getbbox("林周")[3], f_date.getbbox(DATE)[3]
    gap, bottom, cx = 26, 56, W / 2
    date_y = H - bottom - dh
    name_y = date_y - gap - nh
    title_y = name_y - gap - th

    # 第一行：SEATING CHART，左右各一條細線
    tw = tracked_width(f_title, TITLE, 6)
    draw_tracked(d, cx, title_y, TITLE, f_title, 6)
    ry = title_y + th / 2
    for sign in (-1, 1):
        x0 = cx + sign * (tw / 2 + 18)
        d.line([(x0, ry), (x0 + sign * 34, ry)], fill=WHITE, width=2)

    # 第二行：林文瑜 ♥ 周杰鋐
    heart_w, seg = nh * 0.60, nh * 0.16
    lw, rw = tracked_width(f_name, LEFT, 0), tracked_width(f_name, RIGHT, 0)
    x = cx - (lw + seg + heart_w + seg + rw) / 2
    draw_tracked(d, x + lw / 2, name_y, LEFT, f_name, 0)
    x += lw + seg
    heart(d, x + heart_w / 2, name_y + nh * 0.52, heart_w)
    x += heart_w + seg
    draw_tracked(d, x + rw / 2, name_y, RIGHT, f_name, 0)

    # 第三行：日期
    draw_tracked(d, cx, date_y, DATE, f_date, 4)

    img.save(out, "JPEG", quality=88)
    print("wrote", out)

if __name__ == "__main__":
    render(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "og.jpg"))
    touch_icon(str(ROOT / "apple-touch-icon.png"))
