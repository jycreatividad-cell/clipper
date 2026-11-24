"""
Plantillas PRO de hooks: 15 categorías con identidad visual propia.

Cada plantilla es un panel que se pone encima del video y tiene partes editables:
    text    -> el hook (pon *entre asteriscos* lo que va resaltado)
    accent  -> color de resaltado (hex), por defecto el de la categoría
    badge   -> texto del encabezado ("" lo oculta), por defecto el nombre de la categoría
    icon    -> emoji/icono principal ("" lo oculta)
    panel   -> True = fondo oscuro detrás, False = solo texto
    scale   -> tamaño
"""

import math
import random

from PIL import Image, ImageDraw, ImageFilter

from hooks import _emoji, _font, _pieces, _tokens, _word_w

FONT = "Anton-Regular.ttf"

# ---------------------------------------------------------------- categorías
# color: color de la categoría (encabezado y borde) · badge_text: color de letra del encabezado
# accent / accent_mode: color y forma del resaltado (color | box | marker)
# icon / icon_pos: emoji principal y dónde va (top | tl | tr | br | r)
# icon2 / icon2_pos: segundo emoji · deco: elementos gráficos · bg: estilo del panel · rot: inclinación
CATS = {
    "polemica": dict(name="Polémica", color="#6D3BFF", accent="#FFE600", accent_mode="color",
                     icon="😱", icon_pos="br", deco=["torn"], rot=-5,
                     sample="¡LO QUE DIJO DEJÓ A TODOS *SIN PALABRAS!*"),
    "curiosidad": dict(name="Curiosidad", color="#FFD60A", badge_text="#111111", accent="#FFE600",
                       accent_mode="color", icon="", deco=["arrow"], arrow="#FF2D2D", rot=-4,
                       sample="ESPERA... PORQUE LO *MEJOR* VIENE AHORA"),
    "noticias": dict(name="Noticias RD", color="#2563EB", accent="#FFE600", accent_mode="color",
                     icon="🚨", icon_pos="top", icon2="🇩🇴", icon2_pos="bottom", rot=-4,
                     glow="#2563EB", sample="¡ATENCIÓN *REPÚBLICA DOMINICANA!*"),
    "debate": dict(name="Debate", color="#E11D48", accent="#FFE600", accent_mode="color",
                   icon="💬", icon_pos="tl", deco=["underline"], line="#FFFFFF", rot=-5,
                   sample="¿TIENE *RAZÓN* O SE PASÓ DE LA RAYA?"),
    "viral": dict(name="Viral", color="#7C3AED", accent="#E3122B", accent_mode="box",
                  icon="🔥", icon_pos="br", rot=-4, glow="#E3122B",
                  sample="ESTE MOMENTO SE ESTÁ HACIENDO *VIRAL*"),
    "actualidad": dict(name="Actualidad RD", color="#1D4ED8", accent="#FFE600", accent_mode="color",
                       icon="🇩🇴", icon_pos="tl", icon_scale=1.5, rot=-4,
                       sample="ESTO ESTÁ PASANDO AHORA MISMO EN *RD*"),
    "humor": dict(name="Humor / Sarcasmo", color="#FFD60A", badge_text="#111111", accent="#FFE600",
                  accent_mode="color", icon="😂", icon_pos="br", rot=-4,
                  sample="EN REPÚBLICA DOMINICANA NO HAY UN DÍA *ABURRIDO*"),
    "impacto": dict(name="Impacto", color="#E3122B", accent="#FF2D2D", accent_mode="color",
                    icon="", deco=["sparks", "underline"], line="#E3122B", rot=-4,
                    sample="NADIE ESPERABA ESTA RESPUESTA"),
    "verdad": dict(name="Verdad incómoda", color="#FFD60A", badge_text="#111111", accent="#FFE600",
                   accent_mode="color", icon="", deco=["underline"], line="#FFD60A", rot=-5,
                   sample="VOY A DECIR ALGO QUE MUCHOS *NO SE ATREVEN*"),
    "motivacion": dict(name="Motivacional", color="#16A34A", accent="#FFE600", accent_mode="box",
                       icon="🙌", icon_pos="top", bg="sunset", rot=-3,
                       sample="ESCUCHA ESTO SI ESTÁS PASANDO POR UN MOMENTO *DIFÍCIL*"),
    "revelacion": dict(name="Revelación", color="#6D28D9", accent="#FFE600", accent_mode="color",
                       icon="📂", icon_pos="tl", deco=["underline"], line="#E3122B", rot=-3,
                       sample="HAY UN DETALLE QUE CASI *NADIE NOTÓ*"),
    "alerta": dict(name="Alerta", color="#E3122B", accent="#FFFFFF", accent_mode="color",
                   icon="🔔", icon_pos="top", deco=["banner", "underline"], line="#E3122B",
                   rot=-4, glow="#E3122B", sample="ÚLTIMA HORA: MIRA LO QUE ACABA DE *SUCEDER*"),
    "reflexion": dict(name="Reflexión", color="#2563EB", accent="#FFE14D", accent_mode="marker",
                      icon="", bg="paper", rot=-3,
                      sample="A VECES NECESITAS ESCUCHAR *VERDADES INCÓMODAS*"),
    "tendencia": dict(name="Tendencia", color="#06B6D4", accent="#22D3EE", accent_mode="color",
                      icon="📈", icon_pos="top", deco=["underline"], line="#22D3EE", rot=-3,
                      sample="LA GENTE ESTÁ HABLANDO DE ESTO Y *CON RAZÓN*"),
    "local": dict(name="Local / Cotidiano", color="#7C3AED", accent="#FFE600", accent_mode="color",
                  icon="🌴", icon_pos="tl", icon2="🇩🇴", icon2_pos="br", bg="sunset", rot=-4,
                  sample="ESTO SOLAMENTE PASA AQUÍ EN *RD*"),
}


def template_list():
    return [{"id": "t:" + k, "name": v["name"], "sample": v["sample"], "badge": v["name"].upper(),
             "accent": v["accent"], "icon": v.get("icon", "")} for k, v in CATS.items()]


def _rgba(hex_color, alpha=255):
    h = hex_color.lstrip("#")
    if len(h) == 8:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4, 6))
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def _is_light(hex_color):
    r, g, b, _ = _rgba(hex_color)
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150


# ---------------------------------------------------------------- piezas gráficas

def _brush(draw, x0, x1, y, thick, color, seed=1, curve=0.0):
    """trazo de pincel afinado en las puntas."""
    rnd = random.Random(seed)
    n = 28
    top, bot = [], []
    for i in range(n + 1):
        t = i / n
        x = x0 + (x1 - x0) * t
        yc = y - curve * math.sin(t * math.pi) - thick * 0.25 * t
        w = thick * (0.25 + 0.75 * math.sin(min(1, t * 1.15) * math.pi) ** 0.6)
        j = rnd.uniform(-0.08, 0.08) * thick
        top.append((x, yc - w / 2 + j))
        bot.append((x, yc + w / 2 + j))
    draw.polygon(top + bot[::-1], fill=color)


def _arrow(draw, x0, x1, y, thick, color):
    _brush(draw, x0, x1 - thick * 1.2, y, thick, color, seed=3, curve=-thick * 0.9)
    hx, hy = x1, y - thick * 0.55
    draw.polygon([(hx, hy), (hx - thick * 2.2, hy - thick * 1.5), (hx - thick * 1.6, hy + thick * 1.4)],
                 fill=color)


def _torn_band(draw, x0, y0, x1, y1, color, edge, seed=7):
    rnd = random.Random(seed)

    def jag(y, amp):
        pts, x = [], x0
        while x < x1:
            pts.append((x, y + rnd.uniform(-amp, amp)))
            x += rnd.uniform(14, 34)
        pts.append((x1, y + rnd.uniform(-amp, amp)))
        return pts

    amp = (y1 - y0) * 0.05
    pad = (y1 - y0) * 0.035
    top_e, bot_e = jag(y0 - pad, amp), jag(y1 + pad, amp)
    draw.polygon(top_e + bot_e[::-1], fill=edge)           # borde de papel blanco
    top, bot = jag(y0, amp), jag(y1, amp)
    draw.polygon(top + bot[::-1], fill=color)


def _sparks(draw, x, y, s, color):
    for ang, ln in ((-150, 1.0), (-115, 0.8), (-180, 0.7)):
        a = math.radians(ang)
        x0, y0 = x + math.cos(a) * s * 0.35, y + math.sin(a) * s * 0.35
        x1, y1 = x + math.cos(a) * s * (0.35 + 0.45 * ln), y + math.sin(a) * s * (0.35 + 0.45 * ln)
        draw.line((x0, y0, x1, y1), fill=color, width=max(3, int(s * 0.09)))


def _vgrad(w, h, stops):
    """degradado vertical: stops = [(pos, (r,g,b,a)), ...]"""
    col = Image.new("RGBA", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                k = (t - p0) / max(1e-6, p1 - p0)
                col.putpixel((0, y), tuple(int(c0[i] + (c1[i] - c0[i]) * k) for i in range(4)))
                break
    return col.resize((w, h))


# ---------------------------------------------------------------- render

def render_template(text, cat_id, width=1080, height=1920, accent=None, badge=None, icon=None,
                    panel=True, scale=1.0):
    c = CATS.get(cat_id, CATS["viral"])
    text = (text or "").strip() or c["sample"]
    accent = accent or c["accent"]
    badge = c["name"].upper() if badge is None else badge.strip().upper()
    icon = c.get("icon", "") if icon is None else icon.strip()
    deco = c.get("deco", [])
    bg = c.get("bg")
    dark_text = bg == "paper"

    vertical = height > width
    pw = int(width * 0.92) if vertical else (int(width * 0.42) if width > height else int(width * 0.72))
    fs = int(pw * 0.128 * scale)
    inner = pw * 0.80

    # ---- líneas (máx. 4: se achica la letra si hace falta)
    raw = _tokens(text, True)
    banner_words = 0
    if "banner" in deco and raw and any(w.endswith(":") for w, _ in raw[0]):
        for i, (w, _) in enumerate(raw[0]):
            if w.endswith(":"):
                banner_words = i + 1
                break
        raw = [raw[0][:banner_words]] + [raw[0][banner_words:]] + raw[1:]
        raw = [r for r in raw if r]
    while True:
        font = _font(FONT, fs)
        space = font.getlength(" ")
        lines = []
        for li, words in enumerate(raw):
            cur, cur_w = [], 0
            for w, acc in words:
                ww = _word_w(w, font, fs)
                only_emoji = all(k == "e" for k, _ in _pieces(w))
                if cur and cur_w + space + ww > inner and not only_emoji:
                    lines.append(cur)
                    cur, cur_w = [], 0
                cur.append((w, acc, ww))
                cur_w += (space if len(cur) > 1 else 0) + ww
            if cur:
                lines.append(cur)
        if len(lines) <= 4 or fs < pw * 0.06:
            break
        fs = int(fs * 0.92)
    lines = lines[:5]

    cap = -font.getbbox("H", anchor="ls")[1]
    adv = int(cap * 1.34)
    isz = int(fs * 1.45 * c.get("icon_scale", 1.0))

    # ---- alturas
    pad = int(fs * 0.45)
    badge_h = int(fs * 0.7) if badge else 0
    top_icon_h = isz if (icon and c.get("icon_pos") == "top") else 0
    bottom_h = int(fs * 1.1) if c.get("icon2_pos") == "bottom" else 0
    deco_h = int(fs * 0.55) if ({"underline", "arrow"} & set(deco)) else int(fs * 0.15)
    text_h = adv * len(lines)
    ph = pad + badge_h + (int(fs * 0.3) if badge else 0) + top_icon_h + int(fs * 0.25) + text_h + deco_h + bottom_h + pad
    if c.get("icon_pos") == "tl" and icon:
        ph += int(isz * 0.95)
    br_extra = int(isz * 0.4) if ((icon and c.get("icon_pos") == "br") or c.get("icon2_pos") == "br") else 0
    ph += br_extra

    CH = ph + int(fs * 2)
    canvas = Image.new("RGBA", (width, CH), (0, 0, 0, 0))
    px0 = (width - pw) // 2
    px1 = px0 + pw
    py0 = int(fs * 0.6)
    py1 = py0 + ph
    radius = int(fs * 0.38)

    # ---- panel
    if panel:
        glow_col = c.get("glow", c["color"])
        g = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(g).rounded_rectangle((px0, py0, px1, py1), radius, outline=_rgba(glow_col, 230),
                                            width=max(4, int(fs * 0.08)))
        canvas = Image.alpha_composite(canvas, g.filter(ImageFilter.GaussianBlur(fs * 0.22)))
        mask = Image.new("L", canvas.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((px0, py0, px1, py1), radius, fill=255)
        if bg == "paper":
            fill = Image.new("RGBA", canvas.size, (239, 232, 216, 250))
            rnd = random.Random(5)
            fd = ImageDraw.Draw(fill)
            for _ in range(int(pw * ph / 900)):
                x, y = rnd.uniform(px0, px1), rnd.uniform(py0, py1)
                v = rnd.randint(200, 235)
                fd.point((x, y), fill=(v, v - 6, v - 18, 255))
            fill = fill.filter(ImageFilter.GaussianBlur(0.6))
        elif bg == "sunset":
            fill = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            fill.paste(_vgrad(pw, ph, [(0, (249, 115, 22, 245)), (0.32, (124, 45, 18, 240)),
                                       (0.62, (20, 12, 20, 238)), (1, (8, 8, 12, 238))]), (px0, py0))
        else:
            fill = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            fill.paste(_vgrad(pw, ph, [(0, (28, 28, 38, 232)), (1, (6, 6, 10, 236))]), (px0, py0))
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        layer.paste(fill, (0, 0), mask)
        canvas = Image.alpha_composite(canvas, layer)
        ImageDraw.Draw(canvas).rounded_rectangle((px0, py0, px1, py1), radius,
                                                 outline=_rgba(glow_col, 200), width=max(2, int(fs * 0.035)))

    d = ImageDraw.Draw(canvas)
    y = py0 + pad

    # ---- encabezado (badge)
    if badge:
        bf = _font(FONT, int(fs * 0.48))
        bw = bf.getlength(badge)
        bx0 = (width - bw) / 2 - fs * 0.32
        bx1 = (width + bw) / 2 + fs * 0.32
        d.rounded_rectangle((bx0, y, bx1, y + badge_h), int(fs * 0.12), fill=c["color"])
        d.text((width / 2, y + badge_h / 2), badge, font=bf, anchor="mm",
               fill=c.get("badge_text", "#FFFFFF"))
        y += badge_h + int(fs * 0.3)

    icons = []  # (emoji, x_centro, y_centro, tamaño)
    if top_icon_h:
        icons.append((icon, width / 2, y + isz / 2, isz))
        y += top_icon_h
    if c.get("icon_pos") == "tl" and icon:
        y += int(isz * 0.95)
    y += int(fs * 0.25)
    text_top = y

    # ---- capa de texto (se inclina)
    T = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    td = ImageDraw.Draw(T)
    fill_col = "#141414" if dark_text else "#FFFFFF"
    stroke = 0 if dark_text else max(3, int(fs * 0.07))
    acc_mode = c["accent_mode"]
    box_text = "#111111" if _is_light(accent) else "#FFFFFF"

    layout = []
    for li, ln in enumerate(lines):
        lw = sum(w for _, _, w in ln) + space * (len(ln) - 1)
        x = (width - lw) / 2
        base = text_top + adv * li + cap
        layout.append((ln, x, base, lw))

    # decoraciones detrás del texto
    if "torn" in deco:
        _torn_band(td, px0 - fs * 0.15, text_top - fs * 0.35, px1 + fs * 0.15,
                   text_top + text_h + fs * 0.05, "#C8102E", "#F4F1EA")
    if banner_words and layout:
        ln, x, base, lw = layout[0]
        td.rectangle((x - fs * 0.25, base - cap - fs * 0.16, x + lw + fs * 0.25, base + fs * 0.16), fill="#E3122B")

    word_boxes = []
    for li, (ln, x, base, lw) in enumerate(layout):
        cx = x
        span = None
        for wi, (w, acc, ww) in enumerate(ln):
            if acc and acc_mode in ("box", "marker"):
                if span is None:
                    span = [cx, cx + ww]
                else:
                    span[1] = cx + ww
            elif span:
                word_boxes.append((span, base))
                span = None
            cx += ww + space
        if span:
            word_boxes.append((span, base))
    for (sx0, sx1), base in word_boxes:
        padx = fs * 0.16
        top_y, bot_y = base - cap - fs * 0.14, base + fs * 0.14
        if acc_mode == "marker":
            _brush(td, sx0 - padx, sx1 + padx, (top_y + bot_y) / 2, (bot_y - top_y) * 1.05,
                   accent, seed=int(sx0))
        else:
            sk = fs * 0.12
            td.polygon([(sx0 - padx + sk, top_y), (sx1 + padx + sk, top_y),
                        (sx1 + padx - sk, bot_y), (sx0 - padx - sk, bot_y)], fill=accent)

    # texto
    emojis = []
    for li, (ln, x, base, lw) in enumerate(layout):
        cx = x
        for w, acc, ww in ln:
            if acc and acc_mode in ("box", "marker"):
                color = box_text if acc_mode == "box" else "#141414"
                sw = 0
            else:
                color = accent if acc else fill_col
                sw = stroke
            for kind, s in _pieces(w):
                if kind == "e":
                    em = _emoji(s, fs)
                    if em:
                        emojis.append((em, int(cx), int(base - cap - (em.height - cap) / 2)))
                        cx += em.width
                else:
                    td.text((cx, base), s, font=font, anchor="ls", fill=color,
                            stroke_width=sw, stroke_fill="#000000")
                    cx += font.getlength(s)
            cx += space

    text_bottom = text_top + text_h
    last_ln, last_x, last_base, last_w = layout[-1]
    if "underline" in deco:
        _brush(td, last_x - fs * 0.1, last_x + last_w + fs * 0.1, last_base + fs * 0.32,
               fs * 0.2, c.get("line", accent), seed=11, curve=fs * 0.06)
    if "arrow" in deco:
        _arrow(td, width / 2 - pw * 0.3, width / 2 + pw * 0.3, last_base + fs * 0.42, fs * 0.15,
               c.get("arrow", "#FF2D2D"))
    if "sparks" in deco:
        _sparks(td, layout[0][1] - fs * 0.05, text_top + fs * 0.05, fs * 1.2, "#FFD60A")

    # sombra del texto
    if not dark_text:
        sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        off = int(fs * 0.06)
        sh.paste((0, 0, 0, 200), (off, off), T.split()[3])
        canvas = Image.alpha_composite(canvas, sh.filter(ImageFilter.GaussianBlur(fs * 0.06)))
    for em, ex, ey in emojis:
        T.alpha_composite(em, (max(0, ex), max(0, ey)))
    center = (width / 2, (text_top + text_bottom) / 2)
    T = T.rotate(-c.get("rot", 0), resample=Image.BICUBIC, center=center)
    canvas = Image.alpha_composite(canvas, T)

    # ---- iconos alrededor del texto
    pos = c.get("icon_pos")
    if icon and pos == "tl":
        icons.append((icon, max(px0 + isz * 0.6, layout[0][1] + isz * 0.2), text_top - isz * 0.58, isz))
    elif icon and pos == "tr":
        icons.append((icon, min(px1 - isz * 0.55, layout[0][1] + layout[0][3]), text_top - isz * 0.25, isz))
    elif icon and pos == "br":
        icons.append((icon, min(px1 - isz * 0.5, last_x + last_w + isz * 0.3), text_bottom + isz * 0.12, isz))
    elif icon and pos == "r":
        mid = layout[len(layout) // 2]
        icons.append((icon, min(px1 - isz * 0.45, mid[1] + mid[3] + isz * 0.5), mid[2] - cap / 2, isz))
    if c.get("icon2"):
        p2 = c.get("icon2_pos")
        s2 = int(fs * 1.0)
        if p2 == "bottom":
            icons.append((c["icon2"], width / 2, py1 - pad - s2 * 0.45, s2 * 1.15))
        elif p2 == "br":
            icons.append((c["icon2"], px1 - s2 * 0.8, text_bottom + s2 * 0.45, s2))
    for em_txt, ex, ey, s in icons:
        for kind, cl in _pieces(em_txt):
            em = _emoji(cl, int(s))
            if em:
                canvas.alpha_composite(em, (int(max(0, ex - em.width / 2)), int(max(0, ey - em.height / 2))))
                break

    bb = canvas.getbbox()
    if bb:
        canvas = canvas.crop((0, max(0, bb[1] - 4), width, min(CH, bb[3] + 4)))
    return canvas
