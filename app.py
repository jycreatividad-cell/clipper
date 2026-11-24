"""
Clipper en Vivo - clips virales desde transmisiones de YouTube (ej. La Casa de Alofoke 3).

Flujo:
  1. Pegas el link del directo y arrancas la grabación: se guarda un "buffer" de los
     últimos N minutos en segmentos pequeños (no se llena el disco).
  2. Cuando pasa algo fuerte, aprietas "Capturar últimos 30s / 1m / 2m / 5m".
  3. En el editor marcas entrada/salida exactas, escribes el hook, eliges formato
     vertical 9:16 y (opcional) subtítulos automáticos palabra por palabra.
  4. Renderizas y descargas el MP4 listo para TikTok / Reels / Shorts.

Requisitos: Python 3.10+, ffmpeg en el PATH, `pip install -r requirements.txt`.
Subtítulos (opcional): `pip install -r requirements-subtitulos.txt`.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import hooks

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("DATA_DIR", str(BASE))).resolve()  # en servidor: un volumen persistente
BUF = DATA / "buffer"
CLIPS = DATA / "clips"
TMP = DATA / "tmp"
COOKIES = DATA / "cookies.txt"
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")  # obligatorio si la app está en internet
YT_PROXY = os.environ.get("YT_PROXY", "")
for d in (BUF, CLIPS, TMP):
    d.mkdir(parents=True, exist_ok=True)

SEG_SECONDS = 4
BUFFER_MIN = int(os.environ.get("BUFFER_MIN", "30"))  # minutos que se guardan del directo
PORT = int(os.environ.get("PORT", "5055"))
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
QUALITY = os.environ.get("CALIDAD", "1080")  # altura máxima a grabar
# primero formatos ya mezclados (HLS del directo); si no hay, video+audio por separado; si no, lo que haya
LIVE_FORMAT = (f"b[height<={QUALITY}]/bv*[height<={QUALITY}]+ba/b/bv*+ba/best")

app = Flask(__name__, static_folder=str(BASE / "static"))
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

# las cookies también se pueden pasar como variable de entorno (contenido de cookies.txt)
if os.environ.get("YT_COOKIES") and not COOKIES.exists():
    COOKIES.write_text(os.environ["YT_COOKIES"].replace("\\n", "\n"), encoding="utf-8")


@app.before_request
def require_password():
    """Protección con usuario/contraseña (Basic Auth) cuando APP_PASSWORD está definida."""
    if not APP_PASSWORD or request.path == "/healthz":
        return None
    auth = request.authorization
    import hmac
    if auth and hmac.compare_digest(auth.password or "", APP_PASSWORD):
        return None
    from flask import Response
    return Response("Acceso restringido", 401, {"WWW-Authenticate": 'Basic realm="Clipper en Vivo"'})


@app.get("/healthz")
def healthz():
    return "ok"


@app.post("/api/cookies")
def api_cookies():
    f = request.files.get("file")
    if not f:
        return jsonify(error="Sube el archivo cookies.txt"), 400
    data = f.read().decode("utf-8", errors="replace")
    if "youtube.com" not in data:
        return jsonify(error="Ese archivo no tiene cookies de youtube.com"), 400
    COOKIES.write_text(data, encoding="utf-8")
    return jsonify(ok=True)


@app.delete("/api/cookies")
def api_cookies_delete():
    COOKIES.unlink(missing_ok=True)
    return jsonify(ok=True)
jobs = {}
jobs_lock = threading.Lock()


# --------------------------------------------------------------------------- utilidades

def js_runtime_args():
    """yt-dlp necesita un motor de JavaScript para YouTube (Deno por defecto; si no, Node o Bun)."""
    if shutil.which("deno"):
        return []
    for rt in ("node", "bun", "quickjs"):
        if shutil.which(rt):
            return ["--js-runtimes", rt]
    return []


def ytdlp():
    cmd = [sys.executable, "-m", "yt_dlp", *js_runtime_args()]
    if COOKIES.exists():
        cmd += ["--cookies", str(COOKIES)]
    if YT_PROXY:
        cmd += ["--proxy", YT_PROXY]
    return cmd


def ffprobe_duration(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30).stdout.strip()
        return float(out)
    except Exception:
        return 0.0


def new_job(kind, label):
    jid = uuid.uuid4().hex[:8]
    with jobs_lock:
        jobs[jid] = {"id": jid, "kind": kind, "label": label, "status": "trabajando",
                     "progress": 0, "error": None, "created": time.time()}
    return jid


def update_job(jid, **kw):
    with jobs_lock:
        if jid in jobs:
            jobs[jid].update(kw)


def run_job(jid, fn, *args):
    def target():
        try:
            fn(jid, *args)
            update_job(jid, status="listo", progress=100)
        except Exception as e:  # noqa: BLE001
            update_job(jid, status="error", error=str(e)[-600:])
    threading.Thread(target=target, daemon=True).start()


def run_ffmpeg(cmd, jid=None, total=None, cwd=None):
    """Ejecuta ffmpeg mostrando progreso en el job."""
    cmd = ["ffmpeg", "-hide_banner", "-y", "-loglevel", "error", "-progress", "pipe:1"] + cmd
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, cwd=cwd)
    err_lines = []
    t = threading.Thread(target=lambda: err_lines.extend(p.stderr), daemon=True)
    t.start()
    for line in p.stdout:
        if jid and total and line.startswith("out_time_us="):
            try:
                secs = int(line.split("=")[1]) / 1e6
                update_job(jid, progress=min(99, int(secs / total * 100)))
            except ValueError:
                pass
    p.wait()
    t.join(timeout=2)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg falló: " + "".join(err_lines)[-500:])


def meta_path(cid):
    return CLIPS / f"{cid}.json"


def save_meta(cid, data):
    meta_path(cid).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def parse_time(s):
    """'1:02:03' / '12:30' / '95' -> segundos."""
    s = str(s).strip()
    if not s:
        return None
    parts = [float(p) for p in s.split(":")]
    secs = 0.0
    for p in parts:
        secs = secs * 60 + p
    return secs


def youtube_id(url):
    m = re.search(r"(?:v=|youtu\.be/|/live/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else None


# --------------------------------------------------------------------------- fuentes

FONT_CANDIDATES = [
    # (ruta, nombre de familia para los subtítulos)
    ("C:/Windows/Fonts/arialbd.ttf", "Arial"),
    ("C:/Windows/Fonts/impact.ttf", "Impact"),
    ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "Arial"),
    ("/Library/Fonts/Arial Bold.ttf", "Arial"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVu Sans"),
    ("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", "DejaVu Sans"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "Liberation Sans"),
    ("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf", "FreeSans"),
]


def find_font():
    custom = BASE / "fuente.ttf"  # pon aquí tu propia fuente si quieres
    if custom.exists():
        return custom, os.environ.get("FUENTE_NOMBRE", "Montserrat")
    for path, family in FONT_CANDIDATES:
        if Path(path).exists():
            return Path(path), family
    return None, "Arial"


# --------------------------------------------------------------------------- grabadora en vivo

def diagnose(url):
    """Explica en español por qué yt-dlp no consigue el video."""
    lines = []
    try:
        ver = subprocess.run([sys.executable, "-m", "yt_dlp", "--version"], capture_output=True,
                             text=True, timeout=20).stdout.strip()
    except Exception:  # noqa: BLE001
        ver = "?"
    js = "deno" if shutil.which("deno") else next((r for r in ("node", "bun", "quickjs") if shutil.which(r)), None)
    lines.append(f"yt-dlp {ver} · motor JS: {js or 'NINGUNO'} · cookies: {'sí' if COOKIES.exists() else 'no'}")
    try:
        p = subprocess.run(ytdlp() + ["-F", "--no-warnings", url], capture_output=True, text=True, timeout=90)
        out = (p.stdout or "") + (p.stderr or "")
    except Exception as e:  # noqa: BLE001
        out = str(e)
    low = out.lower()
    has_video = any(t in out for t in (" mp4 ", " webm ", " ts ")) or "m3u8" in low
    if "not a bot" in low or "sign in to confirm" in low or "429" in low:
        lines.append("→ YouTube está bloqueando al servidor (\"confirma que no eres un bot\"). "
                     "Sube un cookies.txt nuevo en 🍪 Cookies de YouTube (exportado de una cuenta "
                     "secundaria con la sesión abierta) o usa un proxy (YT_PROXY).")
    elif "not currently live" in low or "will begin" in low or "premieres in" in low or "offline" in low:
        lines.append("→ El directo no está en vivo ahora mismo. Para repeticiones usa "
                     "\"Capturar de un video ya subido\".")
    elif "unable to connect" in low or "timed out" in low or "name resolution" in low or "proxyerror" in low:
        lines.append("→ El servidor no pudo conectarse a YouTube (red o proxy). Revisa YT_PROXY o la conexión.")
    elif "private video" in low or "members-only" in low or "video unavailable" in low:
        lines.append("→ El video es privado, solo para miembros o no está disponible.")
    elif not has_video:
        if not js:
            lines.append("→ Falta un motor de JavaScript: YouTube solo entrega imágenes sin él. "
                         "Instala Deno (Windows: winget install DenoLand.Deno) y reinicia la app.")
        else:
            lines.append("→ YouTube solo entregó imágenes, sin video. Casi siempre se arregla "
                         "actualizando yt-dlp (pip install -U \"yt-dlp[default]\") y subiendo cookies nuevas.")
    else:
        lines.append("→ Hay formatos disponibles pero la descarga falló. Actualiza yt-dlp y prueba de nuevo.")
    return "\n".join(lines)


class Recorder:
    def __init__(self):
        self.url = None
        self.running = False
        self.error = None
        self.started = None
        self.procs = []
        self.lock = threading.Lock()   # protege el buffer mientras se captura
        self.thread = None
        self.dur_cache = {}

    # -- control
    def start(self, url):
        self.stop()
        for f in BUF.glob("seg_*.ts"):
            f.unlink(missing_ok=True)
        self.dur_cache.clear()
        self.url, self.error, self.running, self.started = url, None, True, time.time()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self._kill()

    def _kill(self):
        for p in self.procs:
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:  # noqa: BLE001
                try:
                    p.kill()
                except Exception:  # noqa: BLE001
                    pass
        self.procs = []

    def _next_number(self):
        nums = [int(f.stem.split("_")[1]) for f in BUF.glob("seg_*.ts")]
        return max(nums) + 1 if nums else 0

    def _loop(self):
        fails = 0
        log = open(BUF / "grabadora.log", "a", encoding="utf-8", errors="replace")
        while self.running:
            t0 = time.time()
            is_local = Path(self.url).exists() or self.url.endswith(".m3u8")
            seg_args = ["-map", "0:v:0", "-map", "0:a:0?", "-c", "copy",
                        "-f", "segment", "-segment_time", str(SEG_SECONDS),
                        "-reset_timestamps", "1",
                        "-segment_start_number", str(self._next_number()),
                        str(BUF / "seg_%06d.ts")]
            if is_local:  # modo prueba: archivo local o m3u8 directo
                pre = ["-re", "-stream_loop", "-1"] if Path(self.url).exists() else []
                ff = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", *pre,
                                       "-i", self.url, *seg_args],
                                      stdin=subprocess.DEVNULL, stderr=log)
                self.procs = [ff]
            else:
                yt = subprocess.Popen(
                    ytdlp() + ["-f", LIVE_FORMAT, "--no-part", "--quiet",
                               "--no-warnings", "-o", "-", self.url],
                    stdout=subprocess.PIPE, stderr=log)
                ff = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error",
                                       "-i", "pipe:0", *seg_args],
                                      stdin=yt.stdout, stderr=log)
                yt.stdout.close()
                self.procs = [yt, ff]
            ff.wait()
            self._kill()
            if not self.running:
                break
            # el directo se cortó o el link expiró: reintentar
            fails = fails + 1 if time.time() - t0 < 30 else 0
            if fails >= 4:
                self.error = ("No se pudo grabar el directo.\n" + diagnose(self.url) +
                              "\n\nÚltimas líneas de buffer/grabadora.log:\n" + self.tail_log(4))
                self.running = False
                break
            time.sleep(3)
        log.close()

    def tail_log(self, n=6):
        try:
            lines = (BUF / "grabadora.log").read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(lines[-n:])
        except FileNotFoundError:
            return ""

    # -- buffer
    def segments(self):
        """Segmentos terminados (el último se está escribiendo todavía)."""
        segs = sorted(BUF.glob("seg_*.ts"), key=lambda f: int(f.stem.split("_")[1]))
        return segs[:-1] if self.running else segs

    def seg_dur(self, f):
        key = (f.name, f.stat().st_size)
        if key not in self.dur_cache:
            self.dur_cache[key] = ffprobe_duration(f) or SEG_SECONDS
        return self.dur_cache[key]

    def cleanup(self):
        limit = time.time() - BUFFER_MIN * 60
        with self.lock:
            for f in BUF.glob("seg_*.ts"):
                try:
                    if f.stat().st_mtime < limit:
                        f.unlink()
                except FileNotFoundError:
                    pass

    def buffer_seconds(self):
        segs = self.segments()
        if not segs:
            return 0
        try:
            return int(segs[-1].stat().st_mtime - segs[0].stat().st_mtime + SEG_SECONDS)
        except FileNotFoundError:
            return 0

    def capture(self, seconds, dest_dir):
        """Copia los segmentos que cubren los últimos `seconds` segundos."""
        with self.lock:
            segs = self.segments()
            if not segs:
                raise RuntimeError("El buffer está vacío. Espera unos segundos después de iniciar.")
            chosen, total = [], 0.0
            for f in reversed(segs):
                d = self.seg_dur(f)
                chosen.insert(0, (f, d))
                total += d
                if total >= seconds:
                    break
            copies = []
            for f, d in chosen:
                dst = dest_dir / f.name
                shutil.copy2(f, dst)
                copies.append(dst)
        return copies, total


rec = Recorder()


def janitor():
    while True:
        rec.cleanup()
        # borrar temporales viejos (>2h)
        for d in TMP.iterdir():
            try:
                if time.time() - d.stat().st_mtime > 7200:
                    shutil.rmtree(d, ignore_errors=True) if d.is_dir() else d.unlink()
            except FileNotFoundError:
                pass
        time.sleep(20)


threading.Thread(target=janitor, daemon=True).start()


# --------------------------------------------------------------------------- capturas

def job_capture_buffer(jid, seconds):
    cid = "cap_" + time.strftime("%H%M%S") + "_" + jid[:4]
    work = TMP / cid
    work.mkdir()
    copies, total = rec.capture(seconds, work)
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{c.name}'\n" for c in copies), encoding="utf-8")
    offset = max(0.0, total - seconds)
    out = CLIPS / f"{cid}.mp4"
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", "list.txt", "-ss", f"{offset:.2f}",
                "-c", "copy", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart",
                str(out)], cwd=str(work))
    shutil.rmtree(work, ignore_errors=True)
    save_meta(cid, {"id": cid, "type": "captura", "file": out.name, "created": time.time(),
                    "duration": ffprobe_duration(out), "source": rec.url,
                    "label": f"Últimos {int(seconds)}s · {time.strftime('%I:%M:%S %p')}"})
    update_job(jid, result=cid)


def job_capture_vod(jid, url, start, end):
    cid = "cap_" + time.strftime("%H%M%S") + "_" + jid[:4]
    out_tpl = str(CLIPS / f"{cid}.%(ext)s")
    cmd = ytdlp() + ["-f", f"bv*[height<={QUALITY}]+ba/b[height<={QUALITY}]/bv*+ba/b/best",
                     "--download-sections", f"*{start}-{end}",
                     "--merge-output-format", "mp4", "--no-playlist",
                     "--quiet", "--no-warnings", "-o", out_tpl, url]
    update_job(jid, progress=10)
    p = subprocess.run(cmd, capture_output=True, text=True)
    files = list(CLIPS.glob(f"{cid}.*"))
    if p.returncode != 0 or not files:
        raise RuntimeError("yt-dlp falló: " + (p.stderr or p.stdout)[-500:])
    out = files[0]
    if out.suffix != ".mp4":
        fixed = CLIPS / f"{cid}.mp4"
        run_ffmpeg(["-i", str(out), "-c", "copy", "-movflags", "+faststart", str(fixed)])
        out.unlink()
        out = fixed
    save_meta(cid, {"id": cid, "type": "captura", "file": out.name, "created": time.time(),
                    "duration": ffprobe_duration(out), "source": url,
                    "label": f"Video {fmt_t(start)}–{fmt_t(end)}"})
    update_job(jid, result=cid)


def fmt_t(s):
    s = int(s)
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


# --------------------------------------------------------------------------- render vertical

FORMATS = {
    "vertical": (1080, 1920),
    "cuadrado": (1080, 1080),
    "horizontal": (1920, 1080),
}

_whisper = {}


def transcribe_words(audio_path):
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("Para subtítulos instala: pip install -r requirements-subtitulos.txt") from e
    if "m" not in _whisper:
        _whisper["m"] = WhisperModel(WHISPER_MODEL, device="auto", compute_type="int8")
    segments, _ = _whisper["m"].transcribe(str(audio_path), language="es",
                                            word_timestamps=True, vad_filter=True)
    words = []
    for seg in segments:
        for w in seg.words or []:
            txt = w.word.strip()
            if txt:
                words.append((w.start, w.end, txt))
    return words


def ass_time(t):
    t = max(0, t)
    h, m = int(t // 3600), int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass(words, w, h, family, path, per_chunk=3):
    size = int(w * 0.085) if w < h else int(h * 0.075)
    margin_v = int(h * 0.28) if w < h else int(h * 0.10)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{family},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{max(4, size // 12)},3,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    chunks = [words[i:i + per_chunk] for i in range(0, len(words), per_chunk)]
    for ci, chunk in enumerate(chunks):
        chunk_end = chunk[-1][1]
        if ci + 1 < len(chunks):
            chunk_end = min(chunks[ci + 1][0][0], chunk_end + 0.6)
        for i, (st, en, _) in enumerate(chunk):
            nxt = chunk[i + 1][0] if i + 1 < len(chunk) else chunk_end
            parts = []
            for j, (_, _, txt) in enumerate(chunk):
                txt = txt.upper().replace("{", "").replace("}", "")
                if j == i:  # palabra actual en amarillo y un poco más grande
                    parts.append(r"{\c&H00FFFF&\fscx110\fscy110}" + txt + r"{\c&HFFFFFF&\fscx100\fscy100}")
                else:
                    parts.append(txt)
            lines.append(f"Dialogue: 0,{ass_time(st)},{ass_time(max(nxt, st + 0.05))},Sub,,0,0,0,,{' '.join(parts)}")
    Path(path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


def job_render(jid, opts):
    src_meta = json.loads(meta_path(opts["clip_id"]).read_text(encoding="utf-8"))
    src = CLIPS / src_meta["file"]
    t_in = float(opts.get("in") or 0)
    t_out = float(opts.get("out") or src_meta.get("duration") or ffprobe_duration(src))
    dur = t_out - t_in
    if dur <= 0.3:
        raise RuntimeError("La salida debe ser mayor que la entrada.")
    fmt = opts.get("format", "vertical")
    W, H = FORMATS.get(fmt, FORMATS["vertical"])
    mode = opts.get("mode", "blur")  # blur = fondo desenfocado, fill = recorte a pantalla completa
    pos = min(1.0, max(0.0, float(opts.get("pos", 50)) / 100))
    zoom = min(2.0, max(1.0, float(opts.get("zoom", 100)) / 100))

    rid = "clip_" + time.strftime("%H%M%S") + "_" + jid[:4]
    work = TMP / rid
    work.mkdir()

    font, family = find_font()
    if font:
        shutil.copy(font, work / ("font" + font.suffix.lower()))
        fontfile = "font" + font.suffix.lower()
    else:
        fontfile = None

    # ---- video base
    if fmt == "horizontal":
        base = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1[v0]")
    elif mode == "fill":
        base = (f"[0:v]scale={W}*{zoom}:{H}*{zoom}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H}:(iw-{W})*{pos}:(ih-{H})/2,setsar=1[v0]")
    else:
        fg_w = int(W * zoom) // 2 * 2
        base = (f"[0:v]split[a][b];"
                f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"boxblur=25:3,eq=brightness=-0.08[bg];"
                f"[b]scale={fg_w}:-2[fg0];[fg0]crop='min(iw,{W})':ih:(iw-min(iw\\,{W}))*{pos}:0[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v0]")
    chain = [base]
    last = "v0"
    n = 0

    def add(filter_str):
        nonlocal last, n
        n += 1
        chain.append(f"[{last}]{filter_str}[v{n}]")
        last = f"v{n}"

    font_opt = f"fontfile={fontfile}:" if fontfile else ""

    # ---- hook (imagen PNG con el estilo elegido, ver hooks.py)
    hook = (opts.get("hook") or "").strip()
    extra_inputs = []
    if hook:
        img = hooks.render_hook(hook, opts.get("hook_style") or hooks.DEFAULT_STYLE, W,
                                **hook_kwargs(opts, opts.get("hook_style") or "", W, H))
        if img:
            img.save(work / "hook.png")
            extra_inputs = ["-i", "hook.png"]
            y = hook_y(opts.get("hook_pos", "arriba"), H, img.height)
            chain.append(f"[{last}][1:v]overlay=0:{y}:eof_action=repeat[vh]")
            last = "vh"

    # ---- marca de agua / @usuario
    wm = (opts.get("watermark") or "").strip()
    if wm:
        (work / "wm.txt").write_text(wm, encoding="utf-8")
        fs = int(min(W, H) * 0.04)
        y = f"h-{int(H * 0.16)}" if H > W else f"h-{int(fs * 2)}"
        add(f"drawtext={font_opt}textfile=wm.txt:fontsize={fs}:fontcolor=white@0.85:"
            f"borderw=3:bordercolor=black@0.6:x=(w-text_w)/2:y={y}")

    # ---- subtítulos automáticos
    if opts.get("subs"):
        update_job(jid, label="Transcribiendo audio…", progress=5)
        wav = work / "audio.wav"
        run_ffmpeg(["-ss", f"{t_in:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
                    "-vn", "-ac", "1", "-ar", "16000", str(wav)])
        words = transcribe_words(wav)
        if words:
            build_ass(words, W, H, family, work / "subs.ass")
            add("subtitles=subs.ass:fontsdir=.")
        update_job(jid, label="Renderizando clip…")

    out = CLIPS / f"{rid}.mp4"
    filt = ";".join(chain)
    cmd = ["-ss", f"{t_in:.3f}", "-t", f"{dur:.3f}", "-i", str(src), *extra_inputs,
           "-filter_complex", filt, "-map", f"[{last}]", "-map", "0:a:0?",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-r", "30", "-c:a", "aac", "-b:a", "160k", "-t", f"{dur:.3f}", "-movflags", "+faststart", str(out)]
    run_ffmpeg(cmd, jid=jid, total=dur, cwd=str(work))
    shutil.rmtree(work, ignore_errors=True)
    save_meta(rid, {"id": rid, "type": "final", "file": out.name, "created": time.time(),
                    "duration": dur, "format": fmt, "hook": hook, "from": opts["clip_id"],
                    "label": hook.replace("*", "")[:60] or f"Clip {fmt} {dur:.0f}s"})
    update_job(jid, result=rid)


def hook_kwargs(o, style, W, H, prefix="hook_"):
    """parámetros de tamaño y de plantilla, desde el JSON del render o la URL de la vista previa."""
    size = float(o.get(prefix + "size", o.get("size", 100)) or 100) / 100
    kw = {"scale": size * (1 if (H > W or style.startswith("t:")) else 0.75), "height": H}
    if style.startswith("t:"):
        for k in ("accent", "badge", "icon"):
            v = o.get("tpl_" + k)
            if v is not None and v != "__default__":
                kw[k] = str(v)
        if "tpl_panel" in o:
            kw["panel"] = str(o.get("tpl_panel")).lower() not in ("0", "false", "no")
        if kw.get("accent") and not re.fullmatch(r"#[0-9A-Fa-f]{6}", kw["accent"]):
            kw.pop("accent")
    return kw


def hook_y(pos, H, h):
    if pos == "centro":
        return max(0, (H - h) // 2)
    if pos == "abajo":
        return max(0, int(H * 0.66) - h // 2)
    return int(H * 0.08) if H > 1200 else int(H * 0.03)


def preview_vf(fmt, mode, W, H):
    if fmt == "horizontal":
        return f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2"
    if mode == "fill":
        return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    return (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur=25:3,eq=brightness=-0.08[bg];[b]scale={W}:-2[fg];[bg][fg]overlay=0:(H-h)/2")


_preview_bg = {}


def preview_background(W, H):
    """Fondo de ejemplo (o un fotograma real de la captura) para la vista previa del hook."""
    from PIL import Image, ImageDraw
    key = (W, H)
    if key not in _preview_bg:
        bg = Image.new("RGB", (W, H), "#1b1410")
        d = ImageDraw.Draw(bg)
        for i in range(H):
            t = i / H
            d.line([(0, i), (W, i)], fill=(int(60 + 60 * t), int(40 + 25 * t), int(30 + 10 * t)))
        vh = W * 9 // 16
        d.rectangle((0, (H - vh) // 2, W, (H + vh) // 2), fill="#2b2b33")
        _preview_bg[key] = bg.convert("RGBA")
    return _preview_bg[key].copy()


@app.get("/api/hook-preview")
def api_hook_preview():
    from io import BytesIO
    from flask import send_file
    from PIL import Image
    a = request.args
    fmt = a.get("format", "vertical")
    W, H = FORMATS.get(fmt, FORMATS["vertical"])
    frame = None
    cid = a.get("clip_id", "")
    if re.fullmatch(r"[A-Za-z0-9_]+", cid) and meta_path(cid).exists():  # fotograma real
        src = CLIPS / json.loads(meta_path(cid).read_text(encoding="utf-8"))["file"]
        t = float(a.get("t", 0) or 0)
        try:
            raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(src),
                                  "-frames:v", "1", "-vf", preview_vf(fmt, a.get("mode", "blur"), W, H),
                                  "-f", "image2pipe", "-vcodec", "png", "-"],
                                 capture_output=True, timeout=15).stdout
            frame = Image.open(BytesIO(raw)).convert("RGBA")
        except Exception:  # noqa: BLE001
            frame = None
    if frame is None:
        frame = preview_background(W, H)
    text = a.get("text", "").strip() or "ESCRIBE TU *HOOK* AQUÍ 🔥"
    style = a.get("style", hooks.DEFAULT_STYLE)
    if style.startswith("t:") and not a.get("text", "").strip():
        text = ""  # la plantilla usa su texto de ejemplo
    img = hooks.render_hook(text, style, W, **hook_kwargs(a, style, W, H, prefix=""))
    if img:
        y = hook_y(a.get("pos", "arriba"), H, img.height)
        frame.alpha_composite(img, (0, y))
        if a.get("crop") == "1":  # miniatura: solo la zona del hook
            frame = frame.crop((0, max(0, y - 30), W, min(H, y + img.height + 30)))
            H = frame.height
    w = int(a.get("w", 360))
    frame = frame.convert("RGB").resize((w, int(H * w / W)))
    buf = BytesIO()
    frame.save(buf, "JPEG", quality=82)
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg", max_age=0)


@app.get("/api/hook-styles")
def api_hook_styles():
    import templates
    return jsonify(simple=hooks.style_list(), templates=templates.template_list())


# --------------------------------------------------------------------------- API

@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/clips/<path:name>")
def clip_file(name):
    return send_from_directory(CLIPS, name, as_attachment=request.args.get("dl") == "1")


@app.post("/api/buffer/start")
def api_start():
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify(error="Pega el link del directo"), 400
    rec.start(url)
    return jsonify(ok=True)


@app.post("/api/buffer/stop")
def api_stop():
    rec.stop()
    return jsonify(ok=True)


@app.post("/api/capture")
def api_capture():
    d = request.json or {}
    if d.get("seconds"):
        secs = float(d["seconds"])
        jid = new_job("captura", f"Capturando últimos {int(secs)}s")
        run_job(jid, job_capture_buffer, secs)
    else:
        url = (d.get("url") or "").strip()
        start, end = parse_time(d.get("start", "")), parse_time(d.get("end", ""))
        if not url or start is None or end is None or end <= start:
            return jsonify(error="Pon el link y un rango válido (ej. 1:02:10 a 1:03:40)"), 400
        if end - start > 1800:
            return jsonify(error="Máximo 30 minutos por captura"), 400
        jid = new_job("captura", f"Descargando {fmt_t(start)}–{fmt_t(end)}")
        run_job(jid, job_capture_vod, url, start, end)
    return jsonify(job=jid)


@app.post("/api/render")
def api_render():
    d = request.json or {}
    if not d.get("clip_id") or not meta_path(d["clip_id"]).exists():
        return jsonify(error="Captura no encontrada"), 404
    jid = new_job("render", "Renderizando clip…")
    run_job(jid, job_render, d)
    return jsonify(job=jid)


@app.delete("/api/clip/<cid>")
def api_delete(cid):
    if not re.fullmatch(r"[A-Za-z0-9_]+", cid):
        return jsonify(error="id inválido"), 400
    for f in CLIPS.glob(f"{cid}.*"):
        f.unlink(missing_ok=True)
    return jsonify(ok=True)


@app.get("/api/status")
def api_status():
    clips = []
    for m in CLIPS.glob("*.json"):
        try:
            data = json.loads(m.read_text(encoding="utf-8"))
            if (CLIPS / data["file"]).exists():
                clips.append(data)
        except Exception:  # noqa: BLE001
            pass
    clips.sort(key=lambda c: c["created"], reverse=True)
    with jobs_lock:
        js = sorted(jobs.values(), key=lambda j: j["created"], reverse=True)[:12]
    return jsonify(
        recorder={"running": rec.running, "url": rec.url, "error": rec.error,
                  "buffer": rec.buffer_seconds(), "max": BUFFER_MIN * 60,
                  "video_id": youtube_id(rec.url)},
        jobs=js, clips=clips, subs_available=_has_whisper(), font=find_font()[1],
        cookies=COOKIES.exists(),
        js_runtime=bool(shutil.which("deno") or any(shutil.which(r) for r in ("node", "bun", "quickjs"))))


def _has_whisper():
    try:
        import importlib.util
        return importlib.util.find_spec("faster_whisper") is not None
    except Exception:  # noqa: BLE001
        return False


def check_deps():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("\n[!] No encuentro ffmpeg. Instálalo:")
        if platform.system() == "Windows":
            print("    winget install Gyan.FFmpeg   (y luego cierra y abre la terminal)")
        elif platform.system() == "Darwin":
            print("    brew install ffmpeg")
        else:
            print("    sudo apt install ffmpeg")
        sys.exit(1)


if __name__ == "__main__":
    check_deps()
    host = os.environ.get("HOST", "127.0.0.1")
    if host != "127.0.0.1" and not APP_PASSWORD:
        print("[!] La app está abierta a la red sin contraseña. Define APP_PASSWORD.")
    url = f"http://127.0.0.1:{PORT}"
    print(f"\n  Clipper en Vivo listo -> {url}\n  (Ctrl+C para cerrar)\n")
    if os.environ.get("NO_BROWSER") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=PORT, threaded=True)
