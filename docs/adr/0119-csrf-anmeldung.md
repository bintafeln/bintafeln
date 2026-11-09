# ADR 0119: Freundliche Antwort bei fehlgeschlagener CSRF-Prüfung

## Problem

War eine Seite lange offen (oder in einem zweiten Tab) und die Anmeldung inzwischen abgelaufen,
trägt das Formular ein veraltetes CSRF-Token. Django bricht die Anfrage dann mit einer
technischen Sackgasse ab („Verboten (403) – CSRF-Verifizierung fehlgeschlagen“). Bei einer
erneuten Anmeldung kam die Meldung immer wieder; es half nur, den Browser ganz zu schließen.

## Entscheidung

- **Eigene Fehlerseite:** `settings.CSRF_FAILURE_VIEW = "apps.core.fehler.csrf_fehler"`. Nicht
  angemeldete Besucher werden auf eine frische Anmeldeseite geleitet (mit einem kurzen Hinweis) –
  die bekommt ein neues Token, sodass die nächste Anmeldung sofort klappt. Angemeldete sehen einen
  verständlichen Hinweis zum Neuladen (Status 403).
- **Kein altes Formular aus dem Cache:** Die Anmeldeseiten (`anmelden`, `anmelden_code`) sind mit
  `@never_cache` versehen. So verwendet der Browser – auch über die Zurück-Taste – kein
  zwischengespeichertes Formular mit veraltetem Token mehr (`Cache-Control: … no-store`).

## Begründung

Die beiden Maßnahmen beheben die eigentliche Ursache (veraltetes Token aus einer lange offenen
oder gecachten Seite) an der Stelle, an der sie auftritt, ohne den CSRF-Schutz zu schwächen: Eine
abgelaufene Anmeldung führt nun zurück zur Anmeldung statt in eine Sackgasse. Die Logik liegt an
einer Stelle (`apps/core/fehler.py`) und gilt für jede fehlgeschlagene CSRF-Prüfung im Programm.
