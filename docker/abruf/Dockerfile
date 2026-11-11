# Dienst "abruf" (ADR 0127): Browser für den Abruf aus dem Vereinsportal. Läuft nur mit dem
# Compose-Profil "abruf"; bintafeln selbst bekommt keinen Browser.
FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/browser

# Dieselbe Playwright-Version wie die Browser-Tests (requirements-e2e.txt)
RUN pip install --no-cache-dir playwright==1.64.1 \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home abruf

COPY abruf.py /usr/local/bin/abruf.py

USER abruf
EXPOSE 8700
CMD ["python", "/usr/local/bin/abruf.py"]
