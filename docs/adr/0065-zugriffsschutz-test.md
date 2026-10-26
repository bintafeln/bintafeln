# 0065: Zugriffsschutz aller Seiten automatisch prüfen

- Status: Angenommen
- Datum: 2026-10-26

## Problem

Jede Ansicht schützt sich selbst mit `recht_erforderlich` oder eigenen Prüfungen (ADR 0033).
Die Tests prüfen das bisher Seite für Seite. Vergisst eine neue Seite die Prüfung, fällt das
erst auf, wenn jemand darauf stößt – bei Kundendaten zu spät.

## Entscheidung

`tests/test_zugriffsschutz.py` geht **alle** Adressen des Programms durch (alle Module
eingeschaltet, Platzhalter wie `999999` für Nummern):

- Ohne Anmeldung muss jede Seite zur Anmeldung führen, außer den Seiten in `OEFFENTLICH`
  (Anmeldung, Passwort-Link, Online-Antrag, Aufruf-Geräte mit Schlüssel im Link, Einrichtung).
- Ein angemeldetes Konto ohne Rechte muss überall 403 bekommen, außer auf den Seiten in
  `ALLE_ANGEMELDETEN` (Startseite, eigenes Konto, Zwei-Faktor, Handbuch, Suche).
- Die Rechteprüfung kommt vor der Suche nach dem Datensatz: Ein 404 statt 403 verriete sonst,
  welche Datensätze es gibt. Deshalb zählt auch 404 als Fehler.

Neue Seiten fallen automatisch darunter. Wer eine Seite bewusst öffentlich macht, trägt sie in
eine der beiden Listen ein; die Entscheidung steht damit sichtbar im Pull Request.

## Begründung

Ein einziger Test deckt alle heutigen und künftigen Seiten ab und kostet wenige Sekunden. Er
fand beim Einführen gleich eine Stelle (Dokumente zu Mitarbeitenden), an der ein Konto ohne
Rechte über 404/403 erfahren konnte, welche Konten es gibt.
