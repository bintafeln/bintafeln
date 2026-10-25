FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=bintafeln.settings \
    BINTAFELN_STATIC_ROOT=/app/data/static \
    BINTAFELN_MEDIA_ROOT=/app/data/media

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN groupadd --system --gid 1000 bintafeln \
    && useradd --system --uid 1000 --gid bintafeln --home /app bintafeln \
    && mkdir -p /app/data/static /app/data/media /app/data/betrieb \
    && chown -R bintafeln:bintafeln /app/data

COPY --chown=bintafeln:bintafeln . .
RUN chmod +x docker/entrypoint.sh

USER bintafeln

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz/', timeout=4)"

ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["gunicorn", "bintafeln.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--no-control-socket", "--access-logfile", "-"]
