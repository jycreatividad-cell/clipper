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
from functools import lru_cache
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_file, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

import hooks
import moments
import smartcrop
from social import Social

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
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # https detrás de Railway/Render
social = Social(DATA)
LOGO = DATA / "logo.png"
RENDER_WORKERS = int(os.environ.get("RENDER_WORKERS") or max(1, min(4, (os.cpu_count() or 2) // 2)))  # renders a la vez
RENDER_SEM = threading.Semaphore(RENDER_WORKERS)
markers = []                       # momentos marcados con la tecla M
markers_lock = threading.Lock()

# las cookies también se pueden pasar como variable de entorno (contenido de cookies.txt)
if os.environ.get("YT_COOKIES") and not COOKIES.exists():
    COOKIES.write_text(os.environ["YT_COOKIES"].replace("\\n", "\n"), encoding="utf-8")


# ---- acceso con contraseña: pantalla de inicio de sesión + sesión recordada (ideal para iPhone)
def _secret_key():
    f = DATA / ".secret"
    if not f.exists():
        f.write_text(uuid.uuid4().hex + uuid.uuid4().hex)
        try:
            os.chmod(f, 0o600)
        except OSError:
            pass
    return f.read_text().strip()


app.secret_key = _secret_key()
app.config.update(PERMANENT_SESSION_LIFETIME=180 * 86400, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SECURE=os.environ.get("PUBLIC_URL", "").startswith("https"))
PW_TAG = __import__("hashlib").sha256(("clipper:" + APP_PASSWORD).encode()).hexdigest()[:16]
OPEN_PATHS = ("/healthz", "/login", "/manifest.webmanifest", "/sw.js", "/static/icons/")


@app.before_request
def require_password():
    """Si APP_PASSWORD está definida, pide iniciar sesión (o Basic Auth para scripts)."""
    import hmac
    from flask import session
    if not APP_PASSWORD or request.path.startswith("/pub/") or request.path.startswith(OPEN_PATHS):
        return None
    if session.get("ok") == PW_TAG:
        return None
    auth = request.authorization
    if auth and hmac.compare_digest(auth.password or "", APP_PASSWORD):
        return None
    if request.path.startswith("/api/") or request.method != "GET":
        return jsonify(error="Sesión vencida: vuelve a entrar", login=True), 401
    return redirect("/login?next=" + request.full_path.rstrip("?"))


LOGIN_HTML = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Clipper"><meta name="theme-color" content="#0d0d10">
<link rel="apple-touch-icon" href="/static/icons/icon-180.png"><link rel="manifest" href="/manifest.webmanifest">
<title>Clipper · Entrar</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0d0d10;
color:#f2f2f5;font:16px system-ui,-apple-system,sans-serif;padding:24px;box-sizing:border-box}
form{width:100%;max-width:360px;text-align:center}img{width:96px;border-radius:22px;box-shadow:0 10px 40px #ff2e6355}
h1{font-size:24px;margin:18px 0 4px}p{color:#9a9aa8;margin:0 0 22px}
input{width:100%;box-sizing:border-box;font-size:17px;padding:14px;border-radius:12px;border:1px solid #2a2a33;background:#17171c;color:#fff}
button{width:100%;margin-top:12px;font-size:17px;font-weight:700;padding:14px;border-radius:12px;border:0;background:#ff2e63;color:#fff}
.e{color:#ff6b8a;margin-top:12px;min-height:20px}</style></head><body>
<form method="post"><img src="/static/icons/icon-180.png" alt=""><h1>Clipper en Vivo</h1><p>Clips virales desde el directo</p>
<input type="hidden" name="username" value="clipper" autocomplete="username">
<input type="password" name="password" placeholder="Contraseña" autocomplete="current-password" autofocus required>
<button>Entrar</button><div class="e">__ERR__</div></form></body></html>"""

_login_fails = {}


@app.route("/login", methods=["GET", "POST"])
def login():
    import hmac
    from flask import session
    nxt = request.args.get("next", "/")
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = "/"
    if not APP_PASSWORD:
        return redirect("/")
    err = ""
    if request.method == "POST":
        ip = request.remote_addr or "?"
        if _login_fails.get(ip, 0) >= 5:
            time.sleep(3)  # frena a quien intente adivinar la clave
        if hmac.compare_digest(request.form.get("password", ""), APP_PASSWORD):
            _login_fails.pop(ip, None)
            session.permanent = True
            session["ok"] = PW_TAG
            return redirect(nxt)
        _login_fails[ip] = _login_fails.get(ip, 0) + 1
        time.sleep(1)
        err = "Contraseña incorrecta"
    return LOGIN_HTML.replace("__ERR__", err)


@app.get("/logout")
def logout():
    from flask import session
    session.clear()
    return redirect("/login")


@app.get("/manifest.webmanifest")
def manifest():
    data = {
        "name": "Clipper en Vivo", "short_name": "Clipper", "lang": "es",
        "description": "Clips virales desde transmisiones en vivo",
        "start_url": "/", "scope": "/", "display": "standalone", "orientation": "portrait",
        "background_color": "#0d0d10", "theme_color": "#0d0d10",
        "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
                  {"src": "/static/icons/maskable-512.png", "sizes": "512x512", "type": "image/png",
                   "purpose": "maskable"}],
    }
    from flask import Response
    return Response(json.dumps(data, ensure_ascii=False), mimetype="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    from flask import Response
    js = """// Clipper: permite instalar la app y recibir avisos; todo se pide siempre al servidor
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
self.addEventListener('push', e => {
  let d = {title: 'Clipper', body: 'Hay novedades', url: '/#clips'};
  try { d = Object.assign(d, e.data.json()); } catch (x) {}
  e.waitUntil(self.registration.showNotification(d.title, {body: d.body, icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png', data: {url: d.url}, tag: 'clipper', renotify: true}));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(clients.matchAll({type: 'window', includeUncontrolled: true}).then(list => {
    for (const c of list) { if ('focus' in c) { c.navigate(url).catch(() => {}); return c.focus(); } }
    return clients.openWindow(url);
  }));
});
"""
    return Response(js, mimetype="application/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/healthz")
def healthz():
    return "ok"


LOGIN_COOKIES = ("SAPISID", "__Secure-3PSID", "__Secure-1PSID", "SID", "LOGIN_INFO", "__Secure-3PAPISID")


def to_netscape(text):
    """Acepta cookies.txt (Netscape) o JSON de Cookie-Editor / EditThisCookie y devuelve Netscape."""
    t = text.strip().lstrip("\ufeff")
    if t.startswith("[") or t.startswith("{"):
        data = json.loads(t)
        if isinstance(data, dict):
            data = data.get("cookies", [])
        lines = ["# Netscape HTTP Cookie File"]
        for c in data:
            dom = c.get("domain", "")
            if not dom:
                continue
            exp = int(float(c.get("expirationDate") or c.get("expires") or 0))
            sub = "TRUE" if dom.startswith(".") else "FALSE"
            lines.append("\t".join([dom, sub, c.get("path", "/"), "TRUE" if c.get("secure") else "FALSE",
                                    str(max(exp, 0)), c.get("name", ""), str(c.get("value", ""))]))
        return "\n".join(lines) + "\n"
    first = t.splitlines()[0] if t else ""
    if "\t" not in t and "=" in first and ";" in t:  # "Header String": a=1; b=2
        lines = ["# Netscape HTTP Cookie File"]
        for part in t.replace("\n", ";").split(";"):
            if "=" in part:
                k, _, v = part.strip().partition("=")
                lines.append("\t".join([".youtube.com", "TRUE", "/", "TRUE", "2147483647", k.strip(), v.strip()]))
        return "\n".join(lines) + "\n"
    if not t.startswith("#"):
        t = "# Netscape HTTP Cookie File\n" + t
    return t.replace("\r\n", "\n") + "\n"


@app.post("/api/cookies")
def api_cookies():
    f = request.files.get("file")
    raw = f.read().decode("utf-8", errors="replace") if f else (request.form.get("text") or
                                                                 (request.get_json(silent=True) or {}).get("text", ""))
    if not raw.strip():
        return jsonify(error="Sube el archivo cookies.txt o pega su contenido"), 400
    try:
        data = to_netscape(raw)
    except (ValueError, TypeError, AttributeError):
        return jsonify(error="No entiendo ese formato. Usa cookies.txt (Netscape) o el JSON de Cookie-Editor."), 400
    yt = [ln for ln in data.splitlines() if "youtube.com" in ln and not ln.startswith("#")]
    if not yt:
        return jsonify(error="Esas cookies no son de youtube.com. Exporta estando en youtube.com."), 400
    names = {ln.split("\t")[5] for ln in yt if len(ln.split("\t")) >= 7}
    COOKIES.write_text(data, encoding="utf-8")
    threading.Thread(target=run_health_check, daemon=True).start()
    logged = any(n in names for n in LOGIN_COOKIES)
    return jsonify(ok=True, count=len(yt), logged=logged,
                   warning=None if logged else "Ojo: no veo la sesión iniciada en esas cookies. Entra a YouTube con tu "
                                                "cuenta secundaria antes de exportarlas.")


def yt_probe(url):
    """-> (ok, mensaje). Prueba si el servidor puede leer el video, probando los tipos de cliente."""
    names = {"": "normal", "tv": "TV", "web_safari": "Safari", "mweb": "móvil"}
    for client in [yt_state["client"]] + [c for c in PLAYER_CLIENTS if c != yt_state["client"]]:
        try:
            p = subprocess.run(ytdlp(client) + ["--simulate", "--no-warnings", "-f", LIVE_FORMAT, "--print", "title", url],
                               capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            continue
        if p.returncode == 0 and p.stdout.strip():
            yt_state["client"] = client
            extra = "" if not client else f" (entrando como cliente {names[client]})"
            return True, "✅ YouTube responde bien" + extra + ": " + p.stdout.strip().splitlines()[0][:100]
        if "connect" in (p.stderr or "").lower() and "unable" in (p.stderr or "").lower():
            break  # sin red: no tiene sentido probar los demás
    return False, clean_error(diagnose(url))


LAST_URL = DATA / "ultimo_url.txt"
yt_health = {"ok": None, "checked": None, "msg": "", "notified": 0, "busy": False}
COOKIE_CHECK_MIN = int(os.environ.get("COOKIE_CHECK_MIN", "60"))


def health_url():
    if rec.url and rec.url.startswith("http"):
        return rec.url
    try:
        return LAST_URL.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def run_health_check(reason="revisión"):
    url = health_url()
    if not url or yt_health["busy"]:
        return
    yt_health["busy"] = True
    try:
        ok, msg = yt_probe(url)
        prev = yt_health["ok"]
        yt_health.update(ok=ok, msg=msg, checked=time.time())
        blocked = (not ok) and ("bloqueando" in msg or "imágenes" in msg or "Falta un motor" in msg)
        if blocked and (prev is not False or time.time() - yt_health["notified"] > 6 * 3600):
            yt_health["notified"] = time.time()
            notify("⚠️ YouTube bloqueó al servidor", "Las cookies vencieron o YouTube pide verificación. Toca para pegar unas nuevas.",
                   "/#cookies")
        if ok and prev is False:
            notify("✅ YouTube funciona otra vez", "El servidor ya puede grabar el directo.", "/#cookies")
    finally:
        yt_health["busy"] = False


def cookie_watch_loop():
    time.sleep(90)
    while True:
        try:
            run_health_check()
        except Exception:  # noqa: BLE001
            yt_health["busy"] = False
        time.sleep(max(10, COOKIE_CHECK_MIN) * 60)


threading.Thread(target=cookie_watch_loop, daemon=True).start()


@app.post("/api/yt-test")
def api_yt_test():
    """Prueba si el servidor puede leer el video de YouTube con las cookies actuales."""
    url = ((request.get_json(silent=True) or {}).get("url") or health_url() or "").strip()
    if not url:
        return jsonify(error="Pega primero el link del directo"), 400
    ok, msg = yt_probe(url)
    yt_health.update(ok=ok, msg=msg, checked=time.time())
    return jsonify(ok=ok, message=msg)


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


# tipos de cliente de YouTube a probar si bloquea ("" = el normal de yt-dlp)
PLAYER_CLIENTS = ["", "tv", "web_safari", "mweb"]
yt_state = {"client": ""}  # el último que funcionó


def ytdlp(client=None):
    cmd = [sys.executable, "-m", "yt_dlp", *js_runtime_args()]
    client = yt_state["client"] if client is None else client
    if client:
        cmd += ["--extractor-args", f"youtube:player_client={client}"]
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


def clean_error(e):
    """Mensaje de error sin tokens ni claves."""
    msg = str(e)
    msg = re.sub(r"(access_token|client_secret|fb_exchange_token|refresh_token|code)=[^&\s'\")]+", r"\1=***", msg)
    msg = re.sub(r"HTTPSConnectionPool\(host='([^']+)'.*", r"No se pudo conectar con \1 (revisa la conexión a internet del servidor).", msg)
    return msg


def run_job(jid, fn, *args):
    def target():
        try:
            fn(jid, *args)
            update_job(jid, status="listo", progress=100)
        except Exception as e:  # noqa: BLE001
            update_job(jid, status="error", error=clean_error(e)[-600:])
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
                # si falla, el siguiente intento entra como otro tipo de cliente de YouTube
                order = [yt_state["client"]] + [c for c in PLAYER_CLIENTS if c != yt_state["client"]]
                client = order[fails % len(order)]
                yt = subprocess.Popen(
                    ytdlp(client) + ["-f", LIVE_FORMAT, "--no-part", "--quiet",
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
            if time.time() - t0 >= 30 and not is_local:
                yt_state["client"] = client  # ese cliente sí funcionó
            fails = fails + 1 if time.time() - t0 < 30 else 0
            if fails >= 4:
                threading.Thread(target=run_health_check, daemon=True).start()
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

    def seg_table(self):
        """[(número, ruta, inicio, duración)] de los segmentos terminados + duración total."""
        table, cum = [], 0.0
        for f in self.segments():
            try:
                d = self.seg_dur(f)
            except FileNotFoundError:
                continue
            table.append((int(f.stem.split("_")[1]), f, cum, d))
            cum += d
        return table, cum

    def live_anchor(self):
        """Punto actual del directo (final del último segmento terminado)."""
        table, _ = self.seg_table()
        if not table:
            raise RuntimeError("El buffer está vacío. Inicia la grabación primero.")
        return table[-1][0], table[-1][3]

    def capture_window(self, num, off, before, after, dest_dir):
        """Copia lo necesario para [ancla - before, ancla + after]. -> (copias, inicio, duración)"""
        with self.lock:
            table, total = self.seg_table()
            idx = next((i for i, r in enumerate(table) if r[0] == num), None)
            if idx is None:
                if table and num > table[-1][0]:
                    raise NeedMore(after)
                raise RuntimeError("Ese momento ya salió del buffer (es más viejo que el tiempo guardado).")
            anchor = table[idx][2] + off
            start, end = max(0.0, anchor - before), anchor + after
            if end > total + 0.05:
                raise NeedMore(end - total)
            chosen = [r for r in table if r[2] + r[3] > start and r[2] < end]
            copies = []
            for r in chosen:
                dst = dest_dir / r[1].name
                link_or_copy(r[1], dst)
                copies.append(dst)
            return copies, start - chosen[0][2], end - start

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


class NeedMore(Exception):
    """Todavía no se ha grabado el final de la ventana pedida."""


def link_or_copy(src, dst):
    try:
        os.link(src, dst)  # instantáneo y sobrevive a la limpieza del buffer
    except OSError:
        shutil.copy2(src, dst)


rec = Recorder()


# =========================== chat del directo de YouTube: mensajes por minuto
CHAT_DIR = DATA / "chat"
CHAT_RENDERERS = {"liveChatTextMessageRenderer": 1, "liveChatPaidMessageRenderer": 3,
                  "liveChatPaidStickerRenderer": 3, "liveChatMembershipItemRenderer": 2}


class ChatWatcher:
    """Descarga el chat del directo con yt-dlp y cuenta mensajes cada 5 segundos (hora real)."""

    def __init__(self):
        self.proc = None
        self.running = False
        self.counts = {}       # cubeta de 5 s -> mensajes (los pagados cuentan más)
        self.state = "apagado"
        self.total = 0
        self.lock = threading.Lock()

    def start(self, url):
        self.stop()
        with self.lock:
            self.counts, self.total = {}, 0
        if "youtube.com" not in url and "youtu.be" not in url:
            self.state = "solo funciona con directos de YouTube"
            return
        shutil.rmtree(CHAT_DIR, ignore_errors=True)
        CHAT_DIR.mkdir(parents=True, exist_ok=True)
        self.running = True
        self.state = "conectando…"
        threading.Thread(target=self._run, args=(url,), daemon=True).start()

    def follow_file(self, path):
        """Para pruebas: sigue un archivo de chat ya existente."""
        self.stop()
        self.running = True
        self.state = "leyendo"
        threading.Thread(target=self._tail, args=([Path(path)],), daemon=True).start()

    def stop(self):
        self.running = False
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:  # noqa: BLE001
                pass
            self.proc = None
        if self.state not in ("solo funciona con directos de YouTube",):
            self.state = "apagado"

    def _run(self, url):
        log = open(CHAT_DIR / "chat.log", "a", encoding="utf-8", errors="replace")
        self.proc = subprocess.Popen(ytdlp() + ["--skip-download", "--write-subs", "--sub-langs", "live_chat",
                                                "--no-warnings", "-o", str(CHAT_DIR / "chat.%(ext)s"), url],
                                     stdout=log, stderr=log)
        tail = threading.Thread(target=self._tail, args=(None,), daemon=True)
        tail.start()
        self.proc.wait()
        if self.running and self.total == 0:
            self.state = "chat no disponible en este directo"

    def _tail(self, files):
        offsets, partial = {}, {}
        while self.running:
            paths = files or sorted(CHAT_DIR.glob("chat*.live_chat.json*"))
            for f in paths:
                try:
                    size = f.stat().st_size
                except OSError:
                    continue
                off = offsets.get(f, 0)
                if size <= off:
                    continue
                with open(f, "rb") as fh:
                    fh.seek(off)
                    data = fh.read()
                offsets[f] = off + len(data)
                text = partial.get(f, "") + data.decode("utf-8", errors="replace")
                lines = text.split("\n")
                partial[f] = lines.pop()
                for ln in lines:
                    self._parse(ln)
            time.sleep(1)

    def _parse(self, line):
        line = line.strip()
        if not line:
            return
        try:
            obj = json.loads(line)
        except ValueError:
            return
        stack, found = [obj], []
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in CHAT_RENDERERS and isinstance(v, dict) and v.get("timestampUsec"):
                        found.append((int(v["timestampUsec"]) / 1e6, CHAT_RENDERERS[k]))
                    elif isinstance(v, (dict, list)):
                        stack.append(v)
            elif isinstance(o, list):
                stack.extend(o)
        if found:
            with self.lock:
                for ts, w in found:
                    b = int(ts // 5)
                    self.counts[b] = self.counts.get(b, 0) + w
                    self.total += 1
                old = int(time.time() // 5) - 3 * 720  # se guardan 3 horas
                for b in [b for b in self.counts if b < old]:
                    del self.counts[b]
            self.state = "en vivo"

    # ---- lecturas
    def has_data(self):
        return self.total > 20

    def rate(self, t0, t1):
        """Mensajes por minuto entre dos horas reales."""
        with self.lock:
            n = sum(c for b, c in self.counts.items() if t0 <= b * 5 < t1)
        return n * 60 / max(5, t1 - t0)

    def baseline(self, t0, t1):
        """Ritmo normal del chat (mediana por tramos de 30 s)."""
        rates = [self.rate(t, t + 30) for t in range(int(t0), int(t1), 30)]
        rates = sorted(r for r in rates) or [0]
        return max(5.0, rates[len(rates) // 2])

    def peaks(self, t0, t1, factor=2.5):
        """Horas donde el chat se dispara (por encima de `factor` veces lo normal)."""
        base = self.baseline(t0, t1)
        out = []
        t = int(t0)
        while t < t1:
            if self.rate(t, t + 5) >= base * factor:  # arranque exacto de la explosión (cubetas de 5 s)
                start = t
                peak = 0.0
                while t < t1 and self.rate(t, t + 5) >= base * factor * 0.6:
                    peak = max(peak, self.rate(t, t + 5) / base)
                    t += 5
                if not out or start - out[-1][0] > 30:
                    out.append((start, peak))
            t += 5
        return out, base

    def summary(self):
        now = time.time()
        return {"state": self.state, "per_min": round(self.rate(now - 75, now - 15)), "total": self.total}


chat = ChatWatcher()


def clip_files(cid):
    return [f for f in CLIPS.glob(f"{cid}*") if f.name.split(".")[0] in (cid, f"{cid}_portada")]


def auto_clean():
    """Borra capturas y borradores viejos, y clips terminados antiguos que no estén guardados con ⭐."""
    cfg = pilot_cfg()
    if not cfg.get("clean", True):
        return 0
    now = time.time()
    metas = []
    for mp in CLIPS.glob("*.json"):
        try:
            metas.append(json.loads(mp.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            pass
    in_use = {(m.get("opts") or {}).get("clip_id") for m in metas if m.get("type") == "borrador"}
    removed = 0
    for m in metas:
        age = now - float(m.get("created") or now)
        t = m.get("type")
        old = ((t in ("captura", "borrador") and age > cfg.get("caps_hours", 24) * 3600 and m["id"] not in in_use) or
               (t in ("final", "portada") and age > cfg.get("clips_days", 7) * 86400 and not m.get("keep")))
        if old:
            for f in clip_files(m["id"]):
                f.unlink(missing_ok=True)
            removed += 1
    return removed


def janitor():
    last_clean = 0
    while True:
        rec.cleanup()
        if time.time() - last_clean > 600:
            last_clean = time.time()
            try:
                auto_clean()
            except Exception:  # noqa: BLE001
                pass
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


def capture_anchor(jid, num, off, before, after, label, auto=False):
    """Captura alrededor de un punto del directo; espera si el final aún no se ha grabado."""
    cid = "cap_" + time.strftime("%H%M%S") + "_" + jid[:4]
    work = TMP / cid
    work.mkdir()
    deadline = time.time() + after + 60
    while True:
        try:
            copies, offset, dur = rec.capture_window(num, off, before, after, work)
            break
        except NeedMore as e:
            if time.time() > deadline or not rec.running:
                raise RuntimeError("El directo no avanzó lo suficiente para completar el clip.") from e
            update_job(jid, label=f"Esperando {int(e.args[0]) + 1}s más del directo…")
            time.sleep(2)
    (work / "list.txt").write_text("".join(f"file '{c.name}'\n" for c in copies), encoding="utf-8")
    out = CLIPS / f"{cid}.mp4"
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", "list.txt", "-ss", f"{offset:.2f}", "-t", f"{dur:.2f}",
                "-c", "copy", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", str(out)],
               cwd=str(work))
    shutil.rmtree(work, ignore_errors=True)
    save_meta(cid, {"id": cid, "type": "captura", "file": out.name, "created": time.time(),
                    "duration": ffprobe_duration(out), "source": rec.url, "auto": auto,
                    "label": label})
    return cid


def job_capture_anchor(jid, num, off, before, after, label):
    update_job(jid, result=capture_anchor(jid, num, off, before, after, label))


SMART_WORDS = ("mentira", "traición", "traicion", "pelea", "respeto", "verdad", "confes", "nominad", "elimin",
               "alofoke", "beso", "celos", "secreto", "jaja", "dique", "embuste", "falso", "cállate", "callate",
               "eso no", "tú eres", "tu eres", "llorando", "perdón", "perdon", "te quiero", "amor")


def smart_rerank(jid, found, src_args, d):
    """Detector inteligente: escucha los mejores candidatos y sube los que tienen palabras gancho o nombres."""
    if not found or not d.get("smart", True) or not _has_whisper():
        return found
    cands = sorted(found, key=lambda m: m["score"], reverse=True)[:8]
    for i, m in enumerate(cands, 1):
        update_job(jid, label=f"🧠 Escuchando momento {i}/{len(cands)}…", progress=30 + i * 8)
        wav = TMP / f"sm_{jid}_{i}.wav"
        try:
            run_ffmpeg([*src_args, "-ss", f"{m['start']:.2f}", "-t", f"{max(3.0, m['end'] - m['start']):.2f}",
                        "-vn", "-ac", "1", "-ar", "16000", str(wav)])
            text = " ".join(w[2] for w in transcribe_words(wav))
        except Exception:  # noqa: BLE001
            continue
        finally:
            wav.unlink(missing_ok=True)
        low = text.lower()
        n_words = len(low.split())
        boost = 4 * sum(1 for w in SMART_WORDS if w in low) + 3 * len(people_in_text(low))
        boost += 2 if n_words >= 20 else (-3 if n_words < 4 else 0)
        m["score"] = round(m["score"] + boost, 1)
        m["text"], m["boost"] = text[:600], boost
    best = max(m["score"] for m in found) or 1
    for m in found:
        m["stars"] = 3 if m["score"] >= best * 0.8 else 2 if m["score"] >= best * 0.5 else 1
    return found


def detect_moments(jid, d):
    """Busca las tomas importantes en el buffer del directo o en una captura. -> (lista, fuente)"""
    before, after = float(d.get("before", 20)), float(d.get("after", 8))
    top = int(d.get("top", 8))
    if d.get("clip_id"):
        meta = json.loads(meta_path(d["clip_id"]).read_text(encoding="utf-8"))
        update_job(jid, progress=20)
        lv = moments.loudness_curve(["-i", str(CLIPS / meta["file"])])
        found = moments.find_moments(lv, top=top, before=before, after=after, total=meta.get("duration"),
                                     min_gap=max(12.0, before), min_score=float(d.get("min_score", 3.0)))
        for m in found:
            m.update(kind="capture", clip_id=d["clip_id"])
        found = smart_rerank(jid, found, ["-i", str(CLIPS / meta["file"])], d)
        return found, meta.get("label")
    minutes = float(d.get("minutes", 10))
    work = TMP / ("mom_" + jid)
    work.mkdir()
    with rec.lock:
        table, total = rec.seg_table()
        if not table:
            raise RuntimeError("El buffer está vacío.")
        rows = [r for r in table if r[2] + r[3] >= total - minutes * 60]
        for r in rows:
            link_or_copy(r[1], work / r[1].name)
    w0 = rows[0][2]
    (work / "list.txt").write_text("".join(f"file '{(work / r[1].name).as_posix()}'\n" for r in rows),
                                   encoding="utf-8")
    update_job(jid, progress=20, label=f"Analizando los últimos {int(minutes)} min…")
    src_args = ["-f", "concat", "-safe", "0", "-i", str(work / "list.txt")]
    lv = moments.loudness_curve(src_args)
    found = moments.find_moments(lv, top=top, before=before, after=after, total=total - w0,
                                 min_gap=max(12.0, before), min_score=float(d.get("min_score", 3.0)))
    if chat.has_data():
        found = chat_boost(found, rows, work, w0, total, before, after, top)
    for m in found:
        absolute = w0 + m["t"]
        row = next((r for r in rows if r[2] <= absolute < r[2] + r[3]), rows[-1])
        m.update(kind="anchor", seg=row[0], off=round(absolute - row[2], 2),
                 ago=round(total - absolute), before=before, after=after)
    try:
        found = smart_rerank(jid, found, src_args, d)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return found, f"últimos {int(minutes)} min"


def chat_boost(found, rows, work, w0, total, before, after, top):
    """Sube los momentos donde el chat se disparó y agrega momentos que solo se ven en el chat."""
    import math
    spans = []  # (inicio en el buffer, duración, hora real del final)
    for r in rows:
        try:
            spans.append((r[2], r[3], (work / r[1].name).stat().st_mtime))
        except OSError:
            pass
    if not spans:
        return found

    def wall_of(abs_t):
        for st, du, end in spans:
            if st <= abs_t <= st + du:
                return end - (st + du - abs_t)
        st, du, end = spans[-1]
        return end - (st + du - abs_t)

    def abs_of(wall):
        for st, du, end in spans:
            if end - du <= wall <= end:
                return st + du - (end - wall)
        return None

    w_start, w_end = wall_of(w0), wall_of(total)
    peaks, _ = chat.peaks(w_start, w_end)
    for wall, ratio in peaks:
        a = abs_of(wall - 4)  # lo que pasó unos segundos antes de que el chat explotara
        if a is None:
            continue
        e = a - w0
        boost = round(min(15.0, 6 * math.log2(max(ratio, 1.01))), 1)
        covering = [m for m in found if m["start"] <= e <= m["end"]]
        if covering:  # una toma ya incluye ese segundo: se le sube el puntaje
            m = min(covering, key=lambda m: abs(m["t"] - e))
            m["score"] = round(m["score"] + boost, 1)
            m["chat"] = round(max(ratio, m.get("chat", 0)), 1)
        else:  # momento que solo se ve en el chat
            found.append({"t": round(e, 1), "start": round(max(0.0, e - before), 1),
                          "end": round(min(total - w0, e + after), 1),
                          "score": round(3 + boost, 1), "chat": round(ratio, 1), "stars": 1})
    found = sorted(found, key=lambda m: m["score"], reverse=True)[:max(top, 1)]
    best = max(m["score"] for m in found) or 1
    for m in found:
        m["stars"] = 3 if m["score"] >= best * 0.8 else 2 if m["score"] >= best * 0.5 else 1
    return found


def job_moments(jid, d):
    found, source = detect_moments(jid, d)
    if not d.get("clip_id"):
        found.sort(key=lambda m: m["ago"], reverse=True)
    update_job(jid, result={"moments": found, "source": source})


def job_auto_clips(jid, d):
    """Botón mágico: busca los N mejores momentos y crea los N clips de una vez."""
    n = max(1, min(10, int(d.get("count", 5))))
    # min_score bajo: si hay pocos picos muy claros, completa con los siguientes mejores
    found, source = detect_moments(jid, dict(d, top=max(n, 10), min_score=0.8))
    if not found:
        raise RuntimeError("No encontré momentos fuertes. Prueba analizar más minutos o espera a que pase algo.")
    best = sorted(found, key=lambda m: m["score"], reverse=True)[:n]
    best.sort(key=lambda m: m.get("ago", 0), reverse=True) if best[0]["kind"] == "anchor" else best.sort(key=lambda m: m["start"])
    settings = {**my_style(), **(d.get("settings") or {})}
    hooks_pool = [h for h in (d.get("hooks") or []) if h.strip()]
    if not d.get("with_hook"):
        settings["hook"] = ""
        settings["cover_first"] = False if not settings.get("cover_text") else settings.get("cover_first")
    ids = []
    for i, m in enumerate(best, 1):
        label = f"Mejor momento {i}/{len(best)}" + (f" · hace {fmt_t(m['ago'])}" if m.get("ago") is not None else "")
        if m["kind"] == "anchor":
            item = {"kind": "anchor", "seg": m["seg"], "off": m["off"], "before": m["before"], "after": m["after"]}
        else:
            item = {"kind": "capture", "clip_id": m["clip_id"], "in": m["start"], "out": m["end"]}
        item["text"] = m.get("text")
        item["label"] = label
        item["hook"] = (hooks_pool[(i - 1) % len(hooks_pool)] if hooks_pool else settings.get("hook", "")) if d.get("with_hook") else ""
        cid = new_job("render", label)
        run_job(cid, job_batch_item, item, dict(settings, _label=label, _part=f"PARTE {i}/{len(best)}", _moment_score=m.get("score")))
        ids.append(cid)
    extra = f" (solo encontré {len(ids)} momentos distintos)" if len(ids) < n else ""
    update_job(jid, label=f"✅ {len(ids)} clip{'s' if len(ids) != 1 else ''} en camino · {source}{extra}", result={"jobs": ids})
    wait_and_notify(ids, "clips automáticos listos")


def job_batch_item(jid, item, settings):
    """Un clip del lote: captura (si viene del directo) + render con la configuración común."""
    opts = dict(settings)
    label = item.get("label") or "Clip"
    if item.get("kind") == "anchor":
        update_job(jid, label=f"{label}: capturando…")
        cid = capture_anchor(jid, int(item["seg"]), float(item["off"]), float(item.get("before", 20)),
                             float(item.get("after", 8)), label, auto=True)
        opts.update(clip_id=cid, **{"in": 0, "out": None})
    else:
        opts.update(clip_id=item["clip_id"], **{"in": item.get("in", 0), "out": item.get("out")})
    if item.get("text"):
        opts["_transcript_hint"] = item["text"]
    if item.get("hook") is not None:
        opts["hook"] = item["hook"]
    update_job(jid, label=f"{label}: renderizando…")
    job_render(jid, opts)


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
_whisper_lock = threading.Lock()


def transcribe_words(audio_path):
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("Para subtítulos instala: pip install -r requirements-subtitulos.txt") from e
    with _whisper_lock:
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


SUB_STYLES = {
    # nombre: (color base, color palabra actual BGR, borde, caja, palabras por línea)
    "amarillo": ("&H00FFFFFF", "&H0000E6FF", True, False, 3),
    "verde": ("&H00FFFFFF", "&H0066FF00", True, False, 3),
    "caja": ("&H00FFFFFF", "&H0000E6FF", False, True, 4),
    "blanco": ("&H00FFFFFF", None, True, False, 4),
}


def build_ass(words, w, h, family, path, style="amarillo", pos="abajo"):
    base, hi, outline, box, per_chunk = SUB_STYLES.get(style, SUB_STYLES["amarillo"])
    vertical = w < h
    size = int(w * (0.095 if vertical else 0.05)) if family == "Anton" else int(w * 0.085 if vertical else h * 0.075)
    if pos == "centro":
        align, margin_v = 5, 0
    elif pos == "arriba":
        align, margin_v = 8, int(h * (0.30 if vertical else 0.08))
    else:
        align, margin_v = 2, int(h * (0.26 if vertical else 0.08))
    border_style = 3 if box else 1
    outl = max(4, size // 10) if outline else max(8, size // 6)
    back = "&H00000000" if box else "&H96000000"
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{family},{size},{base},{base},&H00000000,{back},0,0,0,0,100,100,1,0,{border_style},{outl},{0 if box else 3},{align},70,70,{margin_v},1

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
                if j == i and hi:  # palabra que se está diciendo
                    grow = "" if box else "\\fscx112\\fscy112"
                    back = "" if box else "\\fscx100\\fscy100"
                    parts.append("{\\c" + hi + "&" + grow + "}" + txt + "{\\c" + base + "&" + back + "}")
                else:
                    parts.append(txt)
            lines.append(f"Dialogue: 0,{ass_time(st)},{ass_time(max(nxt, st + 0.05))},Sub,,0,0,0,,{' '.join(parts)}")
    Path(path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


def corner_xy(pos, W, H, ow="w", oh="h", main_w="W", main_h="H"):
    """Expresiones x:y para poner algo en una esquina, respetando la zona de botones de TikTok."""
    m = int(min(W, H) * 0.04)
    bottom = int(H * 0.15) if H > W else m
    top = int(H * 0.05) if H > W else m
    xs = {"izq": f"{m}", "der": f"{main_w}-{ow}-{m}", "centro": f"({main_w}-{ow})/2"}
    ys = {"sup": f"{top}", "inf": f"{main_h}-{oh}-{bottom}"}
    v, _, hz = (pos or "abajo").partition("_")
    if pos in ("abajo", "inf_centro"):
        return xs["centro"], ys["inf"]
    if pos == "arriba":
        return xs["centro"], ys["sup"]
    return xs.get(hz, xs["centro"]), ys.get(v, ys["inf"])


def video_lead(path):
    """Segundos de solo audio antes del primer cuadro de video."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,start_time",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    starts = {}
    for line in out.splitlines():
        kind, _, st = line.partition(",")
        try:
            starts.setdefault(kind, float(st))
        except ValueError:
            pass
    if "video" in starts and "audio" in starts:
        return max(0.0, min(2.0, starts["video"] - starts["audio"]))
    return 0.0


SFX_DIR = BASE / "static" / "sfx"
SOUNDS_DIR = DATA / "sounds"
SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
BUILTIN_SFX = [  # (id, emoji, nombre) - creados con generar_sonidos.py, sin derechos de terceros
    ("boom", "💥", "Boom"), ("whoosh", "💨", "Whoosh"), ("ding", "🔔", "Ding"),
    ("dundun", "😱", "Dun dun duuun"), ("triste", "🎺", "Trompeta triste"), ("bocina", "📣", "Bocina"),
    ("grillos", "🦗", "Grillos"), ("suspenso", "😬", "Suspenso"), ("error", "❌", "Error"),
    ("pop", "🫧", "Pop"), ("boing", "🤪", "Boing"), ("redoble", "🥁", "Redoble"),
    ("flash", "📸", "Flash"), ("glitch", "📺", "Glitch"),
]


def sound_list():
    out = [{"id": i, "emoji": e, "name": n, "url": f"/static/sfx/{i}.mp3", "custom": False}
           for i, e, n in BUILTIN_SFX if (SFX_DIR / f"{i}.mp3").exists()]
    for m in sorted(SOUNDS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime):
        try:
            d = json.loads(m.read_text(encoding="utf-8"))
            if (SOUNDS_DIR / f"{d['id']}.mp3").exists():
                out.append({**d, "url": f"/sounds/{d['id']}.mp3", "custom": True})
        except Exception:  # noqa: BLE001
            pass
    return out


def sound_path(sid):
    if not re.fullmatch(r"[A-Za-z0-9_]+", str(sid or "")):
        return None
    for p in (SFX_DIR / f"{sid}.mp3", SOUNDS_DIR / f"{sid}.mp3"):
        if p.exists():
            return p
    return None


def has_audio(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                          "stream=index", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return bool(out.strip())


def make_cover(src, t, opts, W, H):
    """Portada: fotograma + oscurecido suave + hook grande."""
    from io import BytesIO
    from PIL import Image
    fmt = opts.get("format", "vertical")
    mode = opts.get("cover_mode") or "fill"
    raw = preview_frame(str(src), src.stat().st_mtime, round(float(t), 1), fmt, mode, W, H)
    frame = Image.open(BytesIO(raw)).convert("RGBA") if raw else preview_background(W, H).copy()
    col = Image.new("L", (1, H))
    for y in range(H):  # degradado: más oscuro arriba y abajo para que el texto resalte
        col.putpixel((0, y), int(150 * max(0.0, abs(y / H - 0.5) * 2 - 0.25) / 0.75))
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    shade.putalpha(col.resize((W, H)))
    frame = Image.alpha_composite(frame, shade)
    text = (opts.get("cover_text") or opts.get("hook") or "").strip()
    if text:
        style = opts.get("cover_style") or opts.get("hook_style") or hooks.DEFAULT_STYLE
        kw = hook_kwargs(opts, style, W, H)
        kw["scale"] = kw["scale"] * float(opts.get("cover_size", 125)) / 100
        img = hooks.render_hook(text, style, W, **kw)
        if img:
            frame.alpha_composite(img, (0, hook_y(opts.get("cover_pos", "centro"), W, H, img.height)))
    return frame.convert("RGB")


def job_render(jid, opts):
    src_meta = json.loads(meta_path(opts["clip_id"]).read_text(encoding="utf-8"))
    src = CLIPS / src_meta["file"]
    t_in = float(opts.get("in") or 0)
    t_out = float(opts.get("out") or src_meta.get("duration") or ffprobe_duration(src))
    t_in = max(t_in, video_lead(src))  # las capturas pueden empezar con ~0.5 s de solo audio
    dur = t_out - t_in
    if dur <= 0.3:
        raise RuntimeError("La salida debe ser mayor que la entrada.")
    fmt = opts.get("format", "vertical")
    W, H = FORMATS.get(fmt, FORMATS["vertical"])
    draft = bool(opts.get("draft"))
    if draft:  # borrador: mitad de resolución, para revisar rápido antes del final
        W, H = W // 2, H // 2
    mode = opts.get("mode", "blur")  # blur = fondo desenfocado, fill = recorte a pantalla completa
    pos = min(1.0, max(0.0, float(opts.get("pos", 50)) / 100))
    zoom = min(2.0, max(1.0, float(opts.get("zoom", 100)) / 100))

    rid = "clip_" + time.strftime("%H%M%S") + "_" + jid[:4]
    work = TMP / rid
    work.mkdir()

    font, family = find_font()
    fontfile = None
    if font:
        shutil.copy(font, work / ("font" + font.suffix.lower()))
        fontfile = "font" + font.suffix.lower()
    anton = BASE / "fonts" / "Anton-Regular.ttf"
    if anton.exists():
        shutil.copy(anton, work / anton.name)
        sub_family = "Anton"
    else:
        sub_family = family

    inputs = []

    n_inputs = [1]

    def add_input(path, pre=()):
        inputs.extend([*pre, "-i", str(path)])
        n_inputs[0] += 1
        return n_inputs[0] - 1  # 0 es el video

    # ---- video base
    if fmt == "horizontal":
        base = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1[v0]")
    elif mode == "smart" and smartcrop.available():  # encuadre inteligente: sigue las caras
        update_job(jid, label=(opts.get("_label") or "Clip") + " · 🎯 buscando caras…")
        try:
            sc = smartcrop.smart_crop_filter(src, t_in, dur, W, H, zoom)
        except Exception:  # noqa: BLE001
            sc = None
        base = sc[0] if sc else (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                                 f"crop={W}:{H},setsar=1[v0]")
    elif mode in ("fill", "smart"):
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

    def add(filter_str, extra=None):
        nonlocal last, n
        n += 1
        src_lbl = f"[{last}]" + (f"[{extra}]" if extra else "")
        chain.append(f"{src_lbl}{filter_str}[v{n}]")
        last = f"v{n}"

    # ---- subtítulos automáticos (van debajo del hook y de la marca)
    if opts.get("subs") and not draft:
        update_job(jid, label="Transcribiendo audio…", progress=3)
        wav = work / "audio.wav"
        run_ffmpeg(["-ss", f"{t_in:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
                    "-vn", "-ac", "1", "-ar", "16000", str(wav)])
        words = transcribe_words(wav)
        opts["_transcript"] = " ".join(w[2] for w in words)
        if words:
            build_ass(words, W, H, sub_family, work / "subs.ass",
                      style=opts.get("subs_style", "amarillo"), pos=opts.get("subs_pos", "abajo"))
            add("subtitles=subs.ass:fontsdir=.")

    # ---- efectos de sonido del clip (+ uno al empezar, útil en lotes)
    sfx_items = []
    for it in (opts.get("sfx") or []):
        try:
            ts = float(it.get("t", 0))
        except (TypeError, ValueError):
            continue
        p = sound_path(it.get("id"))
        if p and t_in - 0.05 <= ts < t_out:
            sfx_items.append((p, max(0.0, ts - t_in), float(it.get("vol", 100)) / 100, bool(it.get("zoom"))))
    intro = sound_path(opts.get("sfx_intro"))
    if intro:
        sfx_items.append((intro, 0.0, float(opts.get("sfx_intro_vol", 100)) / 100, False))
    zooms = [t for _, t, _, z in sfx_items if z]
    if zooms:  # zoom de impacto: acerca la imagen 0.35 s al sonar el efecto
        expr = "+".join(f"between(t,{z:.2f},{z + 0.35:.2f})" for z in zooms)
        add(f"scale=w='{W}*(1+0.18*min(1,{expr}))':h=-2:eval=frame,crop={W}:{H},setsar=1")

    # ---- hook (imagen PNG con el estilo elegido, ver hooks.py)
    hook = (opts.get("hook") or "").strip()
    if hook:
        img = hooks.render_hook(hook, opts.get("hook_style") or hooks.DEFAULT_STYLE, W,
                                **hook_kwargs(opts, opts.get("hook_style") or "", W, H))
        if img:
            img.save(work / "hook.png")
            k = add_input(work / "hook.png")
            y = hook_y(opts.get("hook_pos", "arriba"), W, H, img.height)
            add(f"overlay=0:{y}:eof_action=repeat", f"{k}:v")

    # ---- marca de agua: logo
    if opts.get("logo") and LOGO.exists():
        lw = int(W * min(40, max(5, float(opts.get("logo_size", 16)))) / 100) // 2 * 2
        op = min(1.0, max(0.1, float(opts.get("logo_op", 90)) / 100))
        k = add_input(LOGO)
        x, y = corner_xy(opts.get("logo_pos", "sup_der"), W, H)
        chain.append(f"[{k}:v]scale={lw}:-1,format=rgba,colorchannelmixer=aa={op:.2f}[lg]")
        add(f"overlay={x}:{y}:eof_action=repeat", "lg")

    # ---- marca de agua: texto / @usuario
    wm = (opts.get("watermark") or "").strip()
    if wm:
        (work / "wm.txt").write_text(wm, encoding="utf-8")
        fs = int(min(W, H) * 0.042)
        op = min(1.0, max(0.1, float(opts.get("wm_op", 85)) / 100))
        x, y = corner_xy(opts.get("wm_pos", "abajo"), W, H, "text_w", "text_h", "w", "h")
        if opts.get("wm_mode") == "movil":  # anti-robo: salta de esquina cada 7 s
            c = [corner_xy(p, W, H, "text_w", "text_h", "w", "h") for p in ("inf_der", "sup_izq", "inf_izq", "sup_der")]
            if H > W:  # en vertical, las posiciones de arriba van entre el hook y el video (libres de etiquetas)
                mid = int(H * 0.30)
                c[1] = (c[1][0], str(mid))
                c[3] = (c[3][0], str(mid))
            k = "mod(floor(t/7),4)"
            x = "'" + f"if(eq({k},0),{c[0][0]},if(eq({k},1),{c[1][0]},if(eq({k},2),{c[2][0]},{c[3][0]})))" + "'"
            y = "'" + f"if(eq({k},0),{c[0][1]},if(eq({k},1),{c[1][1]},if(eq({k},2),{c[2][1]},{c[3][1]})))" + "'"
        font_opt = f"fontfile={fontfile}:" if fontfile else ""
        add(f"drawtext={font_opt}textfile=wm.txt:fontsize={fs}:fontcolor=white@{op:.2f}:"
            f"borderw=3:bordercolor=black@{op * 0.7:.2f}:x={x}:y={y}")

    # ---- texto de contexto (pequeño, no tapa la acción) y "Parte N/M" en lotes
    def corner_png(img, name, pos):
        img.save(work / name)
        k = add_input(work / name)
        m = int(W * 0.035)
        top = int(H * 0.028) if H > W else m
        if pos == "sup_der":
            xy = (f"W-w-{m}", f"{top}")
        elif pos == "inf":
            xy = ("(W-w)/2", f"H-h-{int(H * 0.17) if H > W else m * 2}")
        else:
            xy = (f"{m}", f"{top}")
        add(f"overlay={xy[0]}:{xy[1]}:eof_action=repeat", f"{k}:v")

    if opts.get("ctx_on") and (opts.get("ctx_text") or "").strip():
        img = hooks.render_ctx(opts["ctx_text"], W, 1 if H > W else 0.8)
        if img:
            corner_png(img, "ctx.png", opts.get("ctx_pos", "sup_izq"))
    if opts.get("_part") and opts.get("ctx_parts"):
        img = hooks.render_ctx(opts["_part"], W, 1 if H > W else 0.8)
        if img:
            corner_png(img, "part.png", "sup_der" if opts.get("ctx_pos", "sup_izq") != "sup_der" else "sup_izq")

    # ---- mezcla: audio del clip + efectos en su segundo
    audio_map = "0:a:0?"
    audio_lbl = "0:a"
    src_audio = has_audio(src)
    if sfx_items:
        if src_audio:
            chain.append("[0:a]aformat=channel_layouts=stereo,aresample=48000[am0]")
        else:
            chain.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{dur:.3f}[am0]")
        labels = ["[am0]"]
        for i, (p, t, vol, _) in enumerate(sfx_items[:20]):
            k = add_input(p)
            ms = int(t * 1000)
            chain.append(f"[{k}:a]aformat=channel_layouts=stereo,aresample=48000,volume={min(2.0, max(0.0, vol)):.2f},"
                         f"adelay={ms}:all=1[sx{i}]")
            labels.append(f"[sx{i}]")
        chain.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=first:dropout_transition=0,"
                     "alimiter=limit=0.95[amx]")
        audio_lbl, audio_map, src_audio = "amx", "[amx]", True

    # ---- portada como primer cuadro (0.35 s antes del clip; TikTok usa el primer cuadro de portada)
    cover_file = None
    total = dur
    if opts.get("cover_first") and not draft:
        ct = float(opts.get("cover_t") if opts.get("cover_t") not in (None, "") else t_in + 0.5)
        cover = make_cover(src, ct, opts, W, H)
        cover.save(work / "cover.png")
        cover_file = CLIPS / f"{rid}_portada.jpg"
        cover.save(cover_file, quality=92)
        cl = 0.35
        k = add_input(work / "cover.png", ("-loop", "1", "-framerate", "30", "-t", str(cl)))
        chain.append(f"[{k}:v]scale={W}:{H},setsar=1,fps=30,format=yuv420p[cv]")
        chain.append(f"[{last}]fps=30,format=yuv420p[mv]")
        if src_audio:
            chain.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{cl}[sil]")
            chain.append(f"[{audio_lbl}]aresample=48000,aformat=channel_layouts=stereo[ma]")
            chain.append("[cv][sil][mv][ma]concat=n=2:v=1:a=1[vout][aout]")
            audio_map = "[aout]"
        else:
            chain.append("[cv][mv]concat=n=2:v=1:a=0[vout]")
        last = "vout"
        total = dur + cl

    fast = opts.get("speed", "rapido") != "calidad"
    out = CLIPS / f"{rid}.mp4"
    filt = ";".join(chain)
    cmd = ["-ss", f"{t_in:.3f}", "-t", f"{dur:.3f}", "-i", str(src), *inputs,
           "-filter_complex", filt, "-map", f"[{last}]", "-map", audio_map,
           "-c:v", "libx264", "-preset", "ultrafast" if draft else "superfast" if fast else "veryfast",
           "-crf", "30" if draft else "22" if fast else "19",
           "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}",
           "-movflags", "+faststart", str(out)]
    update_job(jid, label=(opts.get("_label") or "Renderizando clip") + " · en cola…")
    with RENDER_SEM:
        update_job(jid, label=(opts.get("_label") or "Renderizando clip") + "…")
        run_ffmpeg(cmd, jid=jid, total=total, cwd=str(work))
    shutil.rmtree(work, ignore_errors=True)
    meta_out = {"duration": dur, "format": fmt, "hook": hook, "transcript": opts.get("_transcript") or opts.get("_transcript_hint"),
                "subs": bool(opts.get("subs")), "cover": bool(cover_file),
                "watermark": bool((opts.get("watermark") or "").strip() or opts.get("logo")),
                "moment_score": opts.get("_moment_score")}
    try:
        viral = viral_score(out, meta_out)
    except Exception:  # noqa: BLE001
        viral = None
    keep_opts = {k: v for k, v in opts.items() if not k.startswith("_") or k in ("_part", "_moment_score", "_label")}
    keep_opts.pop("draft", None)
    save_meta(rid, {"id": rid, "type": "borrador" if draft else "final", "file": out.name, "created": time.time(),
                    "viral": viral, "opts": keep_opts if draft else None, "auto": bool(opts.get("_auto")),
                    "duration": dur, "format": fmt, "hook": hook, "from": opts["clip_id"],
                    "cover": cover_file.name if cover_file else None, "cat": opts.get("hook_cat"),
                    "transcript": opts.get("_transcript"),
                    "people": sorted(set((opts.get("people") or []) + people_in_text(opts.get("_transcript") or opts.get("_transcript_hint")))),
                    "label": hook.split("|")[0].replace("*", "").strip()[:60] or src_meta.get("label") or f"Clip {fmt} {dur:.0f}s"})
    update_job(jid, result=rid)
    return rid


# ---- porcentaje viral: estimación con señales del clip (no es una garantía)
VIRAL_WORDS = ("mentira", "traición", "traicion", "pelea", "lío", "lio", "verdad", "confes", "nominad",
               "elimin", "alofoke", "beso", "celos", "grit", "falta de respeto", "respeto", "llor", "secreto")


def _clamp(x):
    return int(max(0, min(100, round(x))))


BASE_WEIGHTS = {"momento": .30, "arranque": .20, "duracion": .15, "hook": .15, "palabras": .10, "formato": .10}
LEARN = DATA / "aprendizaje.json"


def current_weights():
    try:
        w = json.loads(LEARN.read_text(encoding="utf-8")).get("weights")
        if w and set(w) == set(BASE_WEIGHTS):
            return w
    except Exception:  # noqa: BLE001
        pass
    return dict(BASE_WEIGHTS)


def weighted_score(parts, weights=None):
    w = weights or current_weights()
    return _clamp(sum(parts.get(k, 0) * v for k, v in w.items()))


def learn_from_views():
    """Ajusta los pesos con las vistas reales: más peso a lo que se relaciona con más vistas en tu página."""
    import math
    rows = []
    for mp in CLIPS.glob("clip_*.json"):
        try:
            d = json.loads(mp.read_text(encoding="utf-8"))
            v = (d.get("stats") or {}).get("views")
            if v is not None and (d.get("viral") or {}).get("parts"):
                rows.append((d["viral"]["parts"], math.log10(float(v) + 1)))
        except Exception:  # noqa: BLE001
            pass
    out = {"n": len(rows), "weights": dict(BASE_WEIGHTS), "corr": {}}
    if len(rows) >= 5:
        ys = [y for _, y in rows]
        my = sum(ys) / len(ys)
        sy = math.sqrt(sum((y - my) ** 2 for y in ys)) or 1
        raw = {}
        for k, base in BASE_WEIGHTS.items():
            xs = [p.get(k, 0) for p, _ in rows]
            mx = sum(xs) / len(xs)
            sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
            corr = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) if sx else 0.0
            out["corr"][k] = round(corr, 2)
            raw[k] = base * max(0.2, 1 + corr)
        tot = sum(raw.values())
        trust = min(1.0, len(rows) / 15)  # con pocos clips se mezcla con los pesos normales
        out["weights"] = {k: round(BASE_WEIGHTS[k] * (1 - trust) + raw[k] / tot * trust, 3) for k in BASE_WEIGHTS}
    LEARN.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def viral_score(path, m):
    lv = moments.loudness_curve(["-i", str(path)])
    voiced = [x for x in lv if x > moments.FLOOR + 5] or [moments.FLOOR]
    med = sorted(voiced)[len(voiced) // 2]
    peak = max(voiced)
    # 1. intensidad del momento (pico sobre lo normal del clip, o el puntaje del detector)
    intensity = _clamp((peak - med) / 14 * 100)
    if m.get("moment_score"):
        intensity = max(intensity, _clamp(float(m["moment_score"]) / 25 * 100))
    # 2. arranque: energía en los primeros 3 s
    first = [x for x in lv[:int(3 / moments.STEP)] if x > moments.FLOOR + 5] or [moments.FLOOR]
    start = _clamp((max(first) - med + 6) / 14 * 100)
    # 3. duración ideal 15-45 s
    d = float(m.get("duration") or 0)
    duration = 100 if 15 <= d <= 45 else 75 if 10 <= d < 15 or 45 < d <= 60 else 50 if 60 < d <= 90 or 6 <= d < 10 else 25
    # 4. hook
    h = (m.get("hook") or "").strip()
    hook = 0 if not h else _clamp(65 + (15 if "*" in h else 0) + (20 if len(h.replace("*", "")) <= 45 else 5))
    # 5. palabras gancho (solo si hay transcripción)
    tr = (m.get("transcript") or "").lower()
    if tr:
        hits = sum(1 for w in VIRAL_WORDS if w in tr) + len(people_in_text(tr))
        words = _clamp(35 + hits * 22)
    else:
        words = 50
    # 6. formato
    fmt = _clamp((40 if m.get("format") == "vertical" else 15) + (30 if m.get("subs") else 0) +
                 (15 if m.get("cover") else 0) + (15 if m.get("watermark") else 0))
    parts = {"momento": intensity, "arranque": start, "duracion": duration, "hook": hook, "palabras": words, "formato": fmt}
    score = weighted_score(parts)
    tips = []
    if intensity < 45:
        tips.append("Momento con poca energía: prueba otra toma más fuerte.")
    if start < 45:
        tips.append("Empieza el clip más cerca de la acción (los primeros 3 s retienen).")
    if d > 45:
        tips.append(f"Acórtalo a menos de 45 s (ahora dura {int(d)} s).")
    elif d < 10:
        tips.append("Es muy corto: dale unos segundos de contexto.")
    if not h:
        tips.append("Ponle un hook.")
    elif "*" not in h:
        tips.append("Resalta una palabra del hook con *asteriscos*.")
    if not m.get("subs"):
        tips.append("Activa los subtítulos.")
    if m.get("format") != "vertical":
        tips.append("Usa formato vertical 9:16.")
    level = "alto" if score >= 70 else "medio" if score >= 45 else "bajo"
    return {"score": score, "level": level, "parts": parts, "tips": tips[:3]}


def backfill_viral():
    """Calcula el porcentaje de los clips hechos antes de esta función."""
    for mp in CLIPS.glob("clip_*.json"):
        try:
            d = json.loads(mp.read_text(encoding="utf-8"))
            if d.get("type") != "final" or d.get("viral") or not (CLIPS / d["file"]).exists():
                continue
            d["viral"] = viral_score(CLIPS / d["file"], {**d, "watermark": True})
            save_meta(d["id"], d)
        except Exception:  # noqa: BLE001
            pass


threading.Thread(target=backfill_viral, daemon=True).start()


def job_cover(jid, opts):
    meta = json.loads(meta_path(opts["clip_id"]).read_text(encoding="utf-8"))
    src = CLIPS / meta["file"]
    W, H = FORMATS.get(opts.get("format", "vertical"), FORMATS["vertical"])
    img = make_cover(src, float(opts.get("t", 0)), opts, W, H)
    pid = "portada_" + time.strftime("%H%M%S") + "_" + jid[:4]
    img.save(CLIPS / f"{pid}.jpg", quality=92)
    text = (opts.get("cover_text") or opts.get("hook") or "").replace("*", "")
    save_meta(pid, {"id": pid, "type": "portada", "file": f"{pid}.jpg", "created": time.time(),
                    "label": "Portada · " + (text[:40] or meta.get("label", ""))})
    update_job(jid, result=pid)


def job_publish(jid, target, clip_id, caption, tiktok_mode, base):
    meta = json.loads(meta_path(clip_id).read_text(encoding="utf-8"))
    path = CLIPS / meta["file"]
    prog = lambda p: update_job(jid, progress=p)  # noqa: E731
    if target == "facebook":
        msg = social.publish_facebook(path, caption, prog)
    elif target == "instagram":
        if not base or "127.0.0.1" in base or "localhost" in base:
            raise RuntimeError("Instagram necesita descargar el video desde internet: usa la app publicada "
                               "(Railway/Render) o define PUBLIC_URL.")
        url = base + "pub/" + social.public_link(path) + "/" + path.name
        cover = meta.get("cover")
        cover_url = (base + "pub/" + social.public_link(CLIPS / cover) + "/" + cover) if cover and (CLIPS / cover).exists() else None
        msg = social.publish_instagram(url, caption, cover_url, prog)
    elif target == "tiktok":
        msg = social.publish_tiktok(path, caption, tiktok_mode, prog)
    else:
        raise RuntimeError("Red desconocida")
    update_job(jid, label=msg)


def hook_kwargs(o, style, W, H, prefix="hook_"):
    """parámetros de tamaño y de plantilla, desde el JSON del render o la URL de la vista previa."""
    size = float(o.get(prefix + "size", o.get("size", 100)) or 100) / 100
    kw = {"scale": size * (1 if (H > W or style.startswith("t:")) else 0.75), "height": H}
    if style.startswith("x:"):  # formas de texto: etiqueta/nombre y @usuario de la publicación
        v = o.get("tpl_badge")
        if v is not None and v != "__default__":
            kw["badge"] = str(v)
        if o.get("tpl_accent") and re.fullmatch(r"#[0-9A-Fa-f]{6}", str(o.get("tpl_accent"))):
            kw["accent"] = o["tpl_accent"]
        wm = (o.get("watermark") or "").strip()
        kw["handle"] = wm if wm.startswith("@") else None
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


def hook_y(pos, W, H, h):
    if pos == "centro":
        return max(0, (H - h) // 2)
    if pos == "abajo":
        return max(0, int(H * 0.66) - h // 2)
    return int(H * 0.08) if H > W else int(H * 0.03)


def preview_vf(fmt, mode, W, H):
    blur = max(2, int(25 * W / 1080))
    if fmt == "horizontal":
        return f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2"
    if mode in ("fill", "smart"):
        return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    return (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur={blur}:3,eq=brightness=-0.08[bg];[b]scale={W}:-2[fg];[bg][fg]overlay=0:(H-h)/2")


@lru_cache(maxsize=16)
def preview_background(W, H):
    """Fondo de ejemplo para la vista previa cuando no hay captura."""
    from PIL import Image, ImageDraw
    bg = Image.new("RGB", (W, H), "#1b1410")
    d = ImageDraw.Draw(bg)
    for i in range(H):
        t = i / H
        d.line([(0, i), (W, i)], fill=(int(60 + 60 * t), int(40 + 25 * t), int(30 + 10 * t)))
    vh = W * 9 // 16
    d.rectangle((0, (H - vh) // 2, W, (H + vh) // 2), fill="#2b2b33")
    return bg.convert("RGBA")


@lru_cache(maxsize=48)
def preview_frame(src, mtime, t, fmt, mode, W, H):
    """Fotograma real ya encuadrado, guardado en memoria (no se repite ffmpeg en cada letra)."""
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.1f}", "-i", src,
                          "-frames:v", "1", "-vf", preview_vf(fmt, mode, W, H),
                          "-f", "image2pipe", "-vcodec", "png", "-"],
                         capture_output=True, timeout=15).stdout
    return raw or None


@lru_cache(maxsize=256)
def preview_jpeg(params):
    """Dibuja la vista previa a tamaño chico directamente (rápido) y devuelve el JPEG."""
    from io import BytesIO
    from PIL import Image
    a = dict(params)
    fmt = a.get("format", "vertical")
    W0, H0 = FORMATS.get(fmt, FORMATS["vertical"])
    W = max(120, min(540, int(a.get("w", 360) or 360)))
    H = int(H0 * W / W0)
    frame = None
    cid = a.get("clip_id", "")
    if re.fullmatch(r"[A-Za-z0-9_]+", cid) and meta_path(cid).exists():
        src = CLIPS / json.loads(meta_path(cid).read_text(encoding="utf-8"))["file"]
        t = round(float(a.get("t", 0) or 0) * 2) / 2
        try:
            raw = preview_frame(str(src), src.stat().st_mtime, t, fmt, a.get("mode", "blur"), W, H)
            frame = Image.open(BytesIO(raw)).convert("RGBA") if raw else None
        except Exception:  # noqa: BLE001
            frame = None
    if frame is None:
        frame = preview_background(W, H).copy()
    style = a.get("style", hooks.DEFAULT_STYLE)
    text = a.get("text", "").strip()
    if not text and style.startswith("x:"):  # ejemplo de cada forma de texto
        text = {"x:encuesta": "¿QUIÉN TIENE LA *RAZÓN*? | ELLA | ÉL"}.get(style, "SE ARMÓ EL *LÍO* EN LA CASA 😱")
    elif not text and not style.startswith("t:"):
        text = "ESCRIBE TU *HOOK* AQUÍ 🔥"   # las plantillas usan su propio texto de ejemplo
    img = hooks.render_hook(text, style, W, **hook_kwargs(a, style, W, H, prefix=""))
    if img:
        y = hook_y(a.get("pos", "arriba"), W, H, img.height)
        frame.alpha_composite(img, (0, y))
        if a.get("crop") == "1":  # miniatura: solo la zona del hook
            m = int(W * 0.03)
            frame = frame.crop((0, max(0, y - m), W, min(H, y + img.height + m)))
    buf = BytesIO()
    frame.convert("RGB").save(buf, "JPEG", quality=85)
    return buf.getvalue()


@app.get("/api/hook-preview")
def api_hook_preview():
    from flask import Response
    params = tuple(sorted(request.args.items()))
    data = preview_jpeg(params)
    # las miniaturas (sin texto ni captura) no cambian: el navegador las guarda
    static = request.args.get("crop") == "1" and not request.args.get("text")
    return Response(data, mimetype="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400" if static else "no-store"})


@app.get("/api/sounds")
def api_sounds():
    return jsonify(sound_list())


@app.post("/api/sounds")
def api_sounds_upload():
    f = request.files.get("file")
    if not f:
        return jsonify(error="Elige un archivo de audio (mp3, m4a, wav…)"), 400
    sid = "s" + uuid.uuid4().hex[:8]
    raw = TMP / f"up_{sid}"
    f.save(raw)
    try:  # a mp3, máximo 15 s, volumen igualado al de la biblioteca
        run_ffmpeg(["-i", str(raw), "-vn", "-t", "15", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-ac", "2", "-ar", "44100", "-b:a", "160k", str(SOUNDS_DIR / f"{sid}.mp3")])
    except RuntimeError:
        return jsonify(error="No pude leer ese audio. Prueba con mp3, m4a o wav."), 400
    finally:
        raw.unlink(missing_ok=True)
    name = (request.form.get("name") or Path(f.filename or "Mi sonido").stem)[:30]
    (SOUNDS_DIR / f"{sid}.json").write_text(json.dumps({"id": sid, "name": name, "emoji": "🎵"},
                                                       ensure_ascii=False), encoding="utf-8")
    return jsonify(ok=True, id=sid)


@app.delete("/api/sounds/<sid>")
def api_sounds_delete(sid):
    if not re.fullmatch(r"s[0-9a-f]{8}", sid):
        return jsonify(error="Solo se pueden borrar los sonidos que subiste"), 400
    for ext in ("mp3", "json"):
        (SOUNDS_DIR / f"{sid}.{ext}").unlink(missing_ok=True)
    return jsonify(ok=True)


@app.get("/sounds/<path:name>")
def custom_sound(name):
    return send_from_directory(SOUNDS_DIR, name)


@app.get("/api/hook-styles")
def api_hook_styles():
    import templates
    import textstyles
    return jsonify(simple=hooks.style_list(), templates=templates.template_list(), forms=textstyles.form_list())


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
    if url.startswith("http"):
        LAST_URL.write_text(url, encoding="utf-8")
    chat.start(url)
    return jsonify(ok=True)


@app.post("/api/buffer/stop")
def api_stop():
    rec.stop()
    chat.stop()
    return jsonify(ok=True)


@app.post("/api/capture")
def api_capture():
    d = request.json or {}
    if d.get("anchor"):
        a = d["anchor"]
        jid = new_job("captura", "Capturando " + (a.get("label") or "momento"))
        run_job(jid, job_capture_anchor, int(a["seg"]), float(a["off"]), float(a.get("before", 20)),
                float(a.get("after", 6)), a.get("label") or "Momento")
        return jsonify(job=jid)
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


# ---- marcadores (tecla M) y tomas importantes
@app.post("/api/marker")
def api_marker():
    try:
        num, off = rec.live_anchor()
    except RuntimeError as e:
        return jsonify(error=str(e)), 400
    m = {"id": uuid.uuid4().hex[:6], "seg": num, "off": off, "created": time.time(),
         "label": (request.json or {}).get("label") or "Momento " + time.strftime("%I:%M:%S %p")}
    with markers_lock:
        markers.insert(0, m)
        del markers[60:]
    return jsonify(m)


@app.delete("/api/marker/<mid>")
def api_marker_delete(mid):
    with markers_lock:
        markers[:] = [m for m in markers if m["id"] != mid]
    return jsonify(ok=True)


@app.post("/api/marker/<mid>/capture")
def api_marker_capture(mid):
    d = request.json or {}
    m = next((x for x in markers if x["id"] == mid), None)
    if not m:
        return jsonify(error="Marcador no encontrado"), 404
    jid = new_job("captura", "Capturando " + m["label"])
    run_job(jid, job_capture_anchor, m["seg"], m["off"], float(d.get("before", 25)),
            float(d.get("after", 5)), m["label"])
    return jsonify(job=jid)


@app.post("/api/moments")
def api_moments():
    d = request.json or {}
    if not d.get("clip_id") and not rec.segments():
        return jsonify(error="No hay nada grabado todavía."), 400
    jid = new_job("momentos", "Buscando tomas importantes…")
    run_job(jid, job_moments, d)
    return jsonify(job=jid)


STYLE = DATA / "estilo.json"
DEFAULT_STYLE = {
    "watermark": "@alofokeclips03", "wm_pos": "abajo", "wm_op": 80, "wm_mode": "fijo",
    "ctx_on": True, "ctx_text": "● EN VIVO · LA CASA DE ALOFOKE 3", "ctx_pos": "sup_izq", "ctx_parts": False,
    "format": "vertical", "mode": "blur", "hook_style": "t:viral", "hook_pos": "arriba", "hook_size": 100,
    "speed": "rapido",
}


def my_style():
    try:
        return {**DEFAULT_STYLE, **json.loads(STYLE.read_text(encoding="utf-8"))}
    except Exception:  # noqa: BLE001
        return dict(DEFAULT_STYLE)


@app.get("/api/style")
def api_style():
    return jsonify(my_style())


@app.post("/api/style")
def api_style_save():
    d = request.json or {}
    keep = {k: v for k, v in d.items() if not k.startswith("_") and k not in ("clip_id", "in", "out", "hook", "sfx", "people", "cover_t")}
    STYLE.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    return jsonify(my_style())


# ================= avisos en el iPhone (Web Push; iOS 16.4+ con la app instalada)
PUSH_SUBS = DATA / "push.json"
VAPID_PEM = DATA / "vapid_private.pem"
_push_lock = threading.Lock()


def push_available():
    try:
        import pywebpush  # noqa: F401
        return True
    except ImportError:
        return False


def vapid():
    from py_vapid import Vapid02
    if not VAPID_PEM.exists():
        v = Vapid02()
        v.generate_keys()
        v.save_key(str(VAPID_PEM))
        try:
            os.chmod(VAPID_PEM, 0o600)
        except OSError:
            pass
    return Vapid02.from_file(str(VAPID_PEM))


def vapid_public():
    import base64
    from cryptography.hazmat.primitives import serialization
    raw = vapid().public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def push_subs():
    try:
        return json.loads(PUSH_SUBS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def notify(title, body, url="/#clips"):
    """Manda un aviso a todos los teléfonos suscritos (en segundo plano)."""
    if not push_available():
        return

    def send():
        from pywebpush import WebPushException, webpush
        v = vapid()
        sub_claim = os.environ.get("PUBLIC_URL", "").strip() or "mailto:avisos@clipper.app"
        payload = json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False)
        with _push_lock:
            subs = push_subs()
            keep = []
            for sub in subs:
                try:
                    webpush(sub, payload, vapid_private_key=v, vapid_claims={"sub": sub_claim}, ttl=3600, timeout=15)
                    keep.append(sub)
                except WebPushException as e:
                    code = getattr(e.response, "status_code", None)
                    if code not in (404, 410):  # 404/410 = el teléfono ya no acepta avisos
                        keep.append(sub)
                except Exception:  # noqa: BLE001
                    keep.append(sub)
            if len(keep) != len(subs):
                PUSH_SUBS.write_text(json.dumps(keep), encoding="utf-8")
    threading.Thread(target=send, daemon=True).start()


@app.get("/api/push/key")
def api_push_key():
    if not push_available():
        return jsonify(error="Los avisos no están instalados en el servidor (pywebpush)."), 400
    return jsonify(key=vapid_public())


@app.post("/api/push/subscribe")
def api_push_subscribe():
    sub = (request.json or {}).get("subscription") or {}
    if not str(sub.get("endpoint", "")).startswith("https://") or not (sub.get("keys") or {}).get("p256dh"):
        return jsonify(error="Suscripción inválida"), 400
    with _push_lock:
        subs = [x for x in push_subs() if x.get("endpoint") != sub["endpoint"]] + [sub]
        PUSH_SUBS.write_text(json.dumps(subs[-20:]), encoding="utf-8")
    return jsonify(ok=True, count=len(subs))


@app.post("/api/push/test")
def api_push_test():
    if not push_subs():
        return jsonify(error="Ningún teléfono tiene los avisos activados todavía."), 400
    notify("✂️ Clipper", "¡Los avisos funcionan! Te avisaré cuando haya clips nuevos.", "/#clips")
    return jsonify(ok=True)


# ================= piloto automático: vigila el directo y crea clips solo
PILOT = DATA / "piloto.json"
PILOT_DEFAULT = {"enabled": False, "interval": 10, "count": 3, "with_hook": True, "drafts": True,
                 "min_stars": 2, "before": 20, "after": 6, "hooks": [], "notify": True,
                 "clean": True, "caps_hours": 24, "clips_days": 7}
pilot_state = {"last_run": None, "next_run": None, "made": 0, "msg": "", "busy": False}
pilot_done = []  # posiciones aproximadas del directo ya convertidas en clip (para no repetir)


def pilot_cfg():
    try:
        return {**PILOT_DEFAULT, **json.loads(PILOT.read_text(encoding="utf-8"))}
    except Exception:  # noqa: BLE001
        return dict(PILOT_DEFAULT)


def _gpos(m):
    return int(m["seg"]) * SEG_SECONDS + float(m["off"])


def wait_and_notify(job_ids, what):
    def run():
        while True:
            with jobs_lock:
                js = [jobs.get(j) for j in job_ids]
            if all(j and j["status"] != "trabajando" for j in js):
                break
            time.sleep(3)
        ok = [j for j in js if j["status"] == "listo"]
        if not ok:
            return
        scores = []
        for j in ok:
            try:
                scores.append(json.loads(meta_path(j["result"]).read_text(encoding="utf-8"))["viral"]["score"])
            except Exception:  # noqa: BLE001
                pass
        best = f" · el mejor 🔥 {max(scores)}%" if scores else ""
        notify(f"🎬 {len(ok)} {what}", f"Listos para revisar en Clipper{best}", "/#clips")
    threading.Thread(target=run, daemon=True).start()


def pilot_cycle(cfg):
    pilot_state["busy"] = True
    jid = new_job("piloto", "🤖 Piloto automático: buscando momentos nuevos…")
    try:
        found, _ = detect_moments(jid, {"minutes": cfg["interval"] + 1, "before": cfg["before"],
                                        "after": cfg["after"], "top": 12})
        fresh = [m for m in found if m["stars"] >= int(cfg["min_stars"]) and
                 all(abs(_gpos(m) - g) > cfg["before"] + cfg["after"] for g in pilot_done)]
        fresh = sorted(fresh, key=lambda m: m["score"], reverse=True)[:int(cfg["count"])]
        if not fresh:
            pilot_state["msg"] = "Sin momentos nuevos fuertes en este ciclo."
            update_job(jid, status="listo", progress=100, label="🤖 Piloto: sin momentos nuevos fuertes")
            return
        settings = my_style()
        hooks_pool = [h for h in cfg.get("hooks") or [] if h.strip()]
        ids = []
        for i, m in enumerate(fresh):
            pilot_done.append(_gpos(m))
            label = f"🤖 Piloto · hace {fmt_t(m['ago'])}"
            hook = (hooks_pool[(pilot_state["made"] + i) % len(hooks_pool)] if hooks_pool else settings.get("hook", "")) if cfg["with_hook"] else ""
            item = {"kind": "anchor", "seg": m["seg"], "off": m["off"], "before": m["before"], "after": m["after"],
                    "label": label, "hook": hook, "text": m.get("text")}
            cid = new_job("render", label)
            run_job(cid, job_batch_item, item, dict(settings, _label=label, _moment_score=m["score"],
                                                    draft=bool(cfg["drafts"]), _auto=True, people=[]))
            ids.append(cid)
        del pilot_done[:-300]
        pilot_state["made"] += len(ids)
        pilot_state["msg"] = f"{len(ids)} clip{'s' if len(ids) > 1 else ''} en camino."
        update_job(jid, status="listo", progress=100, label=f"🤖 Piloto: {len(ids)} momentos nuevos → creando clips")
        if cfg.get("notify"):
            wait_and_notify(ids, "borradores nuevos del piloto" if cfg["drafts"] else "clips nuevos del piloto")
    except Exception as e:  # noqa: BLE001
        pilot_state["msg"] = "Error: " + clean_error(e)[:200]
        update_job(jid, status="error", error=clean_error(e)[:300])
    finally:
        pilot_state["busy"] = False


def pilot_loop():
    while True:
        time.sleep(10)
        try:
            cfg = pilot_cfg()
            if not cfg["enabled"] or not rec.running:
                pilot_state["next_run"] = None
                continue
            now = time.time()
            if pilot_state["next_run"] is None:  # primer ciclo cuando haya buffer suficiente
                pilot_state["next_run"] = now + min(cfg["interval"] * 60, 120)
            if now >= pilot_state["next_run"] and not pilot_state["busy"]:
                pilot_state["last_run"] = now
                pilot_state["next_run"] = now + cfg["interval"] * 60
                threading.Thread(target=pilot_cycle, args=(cfg,), daemon=True).start()
        except Exception:  # noqa: BLE001
            pass


threading.Thread(target=pilot_loop, daemon=True).start()


@app.get("/api/pilot")
def api_pilot():
    return jsonify(cfg=pilot_cfg(), state=pilot_state)


@app.post("/api/pilot")
def api_pilot_save():
    d = request.json or {}
    cfg = pilot_cfg()
    for k, v in d.items():
        if k in PILOT_DEFAULT:
            cfg[k] = v
    cfg["interval"] = max(3, min(60, int(cfg["interval"])))
    cfg["count"] = max(1, min(5, int(cfg["count"])))
    cfg["caps_hours"] = max(2, min(240, int(cfg["caps_hours"])))
    cfg["clips_days"] = max(1, min(60, int(cfg["clips_days"])))
    PILOT.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    if "enabled" in d or "interval" in d:
        pilot_state["next_run"] = None
    return jsonify(cfg=cfg, state=pilot_state)


@app.post("/api/pilot/run")
def api_pilot_run():
    if not rec.running:
        return jsonify(error="Inicia la grabación del directo primero."), 400
    if pilot_state["busy"]:
        return jsonify(error="El piloto ya está trabajando."), 400
    pilot_state["last_run"] = time.time()
    threading.Thread(target=pilot_cycle, args=(pilot_cfg(),), daemon=True).start()
    return jsonify(ok=True)


@app.post("/api/approve/<cid>")
def api_approve(cid):
    """Convierte un borrador en el clip final (calidad completa, subtítulos y portada)."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", cid) or not meta_path(cid).exists():
        return jsonify(error="Borrador no encontrado"), 404
    meta = json.loads(meta_path(cid).read_text(encoding="utf-8"))
    if meta.get("type") != "borrador" or not meta.get("opts"):
        return jsonify(error="Ese clip no es un borrador"), 400
    opts = dict(meta["opts"], draft=False, _label="✅ Final de " + (meta.get("label") or "borrador"))
    if not meta_path(opts.get("clip_id", "")).exists():
        return jsonify(error="La captura de ese borrador ya se borró. Haz el clip de nuevo."), 400
    jid = new_job("render", opts["_label"])

    def job(j, o, draft_id):
        job_render(j, o)
        for f in clip_files(draft_id):
            f.unlink(missing_ok=True)
    run_job(jid, job, opts, cid)
    return jsonify(job=jid)


@app.post("/api/keep/<cid>")
def api_keep(cid):
    if not re.fullmatch(r"[A-Za-z0-9_]+", cid) or not meta_path(cid).exists():
        return jsonify(error="Clip no encontrado"), 404
    meta = json.loads(meta_path(cid).read_text(encoding="utf-8"))
    meta["keep"] = not meta.get("keep")
    save_meta(cid, meta)
    return jsonify(keep=meta["keep"])


@app.post("/api/clean")
def api_clean():
    return jsonify(removed=auto_clean())


def folder_mb(path):
    total = 0
    for f in path.glob("*"):
        try:
            total += f.stat().st_size
        except OSError:
            pass
    return round(total / 1e6)


# ================= cola de publicación en horas pico
QUEUE = DATA / "cola.json"
_queue_lock = threading.Lock()
PEAK_HOURS = [int(h) for h in os.environ.get("HORAS_PICO", "12,19,22").split(",") if h.strip().isdigit()]


def page_tz():
    from zoneinfo import ZoneInfo
    try:
        return ZoneInfo(os.environ.get("ZONA_HORARIA", "America/Santo_Domingo"))
    except Exception:  # noqa: BLE001
        from datetime import timezone, timedelta
        return timezone(timedelta(hours=-4))


def next_peaks(n=6, after=None):
    from datetime import datetime, timedelta
    tz = page_tz()
    now = datetime.fromtimestamp(after or time.time(), tz)
    out, day = [], now.replace(minute=0, second=0, microsecond=0)
    for dd in range(0, 8):
        for h in sorted(PEAK_HOURS):
            t = (day + timedelta(days=dd)).replace(hour=h)
            if t.timestamp() > now.timestamp() + 120:
                out.append(t)
            if len(out) >= n:
                return out
    return out


def peak_label(dt):
    from datetime import datetime
    today = datetime.now(dt.tzinfo).date()
    day = "hoy" if dt.date() == today else "mañana" if (dt.date() - today).days == 1 else \
        ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"][dt.weekday()] + f" {dt.day}"
    h = dt.hour % 12 or 12
    return f"{day} {h}:{dt.minute:02d} {'pm' if dt.hour >= 12 else 'am'}"


def queue_load():
    try:
        return json.loads(QUEUE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def queue_save(items):
    QUEUE.write_text(json.dumps(items[-300:], ensure_ascii=False, indent=1), encoding="utf-8")


def queue_add(clip_id, when, targets, caption, tiktok_mode="inbox"):
    meta = json.loads(meta_path(clip_id).read_text(encoding="utf-8"))
    st = social.status()
    ok_targets = [t for t in targets if st.get(t)]
    item = {"id": uuid.uuid4().hex[:8], "clip_id": clip_id, "when": float(when), "targets": ok_targets,
            "caption": caption, "tiktok_mode": tiktok_mode, "status": "pendiente", "msg": "",
            "label": meta.get("label") or clip_id, "mode": "auto" if ok_targets else "aviso",
            "base": public_base()}
    with _queue_lock:
        items = queue_load()
        items.append(item)
        queue_save(items)
    return item


def queue_loop():
    while True:
        time.sleep(30)
        try:
            with _queue_lock:
                items = queue_load()
                due = [i for i in items if i["status"] == "pendiente" and i["when"] <= time.time()]
                for i in due:
                    i["status"] = "publicando"
                if due:
                    queue_save(items)
            for it in due:
                msgs, failed = [], False
                if not meta_path(it["clip_id"]).exists():
                    it["status"], it["msg"] = "error", "El clip ya no existe (se borró)."
                elif it["mode"] == "aviso":
                    notify("⏰ Hora de publicar", f"{it['label'][:60]} · toca para abrirlo y publicar",
                           f"/?pub={it['clip_id']}#clips")
                    it["status"], it["msg"] = "avisado", "Te avisé en el teléfono."
                else:
                    for t in it["targets"]:
                        jid = new_job("publicar", f"📅 Publicando en {t}…")
                        try:
                            job_publish(jid, t, it["clip_id"], it["caption"], it.get("tiktok_mode", "inbox"), it.get("base"))
                            update_job(jid, status="listo", progress=100)
                            msgs.append(f"{t} ✓")
                        except Exception as e:  # noqa: BLE001
                            failed = True
                            update_job(jid, status="error", error=clean_error(e)[:300])
                            msgs.append(f"{t}: {clean_error(e)[:120]}")
                    it["status"] = "error" if failed else "publicado"
                    it["msg"] = " · ".join(msgs)
                    notify("✅ Publicado" if not failed else "⚠️ Problema al publicar", f"{it['label'][:50]} · {it['msg'][:80]}", "/#clips")
                with _queue_lock:
                    items = queue_load()
                    for x in items:
                        if x["id"] == it["id"]:
                            x.update(status=it["status"], msg=it["msg"])
                    queue_save(items)
        except Exception:  # noqa: BLE001
            pass


threading.Thread(target=queue_loop, daemon=True).start()


@app.get("/api/queue")
def api_queue():
    items = sorted(queue_load(), key=lambda i: i["when"])
    for i in items:
        from datetime import datetime
        i["when_label"] = peak_label(datetime.fromtimestamp(i["when"], page_tz()))
    return jsonify(items=items, peaks=[{"t": p.timestamp(), "label": peak_label(p)} for p in next_peaks(6)])


@app.post("/api/queue")
def api_queue_add():
    d = request.json or {}
    cid = d.get("clip_id", "")
    if not re.fullmatch(r"[A-Za-z0-9_]+", cid) or not meta_path(cid).exists():
        return jsonify(error="Clip no encontrado"), 404
    when = d.get("when")
    if not when:
        taken = {round(i["when"]) for i in queue_load() if i["status"] == "pendiente"}
        when = next((p.timestamp() for p in next_peaks(12) if round(p.timestamp()) not in taken), None)
    if not when or float(when) < time.time() - 60:
        return jsonify(error="Elige una hora en el futuro"), 400
    item = queue_add(cid, when, d.get("targets") or [], d.get("caption", ""), d.get("tiktok_mode", "inbox"))
    return jsonify(item)


@app.delete("/api/queue/<qid>")
def api_queue_delete(qid):
    with _queue_lock:
        queue_save([i for i in queue_load() if i["id"] != qid])
    return jsonify(ok=True)


@app.post("/api/queue/spread")
def api_queue_spread():
    """Reparte los mejores clips (por % viral) en las próximas horas pico libres."""
    d = request.json or {}
    n = max(1, min(9, int(d.get("count", 3))))
    queued = {i["clip_id"] for i in queue_load() if i["status"] in ("pendiente", "publicado", "avisado")}
    finals = []
    for mp in CLIPS.glob("clip_*.json"):
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
            if m.get("type") == "final" and m["id"] not in queued and m.get("viral"):
                finals.append(m)
        except Exception:  # noqa: BLE001
            pass
    w = current_weights()
    finals.sort(key=lambda m: weighted_score(m["viral"]["parts"], w), reverse=True)
    finals = [m for m in finals if weighted_score(m["viral"]["parts"], w) >= int(d.get("min_score", 45))][:n]
    if not finals:
        return jsonify(error="No hay clips terminados sin programar (con 45 % o más)."), 400
    taken = {round(i["when"]) for i in queue_load() if i["status"] == "pendiente"}
    slots = [p for p in next_peaks(20) if round(p.timestamp()) not in taken][:len(finals)]
    out = []
    for m, slot in zip(finals, slots):
        out.append(queue_add(m["id"], slot.timestamp(), d.get("targets") or [], d.get("captions", {}).get(m["id"], ""),
                             d.get("tiktok_mode", "inbox")))
    return jsonify(items=out)


@app.post("/api/stats/<cid>")
def api_stats(cid):
    if not re.fullmatch(r"[A-Za-z0-9_]+", cid) or not meta_path(cid).exists():
        return jsonify(error="Clip no encontrado"), 404
    d = request.json or {}
    try:
        views = int(float(str(d.get("views", "")).lower().replace("k", "e3").replace("m", "e6").replace(",", "")))
    except ValueError:
        return jsonify(error="Escribe un número de vistas, por ejemplo 12500 o 12.5k"), 400
    meta = json.loads(meta_path(cid).read_text(encoding="utf-8"))
    meta["stats"] = {"views": max(0, views), "at": time.time()}
    save_meta(cid, meta)
    return jsonify(stats=meta["stats"], learn=learn_from_views())


@app.get("/api/learn")
def api_learn():
    try:
        return jsonify(json.loads(LEARN.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        return jsonify(n=0, weights=BASE_WEIGHTS, corr={})


@app.post("/api/auto-clips")
def api_auto_clips():
    d = request.json or {}
    if not d.get("clip_id") and not rec.segments():
        return jsonify(error="Inicia la grabación del directo (o abre una captura larga) primero."), 400
    kind = "con hook" if d.get("with_hook") else "sin hook"
    jid = new_job("auto", f"Buscando los {int(d.get('count', 5))} mejores momentos ({kind})…")
    run_job(jid, job_auto_clips, d)
    return jsonify(job=jid)


# ---- participantes (etiquetas manuales; sin reconocimiento facial)
PEOPLE = DATA / "participantes.json"


def people_list():
    try:
        return json.loads(PEOPLE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


@app.get("/api/people")
def api_people():
    return jsonify(people_list())


@app.post("/api/people")
def api_people_add():
    d = request.json or {}
    name = re.sub(r"\s+", " ", (d.get("name") or "")).strip()[:40]
    if not name:
        return jsonify(error="Escribe el nombre"), 400
    tag = (d.get("hashtag") or "").strip().lstrip("#")
    tag = re.sub(r"[^\wáéíóúñÁÉÍÓÚÑ]", "", tag) or re.sub(r"[^\wáéíóúñÁÉÍÓÚÑ]", "", name.title())
    lst = people_list()
    if any(p["name"].lower() == name.lower() for p in lst):
        return jsonify(error="Ya está en la lista"), 400
    lst.append({"id": uuid.uuid4().hex[:6], "name": name, "hashtag": tag,
                "alias": [a.strip() for a in (d.get("alias") or "").split(",") if a.strip()][:5]})
    PEOPLE.write_text(json.dumps(lst, ensure_ascii=False, indent=1), encoding="utf-8")
    return jsonify(lst)


@app.delete("/api/people/<pid>")
def api_people_delete(pid):
    lst = [p for p in people_list() if p["id"] != pid]
    PEOPLE.write_text(json.dumps(lst, ensure_ascii=False, indent=1), encoding="utf-8")
    return jsonify(lst)


def people_in_text(text):
    """Participantes cuyo nombre (o apodo) se menciona en lo que se dice."""
    low = " " + re.sub(r"[^\wáéíóúñ ]", " ", (text or "").lower()) + " "
    found = []
    for p in people_list():
        names = [p["name"]] + p.get("alias", [])
        if any(f" {n.lower()} " in low for n in names if len(n) >= 3):
            found.append(p["id"])
    return found


@app.get("/api/job/<jid>")
def api_job(jid):
    with jobs_lock:
        j = jobs.get(jid)
    return (jsonify(j), 200) if j else (jsonify(error="no existe"), 404)


@app.post("/api/batch")
def api_batch():
    """Varios clips a la vez con la misma configuración."""
    d = request.json or {}
    items, settings = d.get("items") or [], {**my_style(), **(d.get("settings") or {})}
    if not items:
        return jsonify(error="Elige al menos un momento"), 400
    if len(items) > 20:
        return jsonify(error="Máximo 20 clips por lote"), 400
    ids = []
    for i, it in enumerate(items, 1):
        it.setdefault("label", f"Clip {i}/{len(items)}")
        st = dict(settings, _label=it["label"], _moment_score=it.get("score"),
                  _part=f"PARTE {i}/{len(items)}" if len(items) > 1 else None)
        jid = new_job("render", it["label"])
        run_job(jid, job_batch_item, it, st)
        ids.append(jid)
    return jsonify(jobs=ids)


# ---- portada
@app.post("/api/cover")
def api_cover():
    d = request.json or {}
    if not d.get("clip_id") or not meta_path(d["clip_id"]).exists():
        return jsonify(error="Captura no encontrada"), 404
    jid = new_job("portada", "Creando portada…")
    run_job(jid, job_cover, d)
    return jsonify(job=jid)


# ---- logo para marca de agua
@app.post("/api/logo")
def api_logo():
    from PIL import Image
    f = request.files.get("file")
    if not f:
        return jsonify(error="Sube una imagen (PNG con fondo transparente es lo ideal)"), 400
    try:
        im = Image.open(f.stream).convert("RGBA")
    except Exception:  # noqa: BLE001
        return jsonify(error="Esa imagen no se pudo abrir"), 400
    im.thumbnail((1200, 1200))
    im.save(LOGO)
    return jsonify(ok=True)


@app.delete("/api/logo")
def api_logo_delete():
    LOGO.unlink(missing_ok=True)
    return jsonify(ok=True)


@app.get("/api/logo.png")
def api_logo_file():
    return send_file(LOGO, max_age=0) if LOGO.exists() else ("", 404)


# ---- cuentas y publicación
def public_base():
    base = os.environ.get("PUBLIC_URL", "").strip() or request.url_root
    return base.rstrip("/") + "/"


def _oauth_page(msg, ok=False):
    color = "#22c55e" if ok else "#ff2e63"
    return (f"<html><body style='background:#0d0d10;color:#eee;font:16px system-ui;padding:40px'>"
            f"<h2 style='color:{color}'>{'✅' if ok else '❌'} {msg}</h2><a style='color:#ffd60a' href='/'>Volver a Clipper</a>"
            f"<script>setTimeout(()=>location.href='/',{2500 if ok else 15000})</script></body></html>")


@app.get("/oauth/<net>/start")
def oauth_start(net):
    redirect_uri = public_base() + f"oauth/{net}/callback"
    try:
        url = social.meta_auth_url(redirect_uri) if net == "meta" else social.tiktok_auth_url(redirect_uri)
    except KeyError:
        return _oauth_page("Falta configurar la app de desarrollador en el servidor (ver README)."), 400
    return redirect(url)


@app.get("/oauth/<net>/callback")
def oauth_callback(net):
    if request.args.get("error"):
        return _oauth_page("Conexión cancelada: " + request.args.get("error_description", request.args["error"]))
    if not social.check_state(request.args.get("state"), net):
        return _oauth_page("La sesión de conexión venció. Inténtalo otra vez."), 400
    redirect_uri = public_base() + f"oauth/{net}/callback"
    try:
        if net == "meta":
            social.meta_callback(request.args.get("code", ""), redirect_uri)
        else:
            social.tiktok_callback(request.args.get("code", ""), redirect_uri)
    except Exception as e:  # noqa: BLE001
        return _oauth_page("No se pudo conectar: " + clean_error(e)[:300]), 400
    return _oauth_page(("Facebook / Instagram" if net == "meta" else "TikTok") + " conectado", ok=True)


@app.post("/api/cuentas")
def api_cuentas():
    d = request.json or {}
    try:
        if d.get("fb_page_id") and d.get("fb_token"):
            social.set_manual_meta(d["fb_page_id"].strip(), d["fb_token"].strip(), (d.get("ig_id") or "").strip() or None)
        if d.get("tiktok_token"):
            social.set_manual_tiktok(d["tiktok_token"].strip())
        if d.get("page_id"):
            social.select_page(d["page_id"])
    except Exception as e:  # noqa: BLE001
        return jsonify(error=clean_error(e)[:400]), 400
    return jsonify(social.status())


@app.delete("/api/cuentas/<net>")
def api_cuentas_delete(net):
    social.disconnect(net)
    return jsonify(social.status())


# ---- copys con IA (opcional): Claude escribe copys a partir del hook y de lo que se dice en el clip
COPY_MODEL = os.environ.get("COPY_MODEL", "claude-opus-5-5")
COPY_SYSTEM = """Eres el community manager de una página de clips virales de "La Casa de Alofoke 3", un reality show
dominicano que se transmite en vivo por YouTube. Escribes copys (descripciones) para TikTok, Instagram Reels y Facebook.

Reglas:
- Español dominicano natural, cercano, con jerga ligera cuando quede bien (tiguere, dique, ¡qué lo qué!, ta' duro).
- Cada copy: 1 o 2 frases cortas, máximo 160 caracteres, con 1 a 3 emojis.
- Termina con una pregunta o un llamado a comentar, etiquetar o pedir parte 2.
- Basa el copy en lo que realmente pasa en el clip (transcripción y hook). No inventes nombres, hechos ni frases que no estén ahí.
- Nada de insultos, burlas a personas reales, contenido sexual ni acusaciones. Polémica sí, difamación no.
- Sin hashtags (la app los agrega aparte).
- Los 3 copys deben ser distintos entre sí: uno con pregunta polémica, uno con gancho de curiosidad y uno gracioso o de "etiqueta a alguien"."""
COPY_SCHEMA = {
    "type": "object",
    "properties": {"copys": {"type": "array", "items": {"type": "string"}}},
    "required": ["copys"],
    "additionalProperties": False,
}


def ai_available():
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def job_copy_ai(jid, d):
    import anthropic
    cid = d.get("clip_id", "")
    meta = json.loads(meta_path(cid).read_text(encoding="utf-8")) if re.fullmatch(r"[A-Za-z0-9_]+", cid) and meta_path(cid).exists() else {}
    transcript = meta.get("transcript") or ""
    if not transcript and meta.get("file") and _has_whisper():
        update_job(jid, label="Escuchando lo que se dice en el clip…", progress=10)
        wav = TMP / f"copy_{jid}.wav"
        run_ffmpeg(["-i", str(CLIPS / meta["file"]), "-vn", "-ac", "1", "-ar", "16000", "-t", "180", str(wav)])
        try:
            transcript = " ".join(w[2] for w in transcribe_words(wav))
        finally:
            wav.unlink(missing_ok=True)
        meta["transcript"] = transcript
        save_meta(cid, meta)
    hook = (d.get("hook") or meta.get("hook") or "").replace("*", "").strip()
    cat = d.get("cat") or meta.get("cat") or ""
    update_job(jid, label="La IA está escribiendo copys…", progress=60)
    prompt = (f"Tipo de momento: {cat or 'no indicado'}\n"
              f"Hook en pantalla: {hook or '(sin hook)'}\n"
              f"Duración del clip: {int(meta.get('duration') or 0)} segundos\n"
              f"Lo que se dice en el clip (transcripción automática, puede tener errores):\n"
              f"{transcript[:4000] or '(no hay transcripción: básate solo en el hook y el tipo de momento)'}\n\n"
              "Escribe 3 copys virales para este clip.")
    client = anthropic.Anthropic()
    try:
        resp = _copy_request(client, prompt)
    except anthropic.AuthenticationError as e:
        raise RuntimeError("La clave de Anthropic (ANTHROPIC_API_KEY) no es válida. Revísala en Railway.") from e
    except anthropic.PermissionDeniedError as e:
        raise RuntimeError("Tu clave de Anthropic no tiene permiso o no tiene saldo. Revisa tu cuenta en console.anthropic.com.") from e
    except anthropic.RateLimitError as e:
        raise RuntimeError("Demasiadas peticiones a la IA. Espera un minuto y vuelve a intentar.") from e
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"La IA dio un error ({e.status_code}). Intenta otra vez en un momento.") from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError("El servidor no pudo conectarse con la IA. Revisa la conexión.") from e
    if resp.stop_reason == "refusal":
        raise RuntimeError("La IA no quiso escribir sobre este clip. Usa el generador 🎲.")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    copys = [c.strip() for c in json.loads(text).get("copys", []) if c.strip()][:5]
    if not copys:
        raise RuntimeError("La IA no devolvió copys. Intenta otra vez.")
    update_job(jid, label="Copys listos ✨", result={"copys": copys, "transcribed": bool(transcript)})


def _copy_request(client, prompt):
    return client.beta.messages.create(
        model=COPY_MODEL,
        max_tokens=2000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",                      # si el modelo rechaza, la API reintenta con otro
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": COPY_SCHEMA}},
        system=COPY_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )


@app.post("/api/copy-ai")
def api_copy_ai():
    if not ai_available():
        return jsonify(error="La IA no está configurada: agrega ANTHROPIC_API_KEY en Railway (ver README)."), 400
    jid = new_job("copy", "Escribiendo copys con IA…")
    run_job(jid, job_copy_ai, request.json or {})
    return jsonify(job=jid)


@app.post("/api/publish")
def api_publish():
    d = request.json or {}
    cid = d.get("clip_id", "")
    if not re.fullmatch(r"[A-Za-z0-9_]+", cid) or not meta_path(cid).exists():
        return jsonify(error="Clip no encontrado"), 404
    targets = [t for t in d.get("targets", []) if t in ("facebook", "instagram", "tiktok")]
    if not targets:
        return jsonify(error="Elige dónde publicar"), 400
    names = {"facebook": "Facebook", "instagram": "Instagram", "tiktok": "TikTok"}
    ids = []
    for t in targets:
        jid = new_job("publicar", f"Publicando en {names[t]}…")
        run_job(jid, job_publish, t, cid, d.get("caption", ""), d.get("tiktok_mode", "inbox"), public_base())
        ids.append(jid)
    return jsonify(jobs=ids)


@app.get("/pub/<tok>/<name>")
def public_file(tok, name):
    path = Social.resolve_public(tok)
    if not path or Path(path).name != name:
        return "No encontrado", 404
    return send_file(path, conditional=True)


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
    w = current_weights()
    for c in clips:
        v = c.get("viral")
        if v and v.get("parts"):
            v["score"] = weighted_score(v["parts"], w)
            v["level"] = "alto" if v["score"] >= 70 else "medio" if v["score"] >= 45 else "bajo"
    with jobs_lock:
        js = sorted(jobs.values(), key=lambda j: j["created"], reverse=True)[:30]
    return jsonify(
        recorder={"running": rec.running, "url": rec.url, "error": rec.error,
                  "buffer": rec.buffer_seconds(), "max": BUFFER_MIN * 60,
                  "video_id": youtube_id(rec.url)},
        jobs=js, clips=clips, subs_available=_has_whisper(), font=find_font()[1],
        cookies=COOKIES.exists(),
        markers=markers[:30], logo=LOGO.exists(), social=social.status(),
        public_base=public_base(), render_workers=RENDER_WORKERS, ai=ai_available(),
        pilot={"cfg": pilot_cfg(), "state": pilot_state}, push=push_available(), push_count=len(push_subs()),
        queue_pending=sum(1 for i in queue_load() if i["status"] == "pendiente"), smart=_has_whisper(),
        chat=chat.summary(), yt_health={k: yt_health[k] for k in ("ok", "checked", "msg")},
        smartcrop=smartcrop.available(),
        disk={"clips_mb": folder_mb(CLIPS), "buffer_mb": folder_mb(BUF),
              "free_gb": round(shutil.disk_usage(DATA).free / 1e9, 1)},
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
