"""
Crea la biblioteca de efectos de sonido de Clipper desde cero (síntesis), sin audios de terceros.
Uso: python generar_sonidos.py   ->  static/sfx/*.mp3  (requiere numpy y ffmpeg)
"""
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 44100
OUT = Path(__file__).resolve().parent / "static" / "sfx"
rng = np.random.default_rng(7)


def t_(d):
    return np.arange(int(SR * d)) / SR


def env(d, attack=0.005, decay=3.0):
    t = t_(d)
    a = np.minimum(1, t / max(attack, 1e-4))
    return a * np.exp(-decay * t)


def saw(f, t):
    out = np.zeros_like(t)
    for k in range(1, 12):
        out += np.sin(2 * np.pi * f * k * t) / k
    return out


def norm(x, peak=0.89):
    m = np.max(np.abs(x)) or 1
    return x / m * peak


def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.zeros_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def boom():  # impacto grave tipo "boom" con caída de tono
    d = 1.8
    t = t_(d)
    f = 70 * np.exp(-1.6 * t) + 32
    phase = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(phase) * np.exp(-2.2 * t)
    body = np.tanh(3.2 * body)  # saturación
    click = rng.normal(0, 1, len(t)) * np.exp(-90 * t) * 0.5
    sub = np.sin(2 * np.pi * 40 * t) * np.exp(-1.5 * t) * 0.6
    return norm(lowpass(body + click + sub, 900))


def whoosh():
    d = 0.9
    t = t_(d)
    n = rng.normal(0, 1, len(t))
    shape = np.sin(np.pi * t / d) ** 2.5
    out = np.zeros_like(n)
    # barrido de filtro: mezcla de pasa-bajos con corte creciente
    for cut, w in ((600, 1.0), (1800, 0.7), (4000, 0.4)):
        out += lowpass(n, cut) * w
    return norm(out * shape)


def ding():
    d = 1.6
    t = t_(d)
    x = (np.sin(2 * np.pi * 1318.5 * t) + 0.5 * np.sin(2 * np.pi * 2637 * t) +
         0.25 * np.sin(2 * np.pi * 3955 * t) * np.exp(-6 * t))
    return norm(x * env(d, 0.002, 3.2))


def dun_dun():  # "dun dun duuun" dramático
    notes = [(293.66, 0.32), (277.18, 0.32), (233.08, 1.6)]
    parts = []
    for f, d in notes:
        t = t_(d)
        x = saw(f, t) + 0.6 * saw(f / 2, t)
        x *= env(d, 0.01, 1.2 if d > 1 else 4)
        parts.append(lowpass(x, 2200))
        parts.append(np.zeros(int(SR * 0.04)))
    return norm(np.concatenate(parts))


def trombone_triste():  # "wah wah wah waaah"
    notes = [(311.1, 0.42), (293.7, 0.42), (277.2, 0.42), (261.6, 1.5)]
    parts = []
    for i, (f, d) in enumerate(notes):
        t = t_(d)
        vib = 1 + (0.012 * np.sin(2 * np.pi * 6 * t) * (t > 0.3) if i == 3 else 0)
        phase = 2 * np.pi * np.cumsum(f * vib * np.ones_like(t)) / SR
        x = sum(np.sin(phase * k) / k ** 1.3 for k in range(1, 9))
        e = np.minimum(1, t / 0.04) * np.minimum(1, (d - t) / 0.08)
        parts.append(lowpass(x * e, 1800))
    return norm(np.concatenate(parts))


def bocina():  # bocina de estadio, tres toques
    parts = []
    for d in (0.18, 0.18, 0.9):
        t = t_(d)
        f = 466 * (1 + 0.01 * np.sin(2 * np.pi * 7 * t))
        phase = 2 * np.pi * np.cumsum(f) / SR
        x = sum(np.sin(phase * k * r) / k for k in range(1, 10) for r in (1.0, 1.26))
        e = np.minimum(1, t / 0.01) * np.minimum(1, (d - t) / 0.03)
        parts += [np.tanh(1.5 * x * e), np.zeros(int(SR * 0.06))]
    return norm(np.concatenate(parts))


def grillos():  # silencio incómodo
    d = 2.6
    t = t_(d)
    car = np.sin(2 * np.pi * 4600 * t)
    chirp = (np.sin(2 * np.pi * 28 * t) > 0.3).astype(float)
    groups = ((t % 0.65) < 0.24).astype(float)
    x = car * chirp * groups
    return norm(lowpass(x, 7000) * 0.6, 0.6)


def suspenso():  # subida de tensión
    d = 2.4
    t = t_(d)
    f = 180 * np.exp(1.1 * t)
    phase = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(phase) + 0.4 * np.sin(phase * 1.5)
    n = lowpass(rng.normal(0, 1, len(t)), 3000) * (t / d) * 0.6
    return norm((x + n) * (t / d) ** 1.6)


def error():
    parts = []
    for _ in range(2):
        d = 0.22
        t = t_(d)
        x = np.sign(np.sin(2 * np.pi * 150 * t)) * 0.6 + np.sign(np.sin(2 * np.pi * 157 * t)) * 0.4
        parts += [lowpass(x, 2500) * np.minimum(1, (d - t) / 0.02), np.zeros(int(SR * 0.07))]
    return norm(np.concatenate(parts), 0.75)


def pop():
    d = 0.25
    t = t_(d)
    f = 300 + 1400 * np.exp(-25 * t)
    phase = 2 * np.pi * np.cumsum(f) / SR
    return norm(np.sin(phase) * env(d, 0.001, 18))


def boing():
    d = 0.8
    t = t_(d)
    f = 220 + 160 * np.sin(2 * np.pi * 9 * t) * np.exp(-3 * t) + 120 * t
    phase = 2 * np.pi * np.cumsum(f) / SR
    return norm(np.sin(phase) * env(d, 0.002, 4))


def redoble():  # redoble de tambor que termina en golpe
    d = 2.0
    t = t_(d)
    hits = np.zeros_like(t)
    for k, start in enumerate(np.arange(0, 1.6, 0.045)):
        i = int(start * SR)
        n = min(len(t) - i, int(SR * 0.06))
        hits[i:i + n] += rng.normal(0, 1, n) * np.exp(-60 * np.arange(n) / SR) * (0.3 + 0.7 * start / 1.6)
    crash_i = int(1.62 * SR)
    m = len(t) - crash_i
    hits[crash_i:] += rng.normal(0, 1, m) * np.exp(-3 * np.arange(m) / SR) * 1.3
    return norm(lowpass(hits, 5000))


def flash():  # cámara / foto
    d = 0.35
    t = t_(d)
    x = rng.normal(0, 1, len(t)) * (np.exp(-70 * t) + 0.6 * np.exp(-70 * np.maximum(0, t - 0.09)) * (t > 0.09))
    return norm(lowpass(x, 6000), 0.8)


def glitch():
    d = 0.6
    t = t_(d)
    x = np.zeros_like(t)
    for start in np.arange(0, d, 0.05):
        i = int(start * SR)
        n = int(SR * 0.04)
        f = rng.choice([180, 420, 900, 1500, 2600])
        seg = np.sign(np.sin(2 * np.pi * f * np.arange(n) / SR)) * rng.uniform(0.3, 1)
        x[i:i + n] += seg[:len(x) - i]
    return norm(x, 0.7)


SOUNDS = {
    "boom": ("💥", "Boom", boom),
    "whoosh": ("💨", "Whoosh", whoosh),
    "ding": ("🔔", "Ding", ding),
    "dundun": ("😱", "Dun dun duuun", dun_dun),
    "triste": ("🎺", "Trompeta triste", trombone_triste),
    "bocina": ("📣", "Bocina", bocina),
    "grillos": ("🦗", "Grillos (silencio)", grillos),
    "suspenso": ("😬", "Suspenso", suspenso),
    "error": ("❌", "Error", error),
    "pop": ("🫧", "Pop", pop),
    "boing": ("🤪", "Boing", boing),
    "redoble": ("🥁", "Redoble", redoble),
    "flash": ("📸", "Flash", flash),
    "glitch": ("📺", "Glitch", glitch),
}


def level(x, target_db=-16.0):
    """Iguala el volumen percibido (RMS) sin pasarse del pico."""
    rms = np.sqrt(np.mean(x ** 2)) or 1e-9
    gain = min(10 ** (target_db / 20) / rms, 0.89 / (np.max(np.abs(x)) or 1))
    return x * gain


def save(name, x):
    x = level(x)
    OUT.mkdir(parents=True, exist_ok=True)
    wav = OUT / f"{name}.wav"
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-ac", "2", "-b:a", "160k",
                    str(OUT / f"{name}.mp3")], check=True)
    wav.unlink()


if __name__ == "__main__":
    for key, (_, label, fn) in SOUNDS.items():
        save(key, fn())
        print("  ✓", label)
