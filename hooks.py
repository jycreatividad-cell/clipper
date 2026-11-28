"""
Estilos de hook (texto grande arriba del clip) dibujados con Pillow.

Escribe *entre asteriscos* las palabras que quieres resaltar con el color de acento:
    "SE ARMÓ EL *LÍO* EN LA CASA 😱"
Los emojis salen a color (Noto Color Emoji).
"""

import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = Path(__file__).resolve().parent / "fonts"

EMOJI_RE = re.compile(
    "(?:[\U0001F1E6-\U0001F1FF]{2}"                       # banderas
    "|[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿]"
    "[️\U0001F3FB-\U0001F3FF]*"
    "(?:‍[\U0001F000-\U0001FAFF☀-➿][️\U0001F3FB-\U0001F3FF]*)*)")

# ---------------------------------------------------------------- catálogo de estilos
#   font: archivo · upper: mayúsculas · size: % del ancho · fill/accent: colores del texto
#   stroke: (grosor relativo, color) · box: color de caja por línea · band: barra completa
#   glow: color de brillo · shadow: sombra · gradient: degradado vertical · rotate: grados
STYLES = {
    "tiktok": dict(name="TikTok clásico", font="Poppins-ExtraBold.ttf", upper=False, size=0.068,
                   fill="#111111", accent="#E8193C", box="#FFFFFF", radius=0.35),
    "viral": dict(name="Viral borde", font="Anton-Regular.ttf", upper=True, size=0.088,
                  fill="#FFFFFF", accent="#FFE600", stroke=(0.11, "#000000"), shadow=True),
    "amarillo": dict(name="Amarillo bomba", font="Anton-Regular.ttf", upper=True, size=0.09,
                     fill="#FFE600", accent="#FFFFFF", stroke=(0.12, "#000000"), shadow=True),
    "noticia": dict(name="Última hora", font="Anton-Regular.ttf", upper=True, size=0.08,
                    fill="#FFFFFF", accent="#FFE600", box="#E3122B", radius=0.12,
                    tag=("EN VIVO", "#FFFFFF", "#111111")),
    "alternado": dict(name="Dos tonos", font="Poppins-Black.ttf", upper=True, size=0.064,
                      fill="#FFFFFF", accent="#FFE600", box=["#111111", "#FFE600"],
                      box_text=["#FFFFFF", "#111111"], radius=0.18),
    "barra": dict(name="Barra negra", font="Montserrat.ttf", weight=900, upper=True, size=0.064,
                  fill="#FFFFFF", accent="#FFD400", band="#000000C8"),
    "neon": dict(name="Neón", font="BebasNeue-Regular.ttf", upper=True, size=0.105,
                 fill="#FFFFFF", accent="#3DF5FF", glow="#FF2BD6"),
    "fuego": dict(name="Fuego", font="Anton-Regular.ttf", upper=True, size=0.09,
                  gradient=("#FFF200", "#FF2D00"), accent="#FFFFFF",
                  stroke=(0.1, "#2A0000"), shadow=True),
    "comic": dict(name="Cómic", font="Bangers-Regular.ttf", upper=True, size=0.095,
                  fill="#FFE600", accent="#FF3B3B", stroke=(0.12, "#000000"),
                  shadow=True, rotate=-4),
    "limpio": dict(name="Limpio", font="Montserrat.ttf", weight=800, upper=False, size=0.07,
                   fill="#FFFFFF", accent="#FFD400", shadow=True, soft=True),
}

DEFAULT_STYLE = "viral"


def style_list():
    return [{"id": k, "name": v["name"]} for k, v in STYLES.items()]


@lru_cache(maxsize=64)
def _font(file, size, weight=None):
    f = ImageFont.truetype(str(FONTS / file), size)
    if weight:
        try:
            f.set_variation_by_axes([weight])
        except Exception:  # noqa: BLE001
            pass
    return f


@lru_cache(maxsize=256)
def _emoji(cluster, size):
    try:
        f = ImageFont.truetype(str(FONTS / "NotoColorEmoji.ttf"), 109)
    except OSError:
        return None
    im = Image.new("RGBA", (180, 140), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 0), cluster, font=f, embedded_color=True)
    bb = im.getbbox()
    if not bb:
        return None
    im = im.crop(bb)
    h = int(size * 0.92)
    return im.resize((max(1, int(im.width * h / im.height)), h), Image.LANCZOS)


def _tokens(text, upper):
    """-> lista de líneas; cada línea = lista de palabras (texto, acento)."""
    out = []
    accent = False
    for raw_line in text.strip().splitlines():
        words = []
        for w in raw_line.split():
            parts = w.split("*")
            buf = ""
            word_accent = accent
            for i, p in enumerate(parts):
                if i > 0:
                    accent = not accent
                    if not buf:
                        word_accent = accent
                buf += p
            if buf:
                words.append((buf.upper() if upper else buf, word_accent))
        out.append(words)
    return out


def _pieces(word):
    """separa una palabra en trozos de texto y de emoji."""
    res, last = [], 0
    for m in EMOJI_RE.finditer(word):
        if m.start() > last:
            res.append(("t", word[last:m.start()]))
        res.append(("e", m.group(0)))
        last = m.end()
    if last < len(word):
        res.append(("t", word[last:]))
    return res


def _word_w(word, font, size):
    w = 0
    for kind, s in _pieces(word):
        if kind == "e":
            em = _emoji(s, size)
            w += em.width if em else 0
        else:
            w += font.getlength(s)
    return w


def _wrap(lines, font, size, max_w):
    space = font.getlength(" ")
    wrapped = []
    for words in lines:
        cur, cur_w = [], 0
        for word, acc in words:
            ww = _word_w(word, font, size)
            only_emoji = not EMOJI_RE.sub("", word).strip()
            if cur and cur_w + space + ww > max_w and not only_emoji:
                wrapped.append(cur)
                cur, cur_w = [], 0
            cur.append((word, acc, ww))
            cur_w += (space if len(cur) > 1 else 0) + ww
        if cur:
            wrapped.append(cur)
    return wrapped[:5]


def render_hook(text, style_id=DEFAULT_STYLE, width=1080, scale=1.0, height=None, **tpl):
    """Devuelve una imagen RGBA de `width` px de ancho con el hook dibujado.
    Los ids "t:<categoría>" usan las plantillas PRO de templates.py (acepta accent, badge, icon, panel)."""
    if style_id and style_id.startswith("t:"):
        import templates
        return templates.render_template(text, style_id[2:], width, height or 1920, scale=scale, **tpl)
    if style_id and style_id.startswith("x:"):
        import textstyles
        return textstyles.render_form(text, style_id[2:], width, height or 1920, scale=scale, **tpl)
    st = STYLES.get(style_id, STYLES[DEFAULT_STYLE])
    size = max(18, int(width * st["size"] * scale))
    font = _font(st["font"], size, st.get("weight"))
    lines = _wrap(_tokens(text, st["upper"]), font, size, width * 0.84)
    if not lines:
        return None

    asc, desc = font.getmetrics()
    line_h = int((asc + desc) * (1.02 if st.get("box") else 0.98))
    gap = int(size * (0.30 if st.get("box") else 0.06))
    pad_top = int(size * 0.9) + (int(size * 0.9) if st.get("tag") else 0)
    H = pad_top * 2 + len(lines) * line_h + (len(lines) - 1) * gap
    space = font.getlength(" ")
    sw = int(size * st["stroke"][0]) if st.get("stroke") else 0

    # posiciones
    layout = []
    y = pad_top
    for ln in lines:
        lw = sum(w for _, _, w in ln) + space * (len(ln) - 1)
        layout.append((ln, (width - lw) / 2, y, lw))
        y += line_h + gap

    base = Image.new("RGBA", (width, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)

    # barra completa
    if st.get("band"):
        top = layout[0][2] - int(size * 0.45)
        bot = layout[-1][2] + line_h + int(size * 0.35)
        d.rectangle((0, top, width, bot), fill=st["band"])

    # cajas por línea
    if st.get("box"):
        boxes = st["box"] if isinstance(st["box"], list) else [st["box"]]
        padx, pady = int(size * 0.32), int(size * 0.14)
        r = int(size * st.get("radius", 0.2))
        for i, (ln, x, y, lw) in enumerate(layout):
            d.rounded_rectangle((x - padx, y - pady, x + lw + padx, y + line_h + pady - int(size * 0.05)),
                                radius=r, fill=boxes[i % len(boxes)])

    # etiqueta "EN VIVO"
    if st.get("tag"):
        label, fg, bg = st["tag"]
        tf = _font(st["font"], int(size * 0.5))
        dot = int(size * 0.3)
        tw = dot * 1.6 + tf.getlength(label)
        tx, ty = (width - tw) / 2, layout[0][2] - int(size * 1.05)
        d.rounded_rectangle((tx - size * 0.25, ty - size * 0.08, tx + tw + size * 0.25, ty + size * 0.62),
                            radius=int(size * 0.12), fill=bg)
        cy = ty + size * 0.27
        d.ellipse((tx, cy - dot / 2, tx + dot, cy + dot / 2), fill="#FF2B2B")
        d.text((tx + dot * 1.6, ty), label, font=tf, fill=fg)

    # capa de texto (mascara para degradado/brillo/sombra)
    txt = Image.new("RGBA", (width, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(txt)
    emojis = []
    box_text = st.get("box_text")
    for i, (ln, x, y, lw) in enumerate(layout):
        for word, acc, ww in ln:
            color = st.get("accent") if acc else (box_text[i % len(box_text)] if box_text else st.get("fill", "#FFFFFF"))
            if acc and box_text:
                color = "#E8193C" if box_text[i % len(box_text)] != "#FFFFFF" else st["accent"]
            cx = x
            for kind, s in _pieces(word):
                if kind == "e":
                    em = _emoji(s, size)
                    if em:
                        emojis.append((em, int(cx), int(y + (asc - em.height) * 0.75)))
                        cx += em.width
                else:
                    fill = color if not (st.get("gradient") and not acc) else "#FFFFFF"
                    td.text((cx, y), s, font=font, fill=fill,
                            stroke_width=sw, stroke_fill=st["stroke"][1] if sw else None)
                    if st.get("gradient") and not acc:
                        _gradient_word(txt, font, s, cx, y, st["gradient"])
                    cx += font.getlength(s)
            x += ww + space

    # sombra y brillo
    if st.get("shadow"):
        alpha = txt.split()[3]
        sh = Image.new("RGBA", (width, H), (0, 0, 0, 0))
        off = int(size * (0.04 if st.get("soft") else 0.07))
        blur = size * (0.12 if st.get("soft") else 0.05)
        sh.paste((0, 0, 0, 200 if st.get("soft") else 230), (off, off), alpha)
        base = Image.alpha_composite(base, sh.filter(ImageFilter.GaussianBlur(blur)))
    if st.get("glow"):
        alpha = txt.split()[3]
        g = Image.new("RGBA", (width, H), st["glow"])
        g.putalpha(alpha)
        for rad in (size * 0.35, size * 0.15):
            base = Image.alpha_composite(base, g.filter(ImageFilter.GaussianBlur(rad)))
    base = Image.alpha_composite(base, txt)
    for em, ex, ey in emojis:
        base.alpha_composite(em, (max(0, ex), max(0, ey)))

    if st.get("rotate"):
        base = base.rotate(st["rotate"], resample=Image.BICUBIC, expand=False)
    bb = base.getbbox()
    if bb:  # recortar sobrante vertical, mantener ancho completo
        base = base.crop((0, max(0, bb[1] - 6), width, min(H, bb[3] + 6)))
    return base


def _gradient_word(img, font, s, x, y, colors):
    """Rellena una palabra con degradado vertical (dibuja encima del texto blanco)."""
    asc, desc = font.getmetrics()
    h = asc + desc
    top, bot = Image.new("RGBA", (1, 1), colors[0]), Image.new("RGBA", (1, 1), colors[1])
    grad = Image.new("RGBA", (1, h))
    c1, c2 = top.getpixel((0, 0)), bot.getpixel((0, 0))
    for i in range(h):
        t = i / max(1, h - 1)
        grad.putpixel((0, i), tuple(int(c1[k] + (c2[k] - c1[k]) * t) for k in range(4)))
    w = int(font.getlength(s)) + 2
    grad = grad.resize((w, h))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((0, 0), s, font=font, fill=255)
    img.paste(grad, (int(x), int(y)), mask)


def render_ctx(text, width=1080, scale=1.0):
    """Etiqueta pequeña de contexto (ej. "● EN VIVO · LA CASA DE ALOFOKE 3"): píldora oscura semitransparente."""
    text = (text or "").strip()
    if not text:
        return None
    live = text.startswith("●")
    if live:
        text = text.lstrip("●").strip()
    size = max(14, int(width * 0.026 * scale))
    font = _font("Poppins-ExtraBold.ttf", size)
    tw = font.getlength(text)
    dot = int(size * 0.55) if live else 0
    padx, pady = int(size * 0.75), int(size * 0.45)
    w = int(tw + padx * 2 + (dot + size * 0.45 if live else 0))
    asc, desc = font.getmetrics()
    h = asc + desc + pady * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(0, 0, 0, 140))
    x = padx
    if live:
        cy = h / 2
        d.ellipse((x, cy - dot / 2, x + dot, cy + dot / 2), fill=(255, 43, 43, 255))
        x += dot + size * 0.45
    d.text((x, pady), text, font=font, fill=(255, 255, 255, 235))
    return im


def render_endcard(W, H, handle="@alofokeclips03", line1="SÍGUEME PARA MÁS", line2="👉 Parte 2 en mi perfil"):
    """Tarjeta final de marca (pantalla completa)."""
    img = Image.new("RGB", (W, H))
    top, bot = (232, 25, 79), (109, 40, 217)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    img = img.convert("RGBA")
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((-W * .3, -H * .2, W * .9, H * .45), fill=(255, 255, 255, 45))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(W * .08)))
    d = ImageDraw.Draw(img)
    base = min(W, H)
    f1 = _font("Anton-Regular.ttf", int(base * 0.12))
    words, lines, cur = (line1 or "").upper().split(), [], ""
    for w in words:  # partir el título en líneas que quepan
        test = (cur + " " + w).strip()
        if f1.getlength(test) > W * 0.86 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    asc, desc = f1.getmetrics()
    lh = int((asc + desc) * 0.98)
    y = H * 0.5 - (len(lines) * lh) / 2 - base * 0.12
    for ln in lines:
        d.text((W / 2 + 4, y + 6), ln, font=f1, fill=(0, 0, 0, 90), anchor="ma")
        d.text((W / 2, y), ln, font=f1, fill="#FFFFFF", anchor="ma")
        y += lh
    # @usuario en píldora blanca
    f2 = _font("Poppins-Black.ttf", int(base * 0.055))
    hw = f2.getlength(handle)
    py = y + base * 0.05
    ph = int(base * 0.1)
    d.rounded_rectangle((W / 2 - hw / 2 - base * .05, py, W / 2 + hw / 2 + base * .05, py + ph), radius=ph // 2, fill="#FFFFFF")
    d.text((W / 2, py + ph / 2), handle, font=f2, fill="#E8194F", anchor="mm")
    # segunda línea (con emoji)
    if line2:
        f3 = _font("Poppins-ExtraBold.ttf", int(base * 0.045))
        y3 = py + ph + base * 0.06
        pieces = _pieces(line2)
        size = int(base * 0.045)
        total = sum((_emoji(t, size).width if k == "e" and _emoji(t, size) else f3.getlength(t)) for k, t in pieces)
        x = W / 2 - total / 2
        for k, t in pieces:
            if k == "e":
                em = _emoji(t, size)
                if em:
                    img.alpha_composite(em, (int(x), int(y3)))
                    x += em.width
            else:
                d.text((x, y3), t, font=f3, fill="#FFFFFF")
                x += f3.getlength(t)
    return img.convert("RGB")
