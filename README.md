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

## ⭐ Plantillas PRO de hooks (15 categorías)

![Lámina de plantillas](plantillas/lamina.png)

Polémica · Curiosidad · Noticias RD · Debate · Viral · Actualidad RD · Humor/Sarcasmo · Impacto ·
Verdad incómoda · Motivacional · Revelación · Alerta · Reflexión · Tendencia · Local/Cotidiano.

**En la app** (pestaña "⭐ Plantillas PRO"), cada plantilla deja cambiar: texto del hook,
palabra resaltada (`*así*`), color de resaltado, encabezado (o quitarlo), icono/emoji
(`-` = ninguno), fondo del panel, posición y tamaño. Funciona en 9:16, 1:1 y 16:9.

**Fuera de la app** (CapCut, Premiere, Canva): en `plantillas/NN-categoria/` hay PNG
transparentes listos para poner encima del video (`vertical.png` 1080×1920, `cuadrado.png`
1080×1080, `horizontal.png` 1920×1080 y `hook.png` recortado). Para crear uno con tu texto:
```
python generar_plantillas.py --cat viral --texto "SE ARMÓ EL *LÍO* 😱" --encabezado "LA CASA DE ALOFOKE" --color "#22D3EE"
```
Para crear categorías nuevas o cambiar colores/iconos por defecto, edita `CATS` en `templates.py`.

## 🏠 Hooks para La Casa de Alofoke

En el editor, debajo del hook, hay **10 tipos de momento** con frases listas: 🔥 Pelea · 💘 Romance ·
🗳️ Nominación · 🤫 Chisme · 😂 Risa · 🎙️ Reacción de Alofoke · 🐍 Traición · 🎉 Fiesta · 😢 Emotivo ·
👀 Gancho. Al tocar una frase se pone sola la plantilla que mejor le va, y el copy y los hashtags se
adaptan al tipo de momento. **🎲 Al azar** elige una frase. Al crear varios clips a la vez, cada uno
puede llevar un hook distinto. Para agregar o cambiar frases, copys y hashtags, edita
`static/alofoke.js`.

### ✍️ Copys distintos para cada clip
- **Generador automático (gratis):** arma el copy a partir del hook de cada clip, detecta el tipo de
  momento por sus palabras (pelea, chisme, romance, risa…) y usa estructuras virales distintas
  (pregunta polémica, "parte 2", etiqueta a alguien, mira hasta el final). Cada **🎲 Otro** da uno nuevo.
  Las frases están en `static/alofoke.js` (`estructuras`, `cierres`, `palabras`).
- **✨ Copy con IA (opcional):** escucha lo que se dice en el clip (si tienes los subtítulos
  instalados) y Claude escribe 3 copys sobre ese momento concreto, en español dominicano. Para
  activarlo, en Railway → Variables agrega `ANTHROPIC_API_KEY` (créala en console.anthropic.com).
  Usa Claude Opus 5.5 con poco razonamiento para ir rápido (cambia el modelo con `COPY_MODEL`), y si
  el modelo se niega a una petición la API la reintenta sola con otro modelo. Cada copy cuesta
  centavos de dólar.

## 📱 Usarla en el iPhone (como app)

1. Abre en **Safari** el link de tu app en Railway (ej. `https://clipper-production.up.railway.app`).
2. Entra con tu contraseña (`APP_PASSWORD`). El iPhone puede guardarla en el llavero.
3. Toca **Compartir** (cuadrito con flecha ⬆️) → **“Agregar a pantalla de inicio”** → Agregar.
4. Ábrela desde el icono ✂️: se ve a pantalla completa, sin barra de Safari, y la sesión queda
   recordada (180 días).

En el celular la app se organiza en pestañas abajo: **🔴 Directo · ✂️ Editor · 🎬 Clips · 🚀 Cuentas**.
- Mientras graba, el botón amarillo **📍** marca el momento con un toque.
- Al capturar, salta solo al Editor; al renderizar, salta a Clips (con un número cuando hay nuevos).
- En cada clip, **📲** abre el menú de Compartir del iPhone: **Guardar video** (va a Fotos), TikTok,
  Instagram, WhatsApp… El copy queda copiado para pegarlo. Si dice “Toca otra vez”, tócalo de nuevo
  (el iPhone pide que el menú se abra justo al tocar).

> La app necesita estar en internet (Railway/Render) para usarla desde el iPhone. Si la corres en tu
> PC, puedes abrirla desde el iPhone en la misma red Wi-Fi con `HOST=0.0.0.0` y la IP de la PC
> (ej. `http://192.168.1.20:5055`), pero así no se puede instalar a pantalla completa con https.

## 🔥 Porcentaje viral

Cada clip terminado muestra un porcentaje (🔥 alto ≥70 %, ⚡ medio, 💤 bajo). Tócalo para ver el
detalle y consejos. Se calcula con: intensidad del momento (30 %), arranque en los primeros 3 s (20 %),
duración ideal 15-45 s (15 %), hook (15 %), palabras gancho en la transcripción (10 %) y formato
(vertical, subtítulos, portada, marca de agua: 10 %). Es una estimación, no una garantía.
En 🎬 Clips puedes ordenar por **🔥 Más virales**.

## 💾 Mi estilo, 🏷️ texto de contexto y marca @alofokeclips03

- **Mi estilo** (botón 💾 junto a Renderizar): guarda tu configuración en el servidor. La usan los
  lotes y los clips automáticos aunque no abras el editor. Por defecto trae la marca
  **@alofokeclips03** y el texto "● EN VIVO · LA CASA DE ALOFOKE 3".
- **Marca de agua 🛡️ anti-robo**: la marca cambia de lugar cada 7 s para que no la puedan recortar.
- **🏷️ Texto de contexto**: etiqueta pequeña y semitransparente arriba o debajo del video
  (empieza con ● para el punto rojo de "en vivo"). Opción para numerar los lotes: PARTE 1/5…

## ✨ Clips automáticos de los mejores momentos

En **🔴 Directo → Capturar** hay dos botones:
- **🔥 Crear clips CON hook**: busca las tomas más fuertes de los últimos minutos del directo (o de la
  captura abierta) y crea 3, 5, 8 o 10 clips, cada uno con un hook distinto de la categoría elegida.
- **🎬 Crear clips SIN hook**: lo mismo, solo el video limpio.

Usan la configuración del editor (plantilla, formato, subtítulos, marca de agua, efecto al empezar…).
Si hay pocos momentos muy claros, completa con los siguientes mejores.

## 👥 Participantes

En **🎬 Clips → Participantes de La Casa** agrega los nombres (con hashtag y apodos opcionales).
En el editor, **👥 ¿Quién sale?** marca a quienes aparecen: sus nombres van al copy y sus hashtags al
final. Con subtítulos activos, si en el clip se menciona un nombre o apodo de la lista, se marca solo.
En la lista de clips puedes filtrar por participante.
*La app no reconoce caras (reconocimiento facial): las etiquetas son manuales o por nombres mencionados.*

## ⚡ Clips más rápido

- **📍 Marcar momento (tecla `M`)**: mientras ves el directo, aprieta `M` cuando pase algo. Queda
  guardado y luego lo conviertes en clip (con los segundos de "antes" y "después" que elijas).
- **🔎 Buscar tomas importantes**: analiza los últimos 5–30 minutos del directo (o una captura) y
  encuentra los picos de audio: gritos, discusiones, risas, aplausos. Las mejores (🔥🔥🔥) quedan
  marcadas solas.
- **🎬 Crear varios clips a la vez**: marca con ✔ los momentos y aprieta un botón: se capturan y
  renderizan todos con la configuración del editor (hook, plantilla, formato, subtítulos, marca de
  agua, portada). Se renderizan `RENDER_WORKERS` a la vez (2 por defecto) y el resto espera en cola.
- **Velocidad "Rápido"** (por defecto) renderiza más ligero; "Máxima calidad" para clips especiales.

## 🔊 Efectos de sonido

En el editor → **🔊 Efectos de sonido**:
- **Biblioteca de 14 efectos** creados desde cero (sin derechos de terceros): 💥 Boom, 💨 Whoosh,
  🔔 Ding, 😱 Dun dun duuun, 🎺 Trompeta triste, 📣 Bocina, 🦗 Grillos, 😬 Suspenso, ❌ Error, 🫧 Pop,
  🤪 Boing, 🥁 Redoble, 📸 Flash, 📺 Glitch. Se regeneran con `python generar_sonidos.py`.
- Pausa el video donde quieres el efecto → toca el efecto → **➕ Agregar**. Puedes poner varios, con
  volumen, y **🔍 Zoom de impacto** (la imagen se acerca al sonar, ideal con el Boom).
- Los efectos se escuchan al reproducir el video en el editor y se marcan en la barra de recorte.
- **Efecto al empezar cada clip**: se aplica también al crear varios clips a la vez.
- **🎵 Subir mi sonido**: sube tus audios de memes (ej. el "faaah") y quedan en tu biblioteca
  (máx. 15 s, volumen igualado). Mantén presionado uno tuyo para borrarlo. Ojo: los audios de memes
  pueden tener derechos de autor; úsalos bajo tu responsabilidad.

## 🖼 Portada, 💬 subtítulos y 💧 marca de agua

- **Portada**: elige un fotograma ("Usar fotograma actual") y escribe el texto. "Crear portada" saca un
  JPG; "Poner la portada al inicio" la pega como primer cuadro del video (0.35 s), que es lo que
  TikTok toma como portada, y se usa también como portada del Reel en Instagram.
- **Subtítulos** palabra por palabra en 4 estilos (amarillo, verde, caja negra, blanco) y 3
  posiciones. Necesitan `requirements-subtitulos.txt` (el Docker ya los trae).
- **Marca de agua**: texto (@usuario) y/o logo (PNG transparente ideal), con posición, tamaño y
  transparencia. Las posiciones de abajo dejan libre la zona de botones de TikTok/Reels.

## 🚀 Publicar en redes desde Clipper

Toca **🚀** en un clip y elige:
- **Abrir en la app (TikTok, Instagram, Facebook, WhatsApp, Guardar video)**: se copia el copy con
  los hashtags de esa red y se abre el menú de Compartir del iPhone con el video → tocas la app →
  pegas el copy en la descripción. No necesita configurar nada. En computadora: se descarga el
  video, se copia el copy y se abre la página de subida de esa red.
  *(Apple no deja que una página web abra TikTok con el video ya puesto; por eso se elige la app en
  el menú de Compartir, y el copy va copiado porque TikTok no recibe texto por ese camino.)*
- **Publicar automático**: sube directo a tus cuentas conectadas, sin abrir las apps.

| Red | Cómo se publica |
|---|---|
| Facebook | Video en tu **página** (no perfil personal). |
| Instagram | **Reel** en tu cuenta profesional vinculada a la página. Solo con la app en internet. |
| TikTok | A tus **borradores** (terminas en la app de TikTok) o directo. Las apps de TikTok sin auditar solo pueden publicar en privado. |

### Opción A — botones "Conectar" (recomendado)
1. **Meta**: en [developers.facebook.com](https://developers.facebook.com) crea una app tipo
   "Business", agrega *Facebook Login for Business* e *Instagram Graph API*, y registra la dirección
   de retorno `https://TU-APP/oauth/meta/callback`.
2. **TikTok**: en [developers.tiktok.com](https://developers.tiktok.com) crea una app con
   *Login Kit* y *Content Posting API* (permisos `video.upload` y `video.publish`), con retorno
   `https://TU-APP/oauth/tiktok/callback`.
3. En Railway → Variables: `PUBLIC_URL=https://TU-APP`, `META_APP_ID`, `META_APP_SECRET`,
   `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`.
4. En Clipper → **Cuentas para publicar** → Conectar.

### Opción B — pegar tokens
- Facebook/Instagram: en el [Explorador de la Graph API](https://developers.facebook.com/tools/explorer)
  genera un token de usuario con `pages_show_list, pages_manage_posts, pages_read_engagement,
  instagram_basic, instagram_content_publish`, alárgalo en el *Depurador de tokens* ("Extender") y
  consulta `me/accounts`: copia el `id` y el `access_token` de tu página.
- TikTok: token de acceso de tu app de desarrollador.

Los tokens se guardan en el servidor (`cuentas.json` dentro de `/data`) y nunca se muestran en la app.

## Opciones del editor
- **Fondo desenfocado**: el video completo al centro y el mismo video borroso detrás.
- **Pantalla completa (recorte)**: llena la pantalla; mueve "posición" para enfocar a la persona
  que está hablando (izquierda / centro / derecha) y usa zoom si hace falta.
- **Hook** con 10 estilos (TikTok clásico, Viral borde, Amarillo bomba, Última hora, Dos tonos,
  Barra negra, Neón, Fuego, Cómic, Limpio), vista previa en vivo sobre el fotograma real,
  posición arriba/centro/abajo y tamaño. Escribe `*entre asteriscos*` las palabras a resaltar
  en color. Los emojis salen a color.

  ![Estilos de hook](docs/estilos-hook.png)
- **Marca de agua** con tu @.
- Para agregar estilos nuevos edita `STYLES` en `hooks.py` (fuentes en `fonts/`, licencia OFL).

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
5. En **Settings → Networking → Generate Domain**. Listo: entras con tu contraseña.

### Opción B — Render (~7–25 US$/mes)
Sube el repo a GitHub → en [render.com](https://render.com) **New → Blueprint** → elige el repo
(usa `render.yaml`, que ya crea el disco y una contraseña aleatoria; la ves en *Environment*).

### Opción C — Tu propio VPS (Hetzner, DigitalOcean, Contabo…)
```
docker build -t clipper .
docker run -d --restart unless-stopped -p 80:8080 -v clipper-data:/data -e APP_PASSWORD=tuClave clipper
```

### 🍪 Cookies desde el iPhone (sin computadora)
1. Instala **Cookie-Editor** (extensión de Safari) desde el App Store.
2. Ajustes → Apps → Safari → Extensiones → Cookie-Editor: actívala, "Permitir" en todos los sitios y
   "Permitir en navegación privada".
3. En Safari, pestaña privada → youtube.com → entra con una cuenta secundaria.
4. **aA** → Cookie-Editor → Export → JSON (se copian). Cierra la pestaña privada sin cerrar sesión.
5. En Clipper → 🍪 Cookies → **📋 Pegar del portapapeles** → **🔌 Probar conexión**.

Si YouTube bloquea, la grabadora también prueba sola otros tipos de cliente (TV, Safari, móvil) y
recuerda el que funcionó.

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
| `RENDER_WORKERS` | Clips que se renderizan a la vez (2; súbelo si el servidor tiene más CPU) |
| `PUBLIC_URL` | Dirección pública de la app (para Instagram y los botones Conectar) |
| `META_APP_ID` / `META_APP_SECRET` | App de Meta para conectar Facebook/Instagram |
| `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` | App de TikTok para conectar TikTok |
| `ANTHROPIC_API_KEY` | Activa "✨ Copy con IA" |
| `COPY_MODEL` | Modelo de Claude para los copys (por defecto `claude-opus-5-5`) |

Subtítulos en servidor: el Docker los incluye con el modelo `base` (necesita ~2 GB de RAM).
Para un plan más barato, construye sin ellos: `docker build --build-arg SUBTITULOS=0 .`

## Ojo con los derechos
El contenido de La Casa de Alofoke es de sus dueños. Los canales de clips suelen funcionar
porque el canal lo permite o porque agregan valor (comentario, reacción, edición). Si te
llegan reclamos de copyright en TikTok/YouTube, el video se puede caer o la cuenta recibir
strikes; revisa las reglas del canal sobre clips.
