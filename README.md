# ✂️ Clipper en Vivo — clips virales de La Casa de Alofoke 3

App local (corre en tu PC) para sacar clips **mientras el directo de YouTube está pasando**
y exportarlos en vertical 9:16 listos para TikTok, Reels y Shorts.

## Cómo funciona
1. Pegas el link del directo y le das **● Iniciar grabación**. La app va guardando los
   últimos 30 minutos en pedacitos de 4 s (lo viejo se borra solo, no llena el disco).
2. Cuando pasa algo fuerte, aprietas **30 s / 1 min / 2 min / 5 min** (o las teclas `1` `2` `3` `4`).
3. La captura se abre en el editor: marcas **entrada** (`I`) y **salida** (`O`) exactas,
   escribes el hook, eliges formato y si quieres subtítulos automáticos.
4. **🎬 Renderizar** → aparece en "Clips listos" con botón de descarga y un copy con hashtags.

También puedes sacar tramos de un video ya subido o de la repetición del directo
("Capturar de un video ya subido", con desde/hasta tipo `1:02:10`).

## Instalación
**Windows:** doble clic en `iniciar.bat` (instala ffmpeg y Deno con winget la primera vez,
luego cierra y vuelve a abrirlo). Necesitas [Python 3.10+](https://www.python.org/downloads/)
con la casilla "Add to PATH".

**Mac / Linux:** `./iniciar.sh` (necesitas ffmpeg instalado).

Se abre sola en el navegador: http://127.0.0.1:5055

### Subtítulos automáticos (opcional)
```
pip install -r requirements-subtitulos.txt
```
(dentro del `.venv`). La primera vez descarga el modelo Whisper "small" (~500 MB).
Salen palabra por palabra, en mayúsculas, con la palabra que se está diciendo en amarillo.
Para más precisión: `set WHISPER_MODEL=medium` antes de iniciar (más lento).

## Opciones del editor
- **Fondo desenfocado**: el video completo al centro y el mismo video borroso detrás.
- **Pantalla completa (recorte)**: llena la pantalla; mueve "posición" para enfocar a la persona
  que está hablando (izquierda / centro / derecha) y usa zoom si hace falta.
- **Hook** arriba en cajas blancas (los emojis se quitan del video porque salen como cuadritos;
  ponlos en el copy).
- **Marca de agua** con tu @.
- Pon tu propia fuente guardándola como `fuente.ttf` en esta carpeta.

## Ajustes (variables de entorno)
| Variable | Por defecto | Qué hace |
|---|---|---|
| `BUFFER_MIN` | 30 | Minutos del directo que se guardan |
| `CALIDAD` | 1080 | Altura máxima a grabar (720 si tu internet es lento) |
| `WHISPER_MODEL` | small | tiny / base / small / medium |
| `PORT` | 5055 | Puerto de la app |

## Problemas comunes
- **"No se pudo grabar el directo"**: actualiza yt-dlp (`pip install -U "yt-dlp[default]"`),
  asegúrate de tener Deno instalado y revisa `buffer/grabadora.log`.
- **El directo se ve en la app pero no se graba**: el reproductor es solo para mirar; la
  grabación depende de yt-dlp.
- Los clips quedan en la carpeta `clips/`.

## 🌐 Ponerla en línea (acceder desde el celular o cualquier PC)

La app ya viene lista para servidor (`Dockerfile`). Necesita un servidor **encendido 24/7**
(la grabación es un proceso continuo), así que **no sirve en Vercel/Netlify**; usa Railway o Render.

### Opción A — Railway (la más fácil, ~5 US$/mes)
1. Sube esta carpeta a un repositorio de GitHub (privado).
2. En [railway.com](https://railway.com) → **New Project → Deploy from GitHub repo** → elige el repo.
3. En **Variables** agrega: `APP_PASSWORD` = una contraseña fuerte.
4. En **Settings → Volumes** crea un volumen montado en `/data`.
5. En **Settings → Networking → Generate Domain**. Listo: entras con cualquier usuario + tu contraseña.

### Opción B — Render (~7–25 US$/mes)
Sube el repo a GitHub → en [render.com](https://render.com) **New → Blueprint** → elige el repo
(usa `render.yaml`, que ya crea el disco y una contraseña aleatoria; la ves en *Environment*).

### Opción C — Tu propio VPS (Hetzner, DigitalOcean, Contabo…)
```
docker build -t clipper .
docker run -d --restart unless-stopped -p 80:8080 -v clipper-data:/data -e APP_PASSWORD=tuClave clipper
```

### ⚠️ Muy importante: YouTube bloquea servidores
Desde servidores en la nube, YouTube suele responder *"Sign in to confirm you're not a bot"*.
Solución: en la app abre **🍪 Cookies de YouTube** y sube un `cookies.txt` exportado con la
extensión "Get cookies.txt LOCALLY" (usa una **cuenta secundaria**, no la principal).
Si aun así bloquea, usa un proxy residencial con la variable `YT_PROXY=http://usuario:clave@host:puerto`.
Las cookies vencen cada cierto tiempo: si vuelve el error, súbelas de nuevo.

### Variables para servidor
| Variable | Qué hace |
|---|---|
| `APP_PASSWORD` | **Obligatoria en línea.** Contraseña para entrar |
| `DATA_DIR` | Carpeta de datos (en Docker ya es `/data`) |
| `YT_COOKIES` | Alternativa a subir cookies: el contenido de cookies.txt |
| `YT_PROXY` | Proxy para yt-dlp |

Subtítulos en servidor: el Docker los incluye con el modelo `base` (necesita ~2 GB de RAM).
Para un plan más barato, construye sin ellos: `docker build --build-arg SUBTITULOS=0 .`

## Ojo con los derechos
El contenido de La Casa de Alofoke es de sus dueños. Los canales de clips suelen funcionar
porque el canal lo permite o porque agregan valor (comentario, reacción, edición). Si te
llegan reclamos de copyright en TikTok/YouTube, el video se puede caer o la cuenta recibir
strikes; revisa las reglas del canal sobre clips.
