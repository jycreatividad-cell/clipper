"""
Encuadre inteligente para vertical: detecta dónde hay caras (no quién es) y mueve el recorte
suavemente para seguirlas. Usa el detector YuNet de OpenCV (models/yunet.onnx).
"""

import subprocess
from pathlib import Path

MODEL = Path(__file__).resolve().parent / "models" / "yunet.onnx"


def available():
    try:
        import cv2  # noqa: F401
        return MODEL.exists()
    except ImportError:
        return False


def video_size(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    w, h = out.strip().split(",")[:2]
    return int(w), int(h)


def face_track(src, t_in, dur, fps=2.0, det_w=960):
    """-> [(t, centro_x 0..1 o None)] muestreando el clip a `fps` cuadros por segundo."""
    import cv2
    import numpy as np
    sw, sh = video_size(src)
    det_h = int(round(sh * det_w / sw / 2)) * 2
    cmd = ["ffmpeg", "-loglevel", "error", "-ss", f"{t_in:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
           "-vf", f"fps={fps},scale={det_w}:{det_h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    det = cv2.FaceDetectorYN.create(str(MODEL), "", (det_w, det_h), 0.6, 0.3, 50)
    size = det_w * det_h * 3
    points, i = [], 0
    while True:
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        frame = np.frombuffer(buf, np.uint8).reshape(det_h, det_w, 3)
        _, faces = det.detect(frame)
        cx = None
        if faces is not None and len(faces):
            # la cara más grande y segura manda; si hay varias cerca, se centra el grupo
            best = max(faces, key=lambda f: f[2] * f[3] * f[-1])
            group = [f for f in faces if abs((f[0] + f[2] / 2) - (best[0] + best[2] / 2)) < det_w * 0.18]
            xs = [f[0] + f[2] / 2 for f in group]
            cx = (min(xs) + max(xs)) / 2 / det_w
        points.append((i / fps, cx))
        i += 1
    p.wait()
    return points


def smooth_path(points, crop_frac, dead=0.12, alpha=0.5):
    """Camino suave del centro del recorte (0..1), con zona muerta para no temblar."""
    if not points:
        return [(0.0, 0.5)]
    known = [c for _, c in points if c is not None]
    if not known:
        return [(0.0, 0.5)]
    lo, hi = crop_frac / 2, 1 - crop_frac / 2
    cur = min(hi, max(lo, known[0]))
    path = []
    for t, c in points:
        if c is not None:
            target = min(hi, max(lo, c))
            if abs(target - cur) > dead * crop_frac:  # solo se mueve si la cara se acerca al borde
                cur = cur + (target - cur) * alpha
        path.append((t, cur))
    # simplificar: quitar puntos que una recta ya explica (menos de 0.8 % de error)
    keep = [path[0]]
    for k in range(1, len(path) - 1):
        t0, c0 = keep[-1]
        t2, c2 = path[k + 1]
        t1, c1 = path[k]
        interp = c0 + (c2 - c0) * (t1 - t0) / ((t2 - t0) or 1)
        if abs(interp - c1) > 0.008:
            keep.append(path[k])
    keep.append(path[-1])
    while len(keep) > 40:  # tope de puntos para la expresión de ffmpeg
        keep = keep[::2] + ([keep[-1]] if keep[-1] is not keep[::2][-1] else [])
    return keep


def crop_x_expr(path, scaled_w, out_w):
    """Expresión de ffmpeg (en píxeles) que interpola el centro del recorte en el tiempo."""
    def px(c):
        return int(max(0, min(scaled_w - out_w, c * scaled_w - out_w / 2)))
    pts = [(t, px(c)) for t, c in path]
    if len(pts) == 1:
        return str(pts[0][1])
    expr = str(pts[-1][1])
    for k in range(len(pts) - 2, -1, -1):
        t0, x0 = pts[k]
        t1, x1 = pts[k + 1]
        dt = max(0.01, t1 - t0)
        expr = f"if(lt(t,{t1:.2f}),{x0}+({x1 - x0})*(t-{t0:.2f})/{dt:.2f},{expr})"
    return expr


def smart_crop_filter(src, t_in, dur, W, H, zoom=1.0):
    """-> cadena de filtro '[0:v]…[v0]' que sigue las caras, o None si no se puede."""
    sw, sh = video_size(src)
    out_h = int(H * zoom) // 2 * 2
    scaled_w = int(round(sw * out_h / sh / 2)) * 2
    if scaled_w <= W:
        return None
    path = smooth_path(face_track(src, t_in, dur), W / scaled_w)
    expr = crop_x_expr(path, scaled_w, W)
    return (f"[0:v]scale={scaled_w}:{out_h},crop={W}:{H}:'{expr}':{(out_h - H) // 2},setsar=1[v0]",
            sum(1 for _ in path))
