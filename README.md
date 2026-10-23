# bintafeln

Freie Verwaltungssoftware für Tafeln – lizenziert unter der
[GNU Affero General Public License v3.0](LICENSE).

> **Stand:** Grundgerüst. Anmeldung, Rollen, Einrichtung, Tafel-Einstellungen,
> Änderungsprotokoll und Sicherung sind vorhanden; die Fachmodule folgen.

## Funktionen des Grundgerüsts

- **Einrichtung im Browser:** Solange es keinen Admin gibt, öffnet sich automatisch
  die Einrichtungsseite. Dort werden der Name der Tafel und das erste Admin-Konto angelegt.
  Danach ist die Seite gesperrt.
- **Rollen:** Admin, Büro, Ausgabe und Kiosk (als Django-Gruppen, werden beim ersten Start
  automatisch angelegt). Benutzer und Rollen verwaltet ein Admin unter „Verwaltung“.
- **Tafel-Einstellungen:** Name, Logo und Anschrift der Tafel – in der Datenbank, nicht im Code.
- **Änderungsprotokoll:** Wer hat wann welchen Datensatz geändert (mit Feldern vorher/nachher).
  Passwörter werden nie protokolliert.
- **Zwei-Faktor-Anmeldung:** Jede Person richtet sie unter „Mein Konto“ selbst ein
  (QR-Code für die Authenticator-App, dazu 10 Notfallcodes). Für welche Rollen sie Pflicht ist,
  legt ein Admin unter „Einstellungen“ fest; voreingestellt sind Admin und Büro.
- **Sicherung:** täglich und verschlüsselt, mit Wiederherstellung und Update per Befehl
  (`./betrieb`). Die Startseite zeigt Admins den Stand der Sicherung.
- **Kundenstamm (im Aufbau):** Datenmodell für Haushalte, Personen, Abholberechtigte, Sperren,
  Bemerkungen und Kundengruppen. Unter „Einstellungen → Kundenstamm“ legt ein Admin fest, welche
  Angaben erfasst werden, und richtet eigene **Zusatzfelder** ein (z. B. „Schwerbehindert“).
  **Import** mit Prüfbericht unter „Kunden“; Liste und Suche folgen.
- Deutsche, mobilfreundliche Oberfläche (Django-Templates + HTMX, ohne externe CDNs).

## Aufbau

| Dienst  | Aufgabe |
|---------|---------|
| `app`   | Django-Anwendung (gunicorn). Führt beim Start die Migrationen automatisch aus. |
| `db`    | PostgreSQL 17 |
| `proxy` | Caddy: liefert statische Dateien aus und sorgt im Produktionsmodus für TLS. |
| `backup` | Tägliche, verschlüsselte Sicherung von Datenbank und hochgeladenen Dateien. |

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
Namen der Tafel und das erste Admin-Konto eintragen. Direkt danach richtet der Admin die
[Zwei-Faktor-Anmeldung](#zwei-faktor-anmeldung) ein; dafür eine Authenticator-App auf dem Handy
bereithalten. Anschrift und Logo lassen sich danach unter **Einstellungen** ergänzen.

### 6. Sicherung einrichten

```bash
./betrieb schluessel
```

Den angezeigten privaten Schlüssel sicher und getrennt vom Server aufbewahren, siehe
[Sicherung einrichten](#sicherung-einrichten).

## Zwei-Faktor-Anmeldung

Bei der Anmeldung wird zusätzlich zum Passwort ein 6-stelliger Code aus einer
Authenticator-App verlangt (z. B. Aegis, FreeOTP, Google Authenticator).

- **Einrichten:** „Mein Konto“ → „Jetzt einrichten“, QR-Code scannen, Code eingeben. Danach
  erscheinen einmalig **10 Notfallcodes**. Jeder funktioniert einmal anstelle der App.
- **Pflicht je Rolle:** unter „Einstellungen“ per Häkchen. Voreingestellt: Admin und Büro.
  Wer eine Pflicht-Rolle hat, wird nach der Anmeldung direkt zur Einrichtung geleitet und kann
  bis dahin nichts anderes öffnen. Auch der erste Admin richtet sie direkt nach der
  Einrichtungsseite ein.
- **Handy verloren:**
  1. mit einem Notfallcode anmelden und unter „Mein Konto“ neu einrichten, oder
  2. ein Admin löscht unter „Verwaltung → TOTP devices“ das Gerät der Person, oder
  3. als letzter Ausweg auf dem Server, falls sich kein Admin mehr anmelden kann:

     ```bash
     docker compose exec app python manage.py zwei_faktor_zuruecksetzen BENUTZERNAME
     ```

Einrichten und Entfernen stehen im Änderungsprotokoll, Schlüssel und Codes nie.

## Kundenstamm importieren

Der Kundenstamm wird aus dem bisherigen Programm übernommen, im
[offenen Importformat](docs/importformat.md). Jeder Import ersetzt den Bestand vollständig.

1. Vorher unter „Einstellungen → Kundenstamm“ festlegen, welche Angaben erfasst werden, und
   benötigte **Zusatzfelder** anlegen (ihre Schlüssel bestimmen die Spalten `zusatz_…`).
2. „Kunden“ → „Neuen Stand importieren“ → CSV-Dateien auswählen → **Prüfen**.
3. Der **Prüfbericht** nennt Fehler (Import nicht möglich) und Warnungen (Import möglich), jeweils
   mit Datei und Zeile, aber ohne Inhalte.
4. Ohne Fehler: Vorschau mit „bisher / nach dem Import“ ansehen und **Import übernehmen**.

Regeln:

- Übernehmen geht nur, wenn die letzte erfolgreiche Sicherung höchstens **24 Stunden** alt ist
  (sonst vorher `./betrieb sichern`).
- Die geprüften Daten liegen bis zur Bestätigung höchstens **eine Stunde** in der Datenbank und
  werden danach, beim Übernehmen oder beim Verwerfen gelöscht. Die hochgeladenen Dateien selbst
  werden nicht gespeichert.
- Jeder Import erscheint im Änderungsprotokoll und unter „Kunden“ (wer, wann, wie viele
  Datensätze), nicht jeder einzelne Datensatz.
- Importieren dürfen Admin und Büro.
- Abholungen und Ausnahmen werden nur innerhalb der **Aufbewahrungsfrist** übernommen
  („Einstellungen → Kundenstamm“, Vorgabe 3 Jahre). Ältere löscht bintafeln automatisch.

## Kunden ansehen

Unter „Kunden“ stehen alle Haushalte des Kundenstamms, nur zum Lesen.

- **Suche** nach Kundennummer oder Name; Status und Kundengruppe lassen sich filtern. Eine
  vollständige Kundennummer mit Enter (z. B. vom Scanner) öffnet den Haushalt direkt.
- Die **Detailseite** zeigt je nach Rolle unterschiedlich viel:

  | Rolle | sieht |
  |---|---|
  | Admin, Büro | alles: Anschrift, Kontakt, Personen, Abholberechtigte, alle Sperren, Ausnahmen, Abholungen, Kontostand, Bemerkungen, Zusatzfelder |
  | Ausgabe | Name, Status, Kundengruppe, Haushaltsgröße, Ausweis, aktive Sperren, Ausnahmen, die letzten 5 Abholungen, Zusatzfelder (Art. 9 nur mit Freigabe in den Einstellungen) |
  | Kiosk | nichts |

- Jeder Aufruf einer Detailseite steht im **Zugriffsprotokoll** („Kunden“ → „Zugriffsprotokoll“,
  nur Admin). Die Einträge werden nach 365 Tagen gelöscht, einstellbar unter
  „Einstellungen → Kundenstamm“.

## Empfang

„Empfang“ im Menü (Admin, Büro, Ausgabe):

1. Einmal die **Ausgabestelle** wählen, an der man arbeitet (gilt für die Sitzung).
2. Kundennummer **scannen** oder eintippen und Enter. Führende Nullen sind egal.
3. Die **Ampel** zeigt, ob abgeholt werden darf, und warum nicht:
   - 🔴 Sperre, Status gesperrt/beendet, Ausweis abgelaufen, heute schon abgeholt, Höchstzahl
     erreicht, keine Kundengruppe, heute nicht dran (einstellbar rot oder gelb)
   - 🟡 Ausweis läuft bald ab oder fehlt, andere Ausgabestelle, Status pausiert
   - 🟢 alles in Ordnung, oder eine Ausnahme für heute hebt eine Terminregel auf
4. **Abholung eintragen**; der Beitrag ist vorgeschlagen und änderbar. Ein Versehen lässt sich am
   selben Tag zurücknehmen. Admin und Büro können bei Rot wegen einer Terminregel eine
   **Ausnahme für heute** erteilen.

Die Regeln stehen unter „Einstellungen → Ausgabe und Ampel“. Jeder Scan steht im
Zugriffsprotokoll. **Achtung:** Ein neuer Import des Kundenstamms ersetzt auch die am Empfang
eingetragenen Abholungen und Ausnahmen; der Prüfbericht warnt davor (ADR 0013).

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

Alle Betriebsaufgaben erledigt das Werkzeug `./betrieb` im Projektordner:

```bash
./betrieb status                  # Dienste, letzte Sicherung, vorhandene Sicherungen
./betrieb update                  # sichern, neuen Stand holen, neu bauen, starten
./betrieb sichern                 # sofort sichern
./betrieb schluessel              # Schlüsselpaar für die Sicherungen erzeugen
./betrieb wiederherstellen NAME   # eine Sicherung zurückspielen
```

Weitere nützliche Befehle:

```bash
docker compose logs -f app        # Protokoll der Anwendung
docker compose logs backup        # Protokoll der Sicherungen
docker compose down               # anhalten (Daten bleiben erhalten)
```

### Sicherung einrichten

Der Dienst `backup` sichert jeden Tag die Datenbank und die hochgeladenen Dateien
(Uhrzeit, Anzahl und Ablageort stehen in `.env`). Die Sicherungen werden mit
[age](https://age-encryption.org) verschlüsselt. Auf dem Server liegt nur der **öffentliche**
Schlüssel. Wer den Server oder die Sicherungen stiehlt, kann sie also nicht lesen. Ohne
Schlüssel wird nicht gesichert, unverschlüsselt wird nie gesichert.

Einmalig einrichten:

```bash
./betrieb schluessel
```

Das Werkzeug trägt den öffentlichen Schlüssel in `.env` ein und zeigt den **privaten**
Schlüssel an (eine Zeile, beginnt mit `AGE-SECRET-KEY-`). Diese Zeile:

- **nicht auf dem Server speichern**, sondern getrennt aufbewahren: im Passwortmanager,
  ausgedruckt im Tresor oder auf einem USB-Stick, am besten an zwei Orten;
- wird nur zum Wiederherstellen gebraucht. **Ohne sie lassen sich die Sicherungen nicht öffnen.**

Danach zeigt die Startseite allen Admins, wann zuletzt gesichert wurde, und warnt, wenn die
letzte erfolgreiche Sicherung älter als zwei Tage ist.

Jede Sicherung ist ein Ordner in `sicherungen/` (z. B. `2026-01-31_023000`) mit
`datenbank.dump.age`, `medien.tar.age` und `info.txt`. Ältere Stände als
`BINTAFELN_SICHERUNG_ANZAHL` werden automatisch gelöscht.

### Sicherungen auf einen anderen Rechner kopieren

Eine Sicherung auf demselben Server schützt nicht vor einem Plattenschaden oder Verlust des
Servers. Kopieren Sie den Ordner `sicherungen/` regelmäßig an einen anderen Ort. Weil die Dateien
verschlüsselt sind, darf das auch ein fremder Speicher sein. Beispiel mit `rsync` von einem
anderen Linux-Rechner aus, täglich per Cronjob:

```bash
rsync -a --delete benutzer@tafel-server:/opt/bintafeln/sicherungen/ /pfad/zu/tafel-sicherungen/
```

### Wiederherstellen

1. Die Zeile mit dem privaten Schlüssel in eine Datei auf dem Server schreiben,
   z. B. `schluessel.txt` (nach dem Wiederherstellen wieder löschen).
2. Die gewünschte Sicherung aussuchen: `./betrieb status`
3. Wiederherstellen:

   ```bash
   ./betrieb wiederherstellen 2026-01-31_023000 --schluessel schluessel.txt
   rm schluessel.txt
   ```

Das Werkzeug prüft zuerst, ob sich die Sicherung mit dem Schlüssel öffnen lässt, fragt nach,
**sichert den aktuellen Stand** und ersetzt dann Datenbank und hochgeladene Dateien vollständig.
Danach startet die Anwendung wieder, Migrationen laufen automatisch.

Auf einem **neuen Server**: bintafeln wie oben installieren, den Ordner `sicherungen/`
dorthin kopieren und dann wie beschrieben wiederherstellen.

### Aktualisieren

```bash
cd /opt/bintafeln
./betrieb update
```

Das Werkzeug sichert zuerst, holt dann den neuen Stand, aktualisiert die Images und startet neu.
Migrationen laufen beim Start automatisch.

> **Einmalig beim Wechsel auf diese Version:** Das Werkzeug `./betrieb` gibt es erst ab hier.
> Deshalb dieses eine Mal `git pull && docker compose up -d --build` ausführen, danach
> `./betrieb schluessel`. Ab dann genügt `./betrieb update`.

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

GitHub Actions führt bei jedem Pull Request ruff, shellcheck und pytest aus und spielt mit
`tests/sicherung_e2e.sh` eine echte Sicherung und Wiederherstellung im Docker-Aufbau durch.
Dieses Skript überschreibt `.env`, lokal also nur in einer Wegwerf-Kopie starten.

### Verzeichnisstruktur

```
bintafeln/          Django-Projekt (Einstellungen, URLs)
apps/core/          Tafel-Einstellungen, Einrichtung, Startseite, Änderungsprotokoll
apps/konten/        Benutzer, Rollen, Anmeldung, Zwei-Faktor
apps/kunden/        Kundenstamm: Haushalte, Personen, Zusatzfelder, Einstellungen
templates/          Django-Templates
static/             CSS und HTMX
docker/             Caddyfile und Start-Skript des App-Containers
docker/backup/      Dienst "backup" (Sicherungsskript)
betrieb             Betriebswerkzeug: Update, Sicherung, Wiederherstellung
docs/adr/           Architekturentscheidungen (warum bintafeln so gebaut ist)
docs/               fachkonzept.md (kommende Module), importformat.md (Import des
                    Kundenstamms), beispiele/ mit erfundenen Beispieldateien
tests/              pytest-Tests und Ende-zu-Ende-Test der Sicherung
```

## Grundsätze

- Keine echten Daten, Passwörter oder Schlüssel im Repository – `.env` ist ausgeschlossen.
- Keine festen IP-Adressen, Pfade oder Tafel-Namen im Code; alles kommt aus `.env` oder der
  Datenbank.

## Lizenz

bintafeln ist freie Software unter der [GNU AGPL v3.0](LICENSE). Wer eine veränderte Version
als Netzdienst betreibt, muss den Nutzerinnen und Nutzern den Quelltext zugänglich machen.
