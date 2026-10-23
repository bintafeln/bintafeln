# bintafeln

Freie Verwaltungssoftware für Tafeln – lizenziert unter der
[GNU Affero General Public License v3.0](LICENSE).

> **Stand:** Grundgerüst. Anmeldung, Rollen, Einrichtung, Tafel-Einstellungen und
> Änderungsprotokoll sind vorhanden; die Fachmodule folgen.

## Funktionen des Grundgerüsts

- **Einrichtung im Browser:** Solange es keinen Admin gibt, öffnet sich automatisch
  die Einrichtungsseite. Dort werden der Name der Tafel und das erste Admin-Konto angelegt.
  Danach ist die Seite gesperrt.
- **Rollen:** Admin, Büro, Ausgabe und Kiosk (als Django-Gruppen, werden beim ersten Start
  automatisch angelegt). Benutzer und Rollen verwaltet ein Admin unter „Verwaltung“.
- **Tafel-Einstellungen:** Name, Logo und Anschrift der Tafel – in der Datenbank, nicht im Code.
- **Änderungsprotokoll:** Wer hat wann welchen Datensatz geändert (mit Feldern vorher/nachher).
  Passwörter werden nie protokolliert.
- **Zwei-Faktor (vorbereitet):** Hat ein Konto ein bestätigtes TOTP-Gerät
  (Authenticator-App), wird bei der Anmeldung zusätzlich ein Code verlangt. Geräte legt ein
  Admin derzeit unter „Verwaltung → TOTP devices“ an; eine Selbstverwaltung folgt.
- Deutsche, mobilfreundliche Oberfläche (Django-Templates + HTMX, ohne externe CDNs).

## Aufbau

| Dienst  | Aufgabe |
|---------|---------|
| `app`   | Django-Anwendung (gunicorn). Führt beim Start die Migrationen automatisch aus. |
| `db`    | PostgreSQL 17 |
| `proxy` | Caddy: liefert statische Dateien aus und sorgt im Produktionsmodus für TLS. |

Die gesamte Konfiguration steht in der Datei `.env` (Vorlage: [`.env.example`](.env.example)).

## Installation auf Debian 13 (Trixie) mit Docker

Die folgenden Befehle als Benutzer mit `sudo`-Rechten ausführen.

### 1. Docker installieren

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Optional, damit `docker` ohne `sudo` funktioniert (danach ab- und wieder anmelden):

```bash
sudo usermod -aG docker "$USER"
```

### 2. bintafeln herunterladen

```bash
sudo git clone https://github.com/bintafeln/bintafeln.git /opt/bintafeln
sudo chown -R "$USER": /opt/bintafeln
cd /opt/bintafeln
```

### 3. Konfiguration anlegen

```bash
cp .env.example .env
chmod 600 .env
# Zufällige Schlüssel eintragen:
sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$(openssl rand -hex 32)|" .env
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" .env
```

Weitere Werte (Domain, Ports, Zeitzone) bei Bedarf in `.env` anpassen – siehe Kommentare
in der Datei.

### 4. Starten

```bash
docker compose up -d
```

Der erste Start baut das Image und dauert einige Minuten. Den Zustand zeigt
`docker compose ps`; alle Dienste sollten nach kurzer Zeit laufen (`app` als *healthy*).

### 5. Einrichten

Im Browser `http://<IP-des-Servers>` öffnen. Die Einrichtungsseite erscheint automatisch:
Namen der Tafel und das erste Admin-Konto eintragen. Anschrift und Logo lassen sich danach
unter **Einstellungen** ergänzen.

## Entwicklungs- und Produktionsmodus

Umgeschaltet wird über **eine** Zeile in `.env`:

| `BINTAFELN_DOMAIN` | Modus | Zugriff |
|---|---|---|
| leer | Entwicklung / internes Netz | `http://<IP>` ohne TLS |
| z. B. `tafel.example.org` | Produktion | `https://tafel.example.org` mit automatischem Zertifikat (Let's Encrypt) |

Für den Produktionsmodus:

1. Einen DNS-Eintrag (A/AAAA) der Domain auf den Server zeigen lassen.
2. Ports **80** und **443** aus dem Internet zum Server freigeben (80 wird für die
   Zertifikatsausstellung und die Weiterleitung auf HTTPS gebraucht).
3. `BINTAFELN_DOMAIN=tafel.example.org` in `.env` setzen.
4. `docker compose up -d` ausführen – Caddy holt das Zertifikat selbstständig.

Im Produktionsmodus setzt bintafeln zusätzlich sichere Cookies und HSTS und nimmt
Anfragen nur noch für die eingetragene Domain an.

> Der Entwicklungsmodus überträgt Passwörter unverschlüsselt. Er ist nur für Tests oder ein
> abgeschottetes internes Netz gedacht.

## Betrieb

```bash
docker compose ps                 # Zustand der Dienste
docker compose logs -f app        # Protokoll der Anwendung
docker compose down               # anhalten (Daten bleiben erhalten)
```

**Aktualisieren:**

```bash
cd /opt/bintafeln
git pull
docker compose up -d --build      # Migrationen laufen beim Start automatisch
```

**Datensicherung der Datenbank:**

```bash
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > bintafeln-$(date +%F).sql
```

Hochgeladene Dateien (z. B. das Logo) liegen im Docker-Volume `bintafeln_media`.

**Wiederherstellen** (in eine leere Datenbank):

```bash
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"' < bintafeln-JJJJ-MM-TT.sql
```

## Entwicklung

Voraussetzungen: Python 3.12+, eine erreichbare PostgreSQL-Datenbank.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

# Tests (erwartet PostgreSQL auf localhost, Benutzer "bintafeln" mit Recht CREATEDB;
# Passwort über POSTGRES_PASSWORD, Standard in bintafeln/settings_test.py)
.venv/bin/pytest

# Linter
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Einen passenden Datenbank-Container für die Tests startet z. B.:

```bash
docker run -d --name bintafeln-testdb -p 5432:5432 \
  -e POSTGRES_USER=bintafeln -e POSTGRES_PASSWORD=nur-lokal-test postgres:17-alpine
```

GitHub Actions führt bei jedem Pull Request ruff, pytest und einen Docker-Build aus.

### Verzeichnisstruktur

```
bintafeln/          Django-Projekt (Einstellungen, URLs)
apps/core/          Tafel-Einstellungen, Einrichtung, Startseite, Änderungsprotokoll
apps/konten/        Benutzer, Rollen, Anmeldung mit optionalem Zwei-Faktor
templates/          Django-Templates
static/             CSS und HTMX
docker/             Caddyfile und Start-Skript des App-Containers
tests/              pytest-Tests
```

## Grundsätze

- Keine echten Daten, Passwörter oder Schlüssel im Repository – `.env` ist ausgeschlossen.
- Keine festen IP-Adressen, Pfade oder Tafel-Namen im Code; alles kommt aus `.env` oder der
  Datenbank.

## Lizenz

bintafeln ist freie Software unter der [GNU AGPL v3.0](LICENSE). Wer eine veränderte Version
als Netzdienst betreibt, muss den Nutzerinnen und Nutzern den Quelltext zugänglich machen.
