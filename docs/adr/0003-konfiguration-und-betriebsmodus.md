# 0003: Konfiguration über .env, Betriebsmodus über die Domain

- Status: Angenommen
- Datum: 2026-10-23

## Problem

Jede Installation braucht eigene Werte (Schlüssel, Passwörter, Domain). Außerdem soll man
bintafeln ohne Domain und Zertifikat im internen Netz ausprobieren können, im Echtbetrieb aber
TLS erzwingen.

## Entscheidung

- Alle installationsspezifischen Werte stehen in **`.env`**. Die Vorlage `.env.example` enthält
  nur Platzhalter und wird mit eingecheckt, `.env` selbst nie.
- Pflichtwerte (`DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`) haben **keinen Standardwert**. Fehlen
  sie, startet nichts, und die Fehlermeldung sagt, was fehlt.
- **Eine Variable schaltet den Modus:** `BINTAFELN_DOMAIN`.
  - leer: Entwicklungsmodus, Zugriff über `http://IP`, kein TLS
  - gesetzt: Produktionsmodus, Caddy holt ein Zertifikat und leitet HTTP auf HTTPS um, Django
    setzt sichere Cookies und HSTS und akzeptiert nur noch die Domain

## Begründung

- Ein einziger Schalter verhindert widersprüchliche Kombinationen (z. B. TLS bei Caddy, aber
  unsichere Cookies in Django).
- Keine Standardpasswörter bedeutet: Es gibt keine Installation mit einem öffentlich
  bekannten Passwort.

## Folgen

- Der Entwicklungsmodus überträgt Passwörter unverschlüsselt und ist nur für Tests und
  abgeschottete Netze gedacht. Die README weist darauf hin.
