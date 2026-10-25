# Übernahme der bisherigen Zusatzprogramme

Einige Tafeln betreiben neben bintafeln eigene kleine Programme. Sie gehen Schritt für Schritt
als **zuschaltbare Module** (ADR 0049) in bintafeln auf. Die Daten kommen dann direkt aus
bintafeln; Downloads aus Fremdsystemen und der Austausch von Dateien entfallen.

| Bisheriges Programm | In bintafeln | Stand |
|---|---|---|
| Kundennummern-Aufruf (Monitor, Handy, Kiosk) | Modul **Aufruf** (ADR 0050) | umgesetzt |
| Neuanmeldungen / Warteliste mit Einladungen | Modul **Warteliste** auf den Anträgen (ADR 0051) | umgesetzt |
| Wochenübersicht der Ausgabestellen (Soll/Ist, Selbstabholer) | Modul **Wochenübersicht** (ADR 0054) | umgesetzt |
| Spendenbelege und Dankesbriefe | Spenden-Import (ADR 0055), Dankesbriefe mit Belegen (ADR 0056) | umgesetzt |
| Übersicht (Linkliste) | Startseite/Menü | geplant |
| Guthaben-Überwachung von Prepaid-Karten | nicht in bintafeln (kein Tafel-Thema) | – |

Reverse-Proxy und vorgeschaltete Anmeldung der bisherigen Programme braucht es nicht: bintafeln
bringt Caddy, Anmeldung mit Zwei-Faktor und Rechte mit.

Regeln für jedes Modul:

- Eigene App mit `modul.py`; Kern ohne Sonderfälle (ADR 0049).
- Aussehen der Bildschirme, die im Netz der Tafel aufgerufen werden, bleibt wie bisher.
- Keine festen Werte (Namen, Anschriften, Orte) – alles aus den Einstellungen.
- Keine Personendaten, Passwörter oder Listen aus den bisherigen Programmen im Repository.
