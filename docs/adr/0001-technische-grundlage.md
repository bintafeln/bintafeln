# 0001: Technische Grundlage

- Status: Angenommen
- Datum: 2026-10-23

## Problem

bintafeln soll über viele Jahre wartbar bleiben und später von wechselnden Freiwilligen der
nutzenden Tafeln gepflegt werden. Betrieben wird es auf kleinen Servern mit wenig
Administrationsaufwand.

## Entscheidung

- **Python mit Django in der jeweils aktuellen LTS-Version** (derzeit 5.2)
- **PostgreSQL** als einzige Datenbank
- **Oberfläche serverseitig** mit Django-Templates und **HTMX**, kein separates
  JavaScript-Framework, keine externen CDNs (HTMX wird mitgeliefert)
- **Auslieferung per Docker Compose** mit drei Diensten: `app` (gunicorn), `db` (PostgreSQL),
  `proxy` (Caddy)
- **Drucken ausschließlich über erzeugte PDFs**
- **Tests mit pytest, Linter ruff**, beides in GitHub Actions bei jedem Pull Request
- **Abhängigkeiten mit festen Versionen** in `requirements.txt`

## Begründung

- Django-LTS-Versionen erhalten drei Jahre Sicherheitsupdates. Das Framework bringt Anmeldung,
  Formulare, Migrationen und Verwaltung mit und ist weit verbreitet, Helfende finden sich leicht.
- PostgreSQL ist robust, frei und für die Datenmengen einer Tafel mehr als ausreichend.
- Serverseitiges Rendern mit HTMX hält die Oberfläche schlank: kein Build-Schritt fürs Frontend,
  keine zweite Programmiersprache mit eigenem Paket-Ökosystem, weniger Abhängigkeiten.
- Docker Compose macht Installation und Update auf jedem Linux-Server gleich. Caddy erledigt
  TLS-Zertifikate ohne Zusatzaufwand.
- PDFs sehen auf jedem Drucker gleich aus und lassen sich archivieren.

## Folgen

- Interaktive Oberflächen (z. B. Kiosk) werden mit HTMX und wenig eigenem JavaScript gebaut.
- Beim Wechsel der Django-LTS-Version (alle zwei Jahre) ist ein eigener Pull Request nötig.
