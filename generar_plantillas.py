"""
Genera las plantillas PRO de hooks como imágenes PNG transparentes, listas para
CapCut / Premiere / Canva, y la lámina comparativa.

Uso:
  python generar_plantillas.py                         # las 15 con su texto de ejemplo
  python generar_plantillas.py --cat viral --texto "SE ARMÓ EL *LÍO* 😱" --color "#22D3EE" \
         --encabezado "LA CASA DE ALOFOKE" --icono "🔥" --posicion arriba --con-fondo

Salida en la carpeta plantillas/:
  lamina.png                    las 15 en cuadrícula
  NN-categoria/vertical.png     1080x1920 transparente (se pone encima del video)
  NN-categoria/cuadrado.png     1080x1080 transparente
  NN-categoria/horizontal.png   1920x1080 transparente
  NN-categoria/hook.png         solo el panel, recortado
  NN-categoria/muestra.jpg      ejemplo sobre un fondo
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import templates
from hooks import _font

OUT = Path(__file__).resolve().parent / "plantillas"
FORMATS = {"vertical": (1080, 1920), "cuadrado": (1080, 1080), "horizontal": (1920, 1080)}


def pos_y(pos, H, h):
    if pos == "centro":
        return (H - h) // 2
    if pos == "abajo":
        return int(H * 0.66) - h // 2
    return int(H * 0.04)


def sample_bg(W, H):
    bg = Image.new("RGB", (W, H), "#120d0a")
    d = ImageDraw.Draw(bg)
    for i in range(H):
        t = i / H
        d.line([(0, i), (W, i)], fill=(int(40 + 50 * t), int(26 + 22 * t), int(30 + 8 * t)))
    if H > W:
        vh = W * 9 // 16
        d.rectangle((0, (H - vh) // 2, W, (H + vh) // 2), fill="#2a2a34")
        d.text((W / 2, H / 2), "TU VIDEO AQUÍ", font=_font("Anton-Regular.ttf", 60), anchor="mm", fill="#55556a")
    else:
        d.text((W / 2, H * 0.75), "TU VIDEO AQUÍ", font=_font("Anton-Regular.ttf", 60), anchor="mm", fill="#55556a")
    return bg.convert("RGBA")


def render_one(folder, cat, text=None, pos="arriba", **kw):
    folder.mkdir(parents=True, exist_ok=True)
    for name, (W, H) in FORMATS.items():
        hook = templates.render_template(text, cat, W, H, **kw)
        frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        frame.alpha_composite(hook, (0, max(0, pos_y(pos, H, hook.height))))
        frame.save(folder / f"{name}.png", optimize=True)
        if name == "vertical":
            bb = hook.getbbox()
            hook.crop(bb).save(folder / "hook.png", optimize=True)
            m = sample_bg(W, H)
            m.alpha_composite(frame)
            m.convert("RGB").resize((540, 960), Image.LANCZOS).save(folder / "muestra.jpg", quality=88)


def lamina(path):
    cols, cw, ch, pad, head = 5, 400, 560, 18, 190
    rows = 3
    W = cols * (cw + pad) + pad
    H = head + rows * (ch + pad) + pad
    sheet = Image.new("RGBA", (W, H), "#08080f")
    # brillo de fondo
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-200, -300, W * 0.55, 500), fill=(109, 59, 255, 70))
    gd.ellipse((W * 0.5, -300, W + 200, 500), fill=(227, 18, 43, 60))
    sheet = Image.alpha_composite(sheet, glow.filter(ImageFilter.GaussianBlur(120)))
    d = ImageDraw.Draw(sheet)
    tf = _font("Poppins-Black.ttf", 64)
    title = [("Plantillas de ", "#FFFFFF"), ("Hooks", "#FFD60A"), (" para Clipper", "#FFFFFF")]
    tw = sum(tf.getlength(t) for t, _ in title)
    x = (W - tw) / 2
    for t, col in title:
        d.text((x, 40), t, font=tf, fill=col)
        x += tf.getlength(t)
    sf = _font("Poppins-ExtraBold.ttf", 28)
    sub = "15 estilos listos para tus clips virales · TikTok, Reels y Shorts"
    sw = sf.getlength(sub)
    d.rounded_rectangle(((W - sw) / 2 - 24, 122, (W + sw) / 2 + 24, 170), 12, fill="#E3122B")
    d.text((W / 2, 146), sub, font=sf, anchor="mm", fill="#FFFFFF")
    nf = _font("Anton-Regular.ttf", 30)
    for i, (k, c) in enumerate(templates.CATS.items()):
        im = templates.render_template(None, k, 1080, 1920)
        im = im.crop(im.getbbox())
        x0 = pad + (i % cols) * (cw + pad)
        y0 = head + (i // cols) * (ch + pad)
        d.rounded_rectangle((x0, y0, x0 + cw, y0 + ch), 18, fill="#101018", outline="#2a2a3a", width=2)
        d.text((x0 + 16, y0 + 12), f"{i + 1}.", font=nf, fill=c["color"])
        r = min((cw - 24) / im.width, (ch - 70) / im.height)
        t = im.resize((int(im.width * r), int(im.height * r)), Image.LANCZOS)
        sheet.alpha_composite(t, (x0 + (cw - t.width) // 2, y0 + 56 + (ch - 70 - t.height) // 2))
    sheet.convert("RGB").save(path, quality=92)


def main():
    ap = argparse.ArgumentParser(description="Genera plantillas PRO de hooks")
    ap.add_argument("--cat", choices=list(templates.CATS), help="una sola categoría")
    ap.add_argument("--texto", help="texto del hook (*palabra* = resaltada)")
    ap.add_argument("--color", help="color de resaltado, ej. #22D3EE")
    ap.add_argument("--encabezado", help='texto del encabezado ("" para ocultarlo)')
    ap.add_argument("--icono", help='emoji principal ("" para ninguno)')
    ap.add_argument("--posicion", default="arriba", choices=["arriba", "centro", "abajo"])
    ap.add_argument("--con-fondo", action="store_true", help="con recuadro oscuro detrás (por defecto sin fondo)")
    ap.add_argument("--salida", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.salida)
    kw = {"accent": a.color, "badge": a.encabezado, "icon": a.icono, "panel": a.con_fondo}
    if a.cat:
        folder = out / f"personalizada-{a.cat}"
        render_one(folder, a.cat, a.texto, a.posicion, **kw)
        print("Listo:", folder)
        return
    for i, k in enumerate(templates.CATS, 1):
        render_one(out / f"{i:02d}-{k}", k, a.texto, a.posicion, **kw)
        print(f"  {i:02d} {templates.CATS[k]['name']}")
    lamina(out / "lamina.png")
    print("Listo:", out)


if __name__ == "__main__":
    main()
