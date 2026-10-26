# 0066: Browser-Tests mit Playwright

- Status: Angenommen
- Datum: 2026-10-26

## Problem

Die Tests mit dem Django-Testclient prüfen, was der Server ausliefert, aber nicht, was im
Browser passiert: HTMX-Austausch, Kamera-Scanner, Auswahlkästchen, Kopfzeile. Fehler darin
fielen bisher erst auf der Dummy-Tafel oder bei der Tafel auf, z. B. das schwarze Kamerabild
beim zweiten Scan.

## Entscheidung

- Wenige Browser-Tests in `tests/e2e/` mit Playwright (Chromium) gegen den Testserver von
  pytest-django (`live_server`), mit erfundenen Daten: Anmeldung mit Zwei-Faktor-Code, Einlass
  bis zur eingetragenen Abholung, Kamera dreimal hintereinander (Testbild statt Kamera),
  Kundenliste mit Auswahl und Export, Online-Antrag, Suche.
- Jeder JavaScript-Fehler und jede Fehlermeldung in der Konsole lässt den Test scheitern.
- Sie laufen nur mit `pytest -m e2e` und brauchen `requirements-e2e.txt` samt Browser; der
  normale Testlauf bleibt schnell und ohne Browser. In CI läuft dafür der eigene Job `e2e`.
- Nur die wichtigsten Abläufe; Einzelheiten prüfen weiter die schnellen Tests.

## Begründung

Playwright ist etabliert, steuert einen echten Browser und kann Kamera und Downloads
nachstellen. Die Tests fanden beim Einführen gleich einen Fehler: Die Zahl der angehakten
Zeilen wurde in keiner Liste angezeigt, weil `form.id` bei Kästchen mit `name="id"` die
Kästchen liefert statt des Formularnamens.
