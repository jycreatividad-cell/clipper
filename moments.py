"""
Detector de "tomas importantes": busca los momentos donde el audio sube mucho por encima
de lo normal del directo (gritos, discusiones, risas, aplausos, música fuerte).

No necesita internet ni IA: mide el volumen cada medio segundo con ffmpeg y compara
cada instante con el nivel típico de su alrededor (último minuto).
"""

import re
import subprocess

STEP = 0.5          # segundos por medición
FLOOR = -70.0       # silencio


def loudness_curve(input_args):
    """input_args: argumentos de entrada de ffmpeg (p. ej. ["-i", "clip.mp4"]). -> [dB por STEP]"""
    rate = 8000
    n = int(rate * STEP)
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", *input_args,
           "-vn",
           "-af", f"aformat=sample_fmts=fltp:channel_layouts=mono,aresample={rate},"
                  f"asetnsamples=n={n}:p=0,astats=metadata=1:reset=1,"
                  "ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=-",
           "-f", "null", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=900).stdout
    levels = []
    for m in re.finditer(r"RMS_level=(-?[\d.]+|-inf|inf|nan)", out):
        v = m.group(1)
        try:
            x = float(v)
        except ValueError:
            x = FLOOR
        if x != x or x < FLOOR:  # nan o muy bajo
            x = FLOOR
        levels.append(x)
    return levels


def _smooth(xs, k):
    out, acc, q = [], 0.0, []
    for x in xs:
        q.append(x)
        acc += x
        if len(q) > k:
            acc -= q.pop(0)
        out.append(acc / len(q))
    return out


def _median(vals):
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def find_moments(levels, top=8, min_gap=25.0, before=20.0, after=8.0, total=None, min_score=3.0):
    """-> lista de momentos ordenados por intensidad: {t, start, end, score, stars}."""
    if not levels:
        return []
    total = total if total is not None else len(levels) * STEP
    sm = _smooth(levels, 3)                      # 1.5 s
    win = int(30 / STEP)                         # ±30 s alrededor
    base = []
    for i in range(len(sm)):
        lo, hi = max(0, i - win), min(len(sm), i + win)
        base.append(_median(sm[lo:hi:2]))
    scores = []
    for i, x in enumerate(sm):
        rise = x - sm[i - 6] if i >= 6 else 0.0  # subida brusca en 3 s
        sc = (x - base[i]) + 0.5 * max(0.0, rise)
        if x <= FLOOR + 5:
            sc = 0.0
        scores.append(sc)
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    chosen = []
    gap = int(min_gap / STEP)
    for i in order:
        if scores[i] < min_score or len(chosen) >= top:
            break
        if all(abs(i - j) >= gap for j in chosen):
            chosen.append(i)
    res = []
    best = scores[chosen[0]] if chosen else 1
    for i in chosen:
        t = i * STEP
        sc = scores[i]
        res.append({"t": round(t, 1), "start": round(max(0.0, t - before), 1),
                    "end": round(min(total, t + after), 1), "score": round(sc, 1),
                    "stars": 3 if sc >= best * 0.8 else 2 if sc >= best * 0.5 else 1})
    return res
