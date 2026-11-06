FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=bintafeln.settings \
    BINTAFELN_STATIC_ROOT=/app/data/static \
    BINTAFELN_MEDIA_ROOT=/app/data/media

WORKDIR /app

# Tesseract-OCR für die lokale Ausweisprüfung (ADR 0107). Englisch für die MRZ (lateinische
# Großbuchstaben/Ziffern) und Deutsch, um Amtsdokumente (Bescheide) am Text zu erkennen (ADR 0112).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-deu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN groupadd --system --gid 1000 bintafeln \
    && useradd --system --uid 1000 --gid bintafeln --home /app bintafeln \
    && mkdir -p /app/data/static /app/data/media /app/data/betrieb /app/data/fernsicherung \
    && chown -R bintafeln:bintafeln /app/data

COPY --chown=bintafeln:bintafeln . .
RUN chmod +x docker/entrypoint.sh

USER bintafeln

EXPOSE 8000

# Mit gesetzter Domain nimmt Django nur Anfragen an diese Domain an (ALLOWED_HOSTS), daher als Host
# die Domain mitschicken; ohne Domain (Entwicklungsmodus) gilt jeder Name.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request as u; u.urlopen(u.Request('http://127.0.0.1:8000/healthz/', headers={'Host': os.environ.get('BINTAFELN_DOMAIN') or 'localhost'}), timeout=4)"

ENTRYPOINT ["docker/entrypoint.sh"]
# Worker-Zahl, Timeout und Worker-Recycling kommen aus bintafeln/gunicorn.conf.py und lassen sich
# über die .env an die Servergröße anpassen (ADR 0111).
CMD ["gunicorn", "bintafeln.wsgi:application", "--config", "bintafeln/gunicorn.conf.py", "--no-control-socket"]
