# 0143: Liste aller Notizen

- Status: Angenommen
- Datum: 2026-11-17
- Ergänzt: ADR 0026 (Notizen), ADR 0034 (Zuordnung zu Ausgabestellen), ADR 0073 (Papierkorb)

## Problem

Notizen zu Kunden stehen nur beim jeweiligen Haushalt (und am Einlass). Die Verwaltung konnte
nicht sehen, welche Notizen es insgesamt gibt – etwa welche an eine Ausgabestelle gerichtet und
noch nicht gelesen sind –, und alte oder versehentlich geschriebene Notizen nur einzeln beim
Haushalt löschen.

## Entscheidung

- Unter „Kunden → Notizen“ gibt es eine Liste aller Notizen (`apps/kunden/views_notizen.py`,
  `kunden:notizen`), neueste zuerst, 50 je Seite.
- **Filter:** Art (an die Ausgabestelle gerichtet, davon ungelesen, Krankmeldungen/Abwesenheiten,
  einfache Notizen), Ausgabestelle (Kundengruppe des Haushalts oder „für Ausgabestelle“ der
  Notiz), Zeitraum, Suche in Text, Kundennummer, Name der Hauptperson und Verfasser.
- **Löschen:** angehakte Notizen über den Papierkorb, wie beim Haushalt
  (`kunden:notizen_loeschen`, nur POST).
- **Export:** CSV, PDF und E-Mail über das gemeinsame Auswahl-Formular (ADR 0096) – angehakte,
  ohne Haken alle gefilterten Notizen.
- **Recht:** `kunden.notizen_loeschen` („Alle Notizen löschen“). Wer alle Notizen löschen darf,
  darf sie auch alle sehen; ein eigenes Recht gibt es nicht. Konten, die einer Ausgabestelle
  zugeordnet sind, sehen und löschen nur die Notizen ihrer Kunden.

## Begründung

- Kein neues Recht: Die Liste zeigt nichts, was Berechtigte nicht schon beim Haushalt sehen, und
  bleibt am Einlass (Recht „Notizen schreiben“) verschlossen – dort gilt weiter ADR 0026.
- Der Papierkorb macht versehentliches Löschen mehrerer Notizen rückgängig.

## Folgen

- Der Export enthält Notiztexte zu Kunden (auch Krankmeldungen). Er geht deshalb nur an
  Berechtigte und über die bestehenden Wege (Download, Mail an die angegebene Adresse).
