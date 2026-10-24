# Demoversion einrichten

Die Demo ist eine **eigene, vollständig getrennte Installation** von bintafeln. Sie hat einen
eigenen Ordner, eigene Container, eine eigene Datenbank und eine eigene `.env`. Mit einer echten
Tafel teilt sie nichts; sie enthält nur erfundene Daten und wird jede Nacht zurückgesetzt
(ADR 0022).

Es gibt zwei Wege:

- **A. Zum Ausprobieren** auf der Dummy-Tafel oder einem anderen Rechner im eigenen Netz, ohne
  Domain, erreichbar unter `http://IP:8080`. Die Dummy-Tafel läuft daneben unverändert weiter.
- **B. Öffentlich im Internet** unter einer eigenen Domain, z. B. `demo.example.org`, mit TLS.

Voraussetzung für beide: Docker ist installiert (README, „Installation“, Schritt 1).

---

## A. Demo zum Ausprobieren (ohne Domain)

### 1. Eigenen Ordner anlegen

Die Demo bekommt einen **eigenen Ordner**. Am einfachsten als Kopie des Ordners der
bestehenden Installation, dann braucht es keine neuen GitHub-Zugangsdaten (Beispiel: die
Dummy-Tafel liegt in `~/bintafeln`):

```bash
git clone ~/bintafeln ~/bintafeln-demo \
  && git -C ~/bintafeln-demo remote set-url origin "$(git -C ~/bintafeln remote get-url origin)" \
  && cd ~/bintafeln-demo && pwd
```

Die letzte Zeile der Ausgabe muss `.../bintafeln-demo` lauten. **Nur weitermachen, wenn das so
ist** – sonst würden die folgenden Schritte die bestehende Installation verändern.

(Ohne bestehende Installation: `git clone https://github.com/bintafeln/bintafeln.git
~/bintafeln-demo`. Solange das Repository privat ist, verlangt GitHub dabei statt des
Passworts einen *Personal Access Token*.)

### 2. Konfiguration anlegen

Der Befehl bricht ab und ändert nichts, wenn er nicht im Demo-Ordner läuft oder dort schon
eine `.env` liegt:

```bash
[ "$(basename "$PWD")" = bintafeln-demo ] && [ ! -e .env ] \
  && cp .env.example .env && chmod 600 .env \
  && sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$(openssl rand -hex 32)|" .env \
  && sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" .env \
  && echo "OK: .env angelegt" || echo "ABBRUCH: falscher Ordner oder .env existiert schon"
```

Dann `.env` öffnen (z. B. `nano .env`) und diese Werte setzen:

```
COMPOSE_PROJECT_NAME=demo
HTTP_PORT=8080
HTTPS_PORT=8443
BINTAFELN_DEMO=true
BINTAFELN_DEMO_PASSWORT=demo-2026
```

- `COMPOSE_PROJECT_NAME=demo` trennt die Demo von der Dummy-Tafel. Ohne diese Zeile würden
  sich beide in die Quere kommen.
- Die Ports 8080/8443, weil 80/443 schon von der Dummy-Tafel belegt sind.
- Das Demo-Passwort steht später für alle sichtbar auf der Anmeldeseite. Kein Passwort
  verwenden, das woanders benutzt wird.
- Keinen Sicherungsschlüssel eintragen: Die Demo braucht keine Sicherung.

### 3. Starten und mit Beispieldaten füllen

```bash
docker compose up -d --wait
docker compose exec -T app python manage.py demo_zuruecksetzen
```

Der erste Start dauert einige Minuten. Der zweite Befehl meldet am Ende
„Demo zurückgesetzt. Konten: demo-admin, …“.

### 4. Aufrufen

Im Browser `http://<IP-des-Servers>:8080` öffnen. Oben steht der Hinweis „Demoversion“, auf der
Anmeldeseite stehen die Zugänge:

| Konto | Rolle | zeigt |
|---|---|---|
| `demo-admin` | Admin | alles, auch Einstellungen |
| `demo-buero` | Büro | Kunden mit allen Angaben, Kasse, Auskunft, Kundenausweis |
| `demo-ausgabe` | Ausgabe | Einlass mit Ampel, Kasse |
| `demo-personal` | Personal | Personal, Urlaub, Stundenkonto, Arbeitszeiten |
| `demo-fest` | Ausgabe und Fahrer, fest angestellt | „Meine Arbeitszeit“ mit Stempeln |

Das Passwort ist für alle Konten das aus `BINTAFELN_DEMO_PASSWORT`. Am Einlass z. B. die
Kundennummer `1001` eingeben.

### 5. Jede Nacht zurücksetzen (optional)

```bash
crontab -e
```

und diese Zeile anfügen (täglich um 3:15 Uhr):

```
15 3 * * * cd ~/bintafeln-demo && docker compose exec -T app python manage.py demo_zuruecksetzen > /dev/null
```

Der Benutzer braucht dafür Docker-Rechte (Gruppe `docker`, siehe README). Von Hand geht das
Zurücksetzen jederzeit mit dem Befehl aus Schritt 3.

---

## B. Öffentliche Demo unter einer eigenen Domain

Auf dem Server laufen dann ein **gemeinsamer Proxy** (er hält die Ports 80 und 443 und holt
die Zertifikate), die Demo und auf Wunsch weitere Installationen und eine Webseite. Jede bleibt
für sich getrennt.

### 1. DNS

Beim Domain-Anbieter für `demo.example.org` (und ggf. `example.org`, `www.example.org`) einen
**A-Eintrag** auf die IP-Adresse des Servers anlegen. Es kann einige Minuten bis Stunden dauern,
bis er gilt; prüfen mit `ping demo.example.org`.

In der Firewall des Servers bzw. beim Hoster die Ports **80 und 443** freigeben.

### 2. Demo herunterladen und konfigurieren

Wie oben in **A, Schritte 1 und 2**, aber in der `.env` statt der Ports diese Werte setzen:

```
BINTAFELN_DOMAIN=demo.example.org
COMPOSE_PROJECT_NAME=demo
COMPOSE_FILE=docker-compose.yml:docker/hinter-proxy.yml
BINTAFELN_DEMO=true
BINTAFELN_DEMO_PASSWORT=ein-eigenes-demo-passwort
```

`COMPOSE_FILE` hängt die Demo hinter den gemeinsamen Proxy: Sie belegt selbst keine Ports und
macht kein eigenes TLS.

### 3. Gemeinsamen Proxy einrichten (einmal je Server)

```bash
cd ~/bintafeln-demo/docker/gemeinsamer-proxy
cp Caddyfile.beispiel Caddyfile
nano Caddyfile
```

Im `Caddyfile` die Beispiel-Domains ersetzen. Für nur die Demo genügt:

```
demo.example.org {
	reverse_proxy demo:80
}
```

`demo` ist der `COMPOSE_PROJECT_NAME` aus Schritt 2. Eine Webseite unter `example.org` kommt als
eigener Block dazu (siehe Beispiel in der Datei); ihre Dateien gehören in den Ordner
`webseite/` daneben.

```bash
docker compose up -d
```

### 4. Demo starten und füllen

```bash
cd ~/bintafeln-demo
docker compose up -d --wait
docker compose exec -T app python manage.py demo_zuruecksetzen
```

### 5. Aufrufen

`https://demo.example.org` öffnen. Das Zertifikat holt der gemeinsame Proxy beim ersten Aufruf
selbst (dauert einige Sekunden). Anmelden wie in **A, Schritt 4**.

### 6. Jede Nacht zurücksetzen

Wie in **A, Schritt 5**.

---

## Später: weitere Tafel auf demselben Server

Eine echte Tafel kommt genauso dazu: eigener Ordner (z. B. `~/bintafeln-tafel`), in der `.env`
`BINTAFELN_DOMAIN`, `COMPOSE_PROJECT_NAME=tafel` und dieselbe `COMPOSE_FILE`-Zeile, aber
**ohne** `BINTAFELN_DEMO`. Im `Caddyfile` des gemeinsamen Proxys einen Block
`tafel.example.org { reverse_proxy tafel:80 }` ergänzen und dort `docker compose restart`
ausführen. Für die echte Tafel die Sicherung einrichten (`./betrieb schluessel`).

## Wenn etwas nicht klappt

| Problem | Lösung |
|---|---|
| `Nur im Demo-Betrieb (BINTAFELN_DEMO=true) erlaubt` | In der `.env` der Demo `BINTAFELN_DEMO=true` setzen, dann `docker compose up -d` und erneut versuchen. |
| `BINTAFELN_DEMO_PASSWORT fehlt` | Passwort in der `.env` eintragen, `docker compose up -d`. |
| `network bintafeln-web declared as external, but could not be found` | Zuerst den gemeinsamen Proxy starten (B, Schritt 3). |
| Port 80 oder 8080 schon belegt | Andere Ports in `HTTP_PORT`/`HTTPS_PORT` wählen (Variante A). |
| Seite zeigt „Bad Request (400)“ | `BINTAFELN_DOMAIN` stimmt nicht mit der aufgerufenen Adresse überein. |
| Kein Zertifikat | DNS zeigt noch nicht auf den Server, oder Ports 80/443 sind gesperrt; Protokoll: `docker compose logs caddy` im Ordner des gemeinsamen Proxys. |
| `Abbruch: Diese Datenbank enthält Konten, die nicht aus der Demo stammen` | Der Befehl läuft im Ordner einer echten Installation. Nichts wurde gelöscht. In den Demo-Ordner wechseln. |
| Ein Demo-Konto funktioniert nicht mehr (z. B. gesperrt) | `demo_zuruecksetzen` von Hand ausführen. |

Aktualisiert wird die Demo wie jede Installation mit `./betrieb update` in ihrem Ordner; danach
einmal `demo_zuruecksetzen`.
