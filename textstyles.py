"""
Formas de texto para el hook (ids "x:<forma>"): chat, publicación, comentario, encuesta, titular,
sticker, cinta y resaltador. Como las demás, *palabra* = resaltada y los emojis salen a color.

Parámetros extra:
  badge  -> nombre/etiqueta (chat: remitente, publicación: nombre, titular: etiqueta, comentario: @usuario)
  handle -> @usuario de la publicación (por defecto la marca de agua)
Encuesta: "¿Pregunta? | Opción 1 | Opción 2" (sin opciones = SÍ / NO).
"""

import random

from PIL import Image, ImageDraw, ImageFilter

from hooks import _emoji, _font, _pieces, _tokens, _wrap

FORMS = {
    "chat": "💬 Mensaje de chat",
    "tweet": "🐦 Publicación",
    "comentario": "🗨️ Respuesta a comentario",
    "encuesta": "📊 Encuesta",
    "titular": "📰 Titular de noticia",
    "sticker": "🏷️ Sticker",
    "cinta": "🎞️ Cinta adhesiva",
    "resaltador": "🖍️ Resaltador",
}


def form_list():
    return [{"id": "x:" + k, "name": v} for k, v in FORMS.items()]


# ---------------------------------------------------------------- utilidades de texto

def _lines(text, font, size, max_w, upper):
    return _wrap(_tokens(text, upper), font, size, max_w)


def _line_w(ln, font):
    return sum(w for _, _, w in ln) + font.getlength(" ") * (len(ln) - 1)


def _draw_line(img, x, y, ln, font, size, fill, accent, stroke=0, stroke_fill=None):
    """Dibuja una línea (palabras con acento y emojis) con su borde superior en y."""
    d = ImageDraw.Draw(img)
    asc, _ = font.getmetrics()
    space = font.getlength(" ")
    cx = x
    for word, acc, ww in ln:
        color = accent if acc else fill
        for kind, s in _pieces(word):
            if kind == "e":
                em = _emoji(s, size)
                if em:
                    img.alpha_composite(em, (int(cx), int(y + (asc - em.height) * 0.8)))
                    cx += em.width
            else:
                d.text((cx, y), s, font=font, fill=color, stroke_width=stroke, stroke_fill=stroke_fill)
                cx += font.getlength(s)
        cx += space


def _shadow(img, radius, alpha=120, off=(0, 6)):
    a = img.split()[3]
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sh.paste((0, 0, 0, alpha), off, a)
    return Image.alpha_composite(sh.filter(ImageFilter.GaussianBlur(radius)), img)


def _canvas(width, h):
    return Image.new("RGBA", (width, h), (0, 0, 0, 0))


def _crop(img):
    bb = img.getbbox()
    return img.crop((0, max(0, bb[1] - 4), img.width, min(img.height, bb[3] + 4))) if bb else img


# ---------------------------------------------------------------- formas

def _chat(text, W, s, badge, accent, **_):
    size = int(W * 0.06 * s)
    font = _font("Poppins-ExtraBold.ttf", size)
    lines = _lines(text, font, size, W * 0.72, False)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.05)
    pad = int(size * 0.7)
    bw = int(max(_line_w(l, font) for l in lines) + pad * 2)
    bh = lh * len(lines) + pad * 2
    name = badge if badge is not None else "La Casa 🏠"
    nf = _font("Poppins-ExtraBold.ttf", int(size * 0.55))
    top = int(size * 1.0) if name else int(size * 0.3)
    img = _canvas(W, bh + top + size * 2)
    d = ImageDraw.Draw(img)
    x0 = int(W * 0.08)
    if name:
        _draw_line(img, x0 + pad * 0.6, int(size * 0.15), _lines(name, nf, int(size * 0.55), W, False)[0],
                   nf, int(size * 0.55), "#E9E9EE", accent)
    y0 = top
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=int(size * 0.9), fill="#FFFFFF")
    tail = [(x0 + size * 0.2, y0 + bh - size * 0.9), (x0 - size * 0.45, y0 + bh + size * 0.05), (x0 + size * 1.1, y0 + bh - size * 0.25)]
    d.polygon(tail, fill="#FFFFFF")
    for i, ln in enumerate(lines):
        _draw_line(img, x0 + pad, y0 + pad + i * lh, ln, font, size, "#111111", accent if accent != "#FFE600" else "#0A84FF")
    # "leído" como en las apps de mensajes
    tf = _font("Poppins-ExtraBold.ttf", int(size * 0.42))
    d.text((x0 + bw - tf.getlength("Leído"), y0 + bh + size * 0.15), "Leído", font=tf, fill="#D8D8E0")
    return _shadow(_crop(img), size * 0.25)


def _tweet(text, W, s, badge, accent, handle=None, **_):
    size = int(W * 0.052 * s)
    font = _font("Poppins-ExtraBold.ttf", size)
    cw = int(W * 0.88)
    pad = int(size * 0.9)
    lines = _lines(text, font, size, cw - pad * 2, False)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.08)
    av = int(size * 2.1)
    head = av + int(size * 0.6)
    ch = pad + head + lh * len(lines) + int(size * 1.6) + pad
    img = _canvas(W, ch + 20)
    d = ImageDraw.Draw(img)
    x0 = (W - cw) // 2
    d.rounded_rectangle((x0, 0, x0 + cw, ch), radius=int(size * 0.8), fill="#FFFFFF")
    # avatar
    d.ellipse((x0 + pad, pad, x0 + pad + av, pad + av), fill="#E8194F")
    em = _emoji("🏠", int(av * 0.6))
    if em:
        img.alpha_composite(em, (int(x0 + pad + (av - em.width) / 2), int(pad + (av - em.height) / 2)))
    name = badge if badge else "Clips de La Casa"
    nf = _font("Poppins-ExtraBold.ttf", int(size * 0.78))
    hf = _font("Poppins-ExtraBold.ttf", int(size * 0.62))
    nx = x0 + pad + av + int(size * 0.5)
    d.text((nx, pad + int(size * 0.1)), name, font=nf, fill="#0F1419")  # sin insignia de verificado
    d.text((nx, pad + int(size * 1.05)), handle or "@alofokeclips03", font=hf, fill="#536471")
    y = pad + head
    for i, ln in enumerate(lines):
        _draw_line(img, x0 + pad, y + i * lh, ln, font, size, "#0F1419", "#1D9BF0" if accent == "#FFE600" else accent)
    # acciones (solo iconos: sin cifras inventadas)
    fy = y + lh * len(lines) + int(size * 0.5)
    for k, ic in enumerate(("💬", "🔁", "❤️", "📤")):
        ex = x0 + pad + k * (cw - pad * 2) / 4
        e2 = _emoji(ic, int(size * 0.7))
        if e2:
            img.alpha_composite(e2, (int(ex), int(fy)))
    return _shadow(_crop(img), size * 0.3)


def _comentario(text, W, s, badge, accent, **_):
    size = int(W * 0.05 * s)
    font = _font("Poppins-ExtraBold.ttf", size)
    lines = _lines(text, font, size, W * 0.7, False)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.05)
    pad = int(size * 0.65)
    user = badge if badge else "@fan_de_la_casa"
    hf = _font("Poppins-ExtraBold.ttf", int(size * 0.55))
    head_txt = f"Respondiendo al comentario de {user}"
    bw = int(max([_line_w(l, font) for l in lines] + [hf.getlength(head_txt) + size * 1.2]) + pad * 2)
    hh = int(size * 1.0)
    bh = hh + lh * len(lines) + pad * 2
    img = _canvas(W, bh + size)
    d = ImageDraw.Draw(img)
    x0 = (W - bw) // 2
    d.rounded_rectangle((x0, 0, x0 + bw, bh), radius=int(size * 0.5), fill="#FFFFFF")
    d.polygon([(x0 + size * 1.2, bh), (x0 + size * 1.8, bh + size * 0.6), (x0 + size * 2.4, bh)], fill="#FFFFFF")
    d.ellipse((x0 + pad, pad + size * 0.08, x0 + pad + size * 0.55, pad + size * 0.63), fill="#FE2C55")
    d.text((x0 + pad + size * 0.8, pad), head_txt, font=hf, fill="#8A8B91")
    for i, ln in enumerate(lines):
        _draw_line(img, x0 + pad, pad + hh + i * lh, ln, font, size, "#161823", "#FE2C55" if accent == "#FFE600" else accent)
    return _shadow(_crop(img), size * 0.25)


def _encuesta(text, W, s, badge, accent, **_):
    parts = [p.strip() for p in text.split("|")]
    q = parts[0]
    opts = [p for p in parts[1:] if p][:3] or ["SÍ", "NO"]
    size = int(W * 0.055 * s)
    font = _font("Poppins-Black.ttf", size)
    cw = int(W * 0.84)
    pad = int(size * 0.8)
    lines = _lines(q, font, size, cw - pad * 2, True)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.02)
    oh = int(size * 1.9)
    ch = pad + lh * len(lines) + int(size * 0.5) + len(opts) * (oh + int(size * 0.35)) + pad
    img = _canvas(W, ch + 10)
    d = ImageDraw.Draw(img)
    x0 = (W - cw) // 2
    d.rounded_rectangle((x0, 0, x0 + cw, ch), radius=int(size * 0.7), fill="#FFFFFF")
    for i, ln in enumerate(lines):
        lw = _line_w(ln, font)
        _draw_line(img, x0 + (cw - lw) / 2, pad + i * lh, ln, font, size, "#111111", "#E8194F" if accent == "#FFE600" else accent)
    of = _font("Poppins-ExtraBold.ttf", int(size * 0.8))
    colors = ["#E8194F", "#1D9BF0", "#16A34A"]
    y = pad + lh * len(lines) + int(size * 0.5)
    for k, o in enumerate(opts):
        bx0, bx1 = x0 + pad, x0 + cw - pad
        d.rounded_rectangle((bx0, y, bx1, y + oh), radius=oh // 2, fill="#F1F1F4")
        d.rounded_rectangle((bx0, y, bx0 + oh, y + oh), radius=oh // 2, fill=colors[k % 3])
        d.text((bx0 + oh / 2, y + oh / 2), "ABC"[k], font=of, fill="#FFFFFF", anchor="mm")
        ol = _lines(o, of, int(size * 0.8), bx1 - bx0 - oh * 1.5, True)[:1]
        if ol:
            _draw_line(img, bx0 + oh * 1.3, y + (oh - sum(of.getmetrics())) / 2, ol[0], of, int(size * 0.8), "#111111", "#111111")
        y += oh + int(size * 0.35)
    return _shadow(_crop(img), size * 0.3)


def _titular(text, W, s, badge, accent, **_):
    size = int(W * 0.05 * s)
    font = _font("Anton-Regular.ttf", int(size * 1.1))
    label = (badge if badge else "ÚLTIMA HORA").upper()
    lf = _font("Anton-Regular.ttf", int(size * 0.75))
    lines = _lines(text, font, int(size * 1.1), W * 0.84, True)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.0)
    pad = int(size * 0.4)
    bh = lh * len(lines) + pad * 2
    lw = int(lf.getlength(label) + size * 1.1)
    lhh = int(size * 1.15)
    img = _canvas(W, bh + lhh + 10)
    d = ImageDraw.Draw(img)
    x0 = int(W * 0.05)
    d.rectangle((x0, 0, x0 + lw, lhh), fill="#D90429")
    d.ellipse((x0 + size * 0.25, lhh / 2 - size * 0.14, x0 + size * 0.53, lhh / 2 + size * 0.14), fill="#FFFFFF")
    d.text((x0 + size * 0.7, lhh / 2), label, font=lf, fill="#FFFFFF", anchor="lm")
    d.rectangle((x0, lhh, W - x0, lhh + bh), fill="#FFFFFF")
    d.rectangle((x0, lhh + bh - int(size * 0.12), W - x0, lhh + bh), fill="#D90429")
    for i, ln in enumerate(lines):
        _draw_line(img, x0 + pad * 1.5, lhh + pad + i * lh, ln, font, int(size * 1.1), "#111111", "#D90429" if accent == "#FFE600" else accent)
    return _shadow(_crop(img), size * 0.2)


def _sticker(text, W, s, badge, accent, **_):
    size = int(W * 0.085 * s)
    font = _font("Bangers-Regular.ttf", size)
    lines = _lines(text, font, size, W * 0.8, True)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 0.95)
    img = _canvas(W, lh * len(lines) + size)
    stroke = max(4, int(size * 0.16))
    for i, ln in enumerate(lines):
        lw = _line_w(ln, font)
        _draw_line(img, (W - lw) / 2, size * 0.3 + i * lh, ln, font, size, "#111111",
                   "#E8194F" if accent == "#FFE600" else accent, stroke, "#FFFFFF")
    img = img.rotate(4, resample=Image.BICUBIC)
    return _shadow(_crop(img), size * 0.12, 160, (0, int(size * 0.08)))


def _cinta(text, W, s, badge, accent, **_):
    size = int(W * 0.06 * s)
    font = _font("Poppins-Black.ttf", size)
    lines = _lines(text, font, size, W * 0.76, True)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.35)
    img = _canvas(W, lh * len(lines) + size * 2)
    rnd = random.Random(len(text))
    for i, ln in enumerate(lines):
        lw = _line_w(ln, font)
        strip = Image.new("RGBA", (int(lw + size * 1.4), int((asc + desc) * 1.25)), (0, 0, 0, 0))
        sd = ImageDraw.Draw(strip)
        tape = (255, 220, 60, 235) if i % 2 == 0 else (255, 255, 255, 235)
        sd.rectangle((0, 0, strip.width, strip.height), fill=tape)
        for xx in range(0, strip.height, max(3, size // 6)):  # bordes dentados de cinta rasgada
            sd.polygon([(0, xx), (size * 0.12, xx + size * 0.08), (0, xx + size * 0.16)], fill=(0, 0, 0, 0))
            sd.polygon([(strip.width, xx), (strip.width - size * 0.12, xx + size * 0.08), (strip.width, xx + size * 0.16)], fill=(0, 0, 0, 0))
        _draw_line(strip, size * 0.7, (strip.height - asc - desc) / 2, ln, font, size, "#111111",
                   "#E8194F" if accent == "#FFE600" else accent)
        strip = strip.rotate(rnd.uniform(-3.5, 3.5), resample=Image.BICUBIC, expand=True)
        img.alpha_composite(strip, (int((W - strip.width) / 2), int(size * 0.5 + i * lh)))
    return _shadow(_crop(img), size * 0.2, 110)


def _resaltador(text, W, s, badge, accent, **_):
    size = int(W * 0.064 * s)
    font = _font("Poppins-Black.ttf", size)
    lines = _lines(text, font, size, W * 0.8, True)
    asc, desc = font.getmetrics()
    lh = int((asc + desc) * 1.2)
    img = _canvas(W, lh * len(lines) + size)
    rnd = random.Random(len(text) * 7)
    for i, ln in enumerate(lines):
        lw = _line_w(ln, font)
        x = (W - lw) / 2
        y = size * 0.3 + i * lh
        mark = Image.new("RGBA", img.size, (0, 0, 0, 0))
        md = ImageDraw.Draw(mark)
        top, bot = y + (asc + desc) * 0.28, y + (asc + desc) * 1.02
        md.polygon([(x - size * 0.3, top + rnd.uniform(-4, 4)), (x + lw + size * 0.3, top + rnd.uniform(-4, 4)),
                    (x + lw + size * 0.22, bot + rnd.uniform(-4, 4)), (x - size * 0.22, bot + rnd.uniform(-4, 4))],
                   fill=(255, 225, 40, 230))
        img = Image.alpha_composite(img, mark.filter(ImageFilter.GaussianBlur(1.2)))
        _draw_line(img, x, y, ln, font, size, "#111111", "#E8194F" if accent == "#FFE600" else accent,
                   max(2, size // 16), "#FFFFFF")
    return _shadow(_crop(img), size * 0.15, 100)


RENDER = {"chat": _chat, "tweet": _tweet, "comentario": _comentario, "encuesta": _encuesta,
          "titular": _titular, "sticker": _sticker, "cinta": _cinta, "resaltador": _resaltador}


def render_form(text, form, width=1080, height=1920, scale=1.0, badge=None, accent=None, handle=None, **_):
    fn = RENDER.get(form)
    if not fn or not (text or "").strip():
        return None
    s = scale * (1 if height > width else 0.8)
    return fn(text.strip(), width, s, badge, accent or "#FFE600", handle=handle)
