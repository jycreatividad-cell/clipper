FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core curl unzip ca-certificates \
 && curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh -s -- -y \
 && apt-get purge -y unzip && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-subtitulos.txt ./
ARG SUBTITULOS=1
RUN pip install --no-cache-dir -r requirements.txt gunicorn \
 && if [ "$SUBTITULOS" = "1" ]; then pip install --no-cache-dir -r requirements-subtitulos.txt; fi

COPY app.py hooks.py templates.py ./
COPY fonts ./fonts
COPY static ./static

ENV DATA_DIR=/data \
    HOST=0.0.0.0 \
    PORT=8080 \
    NO_BROWSER=1 \
    WHISPER_MODEL=base \
    PYTHONUNBUFFERED=1
RUN mkdir -p /data
EXPOSE 8080

# 1 solo worker: la grabadora y los trabajos viven en memoria
CMD gunicorn -w 1 -k gthread --threads 16 --timeout 0 -b 0.0.0.0:${PORT} app:app
