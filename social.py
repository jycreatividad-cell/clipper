"""
Publicación directa en Facebook (página), Instagram (Reels) y TikTok.

Conexión de cuentas:
  · Botones "Conectar" (OAuth) si defines en el servidor:
        META_APP_ID, META_APP_SECRET            (app de developers.facebook.com)
        TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET (app de developers.tiktok.com)
        PUBLIC_URL                               (ej. https://clipper.up.railway.app)
  · O pegando tokens a mano en la app (sección Cuentas).

Instagram descarga el video desde una URL pública, por eso solo funciona con la app en
internet (Railway/Render), no en 127.0.0.1.
"""

import json
import os
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

GRAPH = "https://graph.facebook.com/v21.0"
GRAPH_VIDEO = "https://graph-video.facebook.com/v21.0"
TT = "https://open.tiktokapis.com/v2"

META_SCOPES = ("pages_show_list,pages_read_engagement,pages_manage_posts,"
               "instagram_basic,instagram_content_publish,business_management")
TIKTOK_SCOPES = "user.info.basic,video.upload,video.publish"

_lock = threading.Lock()
_states = {}          # state OAuth -> (red, vence)
_public = {}          # token -> (ruta, vence)


class Social:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / "cuentas.json"

    # ------------------------------------------------------------ almacenamiento
    def load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def save(self, data):
        with _lock:
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass

    def status(self):
        d = self.load()
        meta = d.get("meta", {})
        page = next((p for p in meta.get("pages", []) if p["id"] == meta.get("page_id")), None)
        tt = d.get("tiktok", {})
        return {
            "meta_oauth": bool(os.environ.get("META_APP_ID") and os.environ.get("META_APP_SECRET")),
            "tiktok_oauth": bool(os.environ.get("TIKTOK_CLIENT_KEY") and os.environ.get("TIKTOK_CLIENT_SECRET")),
            "pages": [{"id": p["id"], "name": p.get("name", p["id"]),
                       "ig": p.get("ig_username") or (p.get("ig_id") and "conectado")} for p in meta.get("pages", [])],
            "page_id": meta.get("page_id"),
            "facebook": bool(page and page.get("token")),
            "facebook_name": page.get("name") if page else None,
            "instagram": bool(page and page.get("ig_id")),
            "instagram_name": page.get("ig_username") if page else None,
            "tiktok": bool(tt.get("access_token")),
            "tiktok_name": tt.get("name"),
        }

    # ------------------------------------------------------------ OAuth
    @staticmethod
    def new_state(net):
        st = secrets.token_urlsafe(16)
        _states[st] = (net, time.time() + 900)
        return st

    @staticmethod
    def check_state(st, net):
        v = _states.pop(st or "", None)
        return bool(v and v[0] == net and v[1] > time.time())

    def meta_auth_url(self, redirect):
        q = {"client_id": os.environ["META_APP_ID"], "redirect_uri": redirect,
             "scope": META_SCOPES, "state": self.new_state("meta"), "response_type": "code"}
        return "https://www.facebook.com/v21.0/dialog/oauth?" + urlencode(q)

    def meta_callback(self, code, redirect):
        app_id, secret = os.environ["META_APP_ID"], os.environ["META_APP_SECRET"]
        r = _ok(requests.get(f"{GRAPH}/oauth/access_token", params={
            "client_id": app_id, "client_secret": secret, "redirect_uri": redirect, "code": code}, timeout=30))
        short = r["access_token"]
        r = _ok(requests.get(f"{GRAPH}/oauth/access_token", params={
            "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": secret,
            "fb_exchange_token": short}, timeout=30))
        self._store_meta_user_token(r["access_token"])

    def _store_meta_user_token(self, user_token):
        r = _ok(requests.get(f"{GRAPH}/me/accounts", params={
            "fields": "id,name,access_token,instagram_business_account{id,username}",
            "access_token": user_token, "limit": 100}, timeout=30))
        pages = []
        for p in r.get("data", []):
            ig = p.get("instagram_business_account") or {}
            pages.append({"id": p["id"], "name": p.get("name"), "token": p.get("access_token"),
                          "ig_id": ig.get("id"), "ig_username": ig.get("username")})
        if not pages:
            raise RuntimeError("Tu cuenta no administra ninguna página de Facebook (o no diste permiso).")
        d = self.load()
        old = d.get("meta", {}).get("page_id")
        d["meta"] = {"user_token": user_token, "pages": pages,
                     "page_id": old if any(p["id"] == old for p in pages) else pages[0]["id"]}
        self.save(d)

    def set_manual_meta(self, page_id, page_token, ig_id=None):
        """Token de página pegado a mano (desde el Explorador de la Graph API)."""
        info = _ok(requests.get(f"{GRAPH}/{page_id}", params={
            "fields": "id,name,instagram_business_account{id,username}", "access_token": page_token}, timeout=30))
        ig = info.get("instagram_business_account") or {}
        d = self.load()
        d["meta"] = {"pages": [{"id": info["id"], "name": info.get("name"), "token": page_token,
                                "ig_id": ig_id or ig.get("id"), "ig_username": ig.get("username")}],
                     "page_id": info["id"]}
        self.save(d)

    def select_page(self, page_id):
        d = self.load()
        if not any(p["id"] == page_id for p in d.get("meta", {}).get("pages", [])):
            raise RuntimeError("Página no encontrada")
        d["meta"]["page_id"] = page_id
        self.save(d)

    def tiktok_auth_url(self, redirect):
        q = {"client_key": os.environ["TIKTOK_CLIENT_KEY"], "scope": TIKTOK_SCOPES,
             "response_type": "code", "redirect_uri": redirect, "state": self.new_state("tiktok")}
        return "https://www.tiktok.com/v2/auth/authorize/?" + urlencode(q)

    def tiktok_callback(self, code, redirect):
        r = requests.post(f"{TT}/oauth/token/", data={
            "client_key": os.environ["TIKTOK_CLIENT_KEY"], "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
            "code": code, "grant_type": "authorization_code", "redirect_uri": redirect},
            headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
        self._store_tiktok(_ok(r))

    def _store_tiktok(self, tok):
        if "access_token" not in tok:
            raise RuntimeError("TikTok no devolvió token: " + json.dumps(tok)[:300])
        d = self.load()
        tt = {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token"),
              "expires_at": time.time() + int(tok.get("expires_in", 86400)) - 120,
              "open_id": tok.get("open_id")}
        try:
            u = requests.get(f"{TT}/user/info/", params={"fields": "display_name"},
                             headers={"Authorization": "Bearer " + tt["access_token"]}, timeout=20).json()
            tt["name"] = u.get("data", {}).get("user", {}).get("display_name")
        except Exception:  # noqa: BLE001
            pass
        d["tiktok"] = tt
        self.save(d)

    def set_manual_tiktok(self, token):
        self._store_tiktok({"access_token": token, "expires_in": 86400 * 365})

    def _tiktok_token(self):
        d = self.load()
        tt = d.get("tiktok", {})
        if not tt.get("access_token"):
            raise RuntimeError("TikTok no está conectado.")
        if tt.get("refresh_token") and tt.get("expires_at", 0) < time.time() and os.environ.get("TIKTOK_CLIENT_KEY"):
            r = requests.post(f"{TT}/oauth/token/", data={
                "client_key": os.environ["TIKTOK_CLIENT_KEY"], "client_secret": os.environ.get("TIKTOK_CLIENT_SECRET", ""),
                "grant_type": "refresh_token", "refresh_token": tt["refresh_token"]},
                headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
            self._store_tiktok(_ok(r))
            tt = self.load()["tiktok"]
        return tt["access_token"]

    def disconnect(self, net):
        d = self.load()
        d.pop("meta" if net in ("meta", "facebook", "instagram") else net, None)
        self.save(d)

    def _page(self):
        meta = self.load().get("meta", {})
        page = next((p for p in meta.get("pages", []) if p["id"] == meta.get("page_id")), None)
        if not page or not page.get("token"):
            raise RuntimeError("Facebook no está conectado.")
        return page

    # ------------------------------------------------------------ publicar
    def publish_facebook(self, video_path, caption, progress=lambda p: None):
        page = self._page()
        progress(20)
        with open(video_path, "rb") as f:
            r = requests.post(f"{GRAPH_VIDEO}/{page['id']}/videos",
                              data={"description": caption, "access_token": page["token"]},
                              files={"source": (Path(video_path).name, f, "video/mp4")}, timeout=900)
        res = _ok(r)
        return f"Publicado en la página {page.get('name')} (video {res.get('id')})"

    def publish_instagram(self, video_url, caption, cover_url=None, progress=lambda p: None):
        page = self._page()
        if not page.get("ig_id"):
            raise RuntimeError("La página no tiene una cuenta de Instagram profesional vinculada.")
        params = {"media_type": "REELS", "video_url": video_url, "caption": caption,
                  "share_to_feed": "true", "access_token": page["token"]}
        if cover_url:
            params["cover_url"] = cover_url
        cont = _ok(requests.post(f"{GRAPH}/{page['ig_id']}/media", data=params, timeout=60))["id"]
        progress(30)
        for i in range(90):  # hasta ~7 minutos procesando
            st = _ok(requests.get(f"{GRAPH}/{cont}", params={
                "fields": "status_code,status", "access_token": page["token"]}, timeout=30))
            code = st.get("status_code")
            if code == "FINISHED":
                break
            if code in ("ERROR", "EXPIRED"):
                raise RuntimeError("Instagram rechazó el video: " + str(st.get("status")))
            progress(min(90, 30 + i))
            time.sleep(5)
        else:
            raise RuntimeError("Instagram tardó demasiado procesando el video.")
        res = _ok(requests.post(f"{GRAPH}/{page['ig_id']}/media_publish", data={
            "creation_id": cont, "access_token": page["token"]}, timeout=60))
        return f"Publicado en Instagram @{page.get('ig_username') or ''} (reel {res.get('id')})"

    def publish_tiktok(self, video_path, caption, mode="inbox", progress=lambda p: None):
        token = self._tiktok_token()
        h = {"Authorization": "Bearer " + token, "Content-Type": "application/json; charset=UTF-8"}
        size = os.path.getsize(video_path)
        if size <= 64 * 1024 * 1024:
            chunk, count = size, 1
        else:
            chunk = 10 * 1024 * 1024
            count = size // chunk
        source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk, "total_chunk_count": count}
        if mode == "direct":
            info = _ok(requests.post(f"{TT}/post/publish/creator_info/query/", headers=h, json={}, timeout=30))
            opts = info.get("data", {}).get("privacy_level_options") or ["SELF_ONLY"]
            privacy = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in opts else opts[0]
            body = {"post_info": {"title": caption[:2200], "privacy_level": privacy}, "source_info": source}
            init = _ok(requests.post(f"{TT}/post/publish/video/init/", headers=h, json=body, timeout=30))
        else:
            init = _ok(requests.post(f"{TT}/post/publish/inbox/video/init/", headers=h,
                                     json={"source_info": source}, timeout=30))
        data = init.get("data", {})
        url, pid = data.get("upload_url"), data.get("publish_id")
        if not url:
            raise RuntimeError("TikTok no dio URL de subida: " + json.dumps(init)[:300])
        with open(video_path, "rb") as f:
            for i in range(count):
                start = i * chunk
                end = size - 1 if i == count - 1 else start + chunk - 1
                f.seek(start)
                part = f.read(end - start + 1)
                r = requests.put(url, data=part, headers={
                    "Content-Type": "video/mp4", "Content-Length": str(len(part)),
                    "Content-Range": f"bytes {start}-{end}/{size}"}, timeout=600)
                if r.status_code not in (200, 201, 206):
                    raise RuntimeError(f"TikTok rechazó la subida ({r.status_code}): {r.text[:300]}")
                progress(20 + int(70 * (i + 1) / count))
        if mode == "direct":
            return f"Enviado a TikTok ({privacy}). Puede tardar unos minutos en aparecer. id {pid}"
        return "Enviado a tus borradores de TikTok: abre la app de TikTok (notificaciones) para terminar de publicar."

    # ------------------------------------------------------------ enlaces públicos (para Instagram)
    @staticmethod
    def public_link(path, hours=3):
        tok = secrets.token_urlsafe(24)
        _public[tok] = (str(path), time.time() + hours * 3600)
        for k, (_, exp) in list(_public.items()):
            if exp < time.time():
                _public.pop(k, None)
        return tok

    @staticmethod
    def resolve_public(tok):
        v = _public.get(tok)
        if v and v[1] > time.time():
            return v[0]
        return None


def _ok(resp):
    try:
        j = resp.json()
    except ValueError:
        j = {"raw": resp.text[:300]}
    err = j.get("error") if isinstance(j, dict) else None
    if resp.status_code >= 400 or (isinstance(err, dict) and err.get("code") not in (None, "ok")):
        msg = err.get("message") if isinstance(err, dict) else None
        raise RuntimeError(f"Error {resp.status_code}: {msg or json.dumps(j)[:400]}")
    return j
