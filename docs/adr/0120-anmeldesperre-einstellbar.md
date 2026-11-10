# ADR 0120: Anmelde-Sperre einstellbar und vom Admin aufhebbar

## Problem

Nach fünf falschen Passwörtern war ein Benutzername fest für 15 Minuten gesperrt (ADR 0093). Wer
sich versehentlich ein paar Mal vertippt, stand damit schnell vor verschlossener Tür – und niemand
konnte die Sperre vor Ablauf aufheben.

## Entscheidung

- **Einstellbar:** `AnmeldeEinstellungen.fehlversuche` (Vorgabe 5, 3–50) und `sperre_minuten`
  (Vorgabe 15, 1–240) unter „Einstellungen → Anmeldung und Zwei-Faktor“. Die Vorgaben entsprechen
  dem bisherigen Verhalten.
- **Sofort aufheben:** Ist ein Benutzername gesperrt, zeigt die Seite der Person (bzw. der
  Ausgabestelle) den Knopf „Anmelde-Sperre aufheben“ (`verwaltung.anmeldesperre_aufheben`, nur für
  Verwalter). Das Passwort bleibt unverändert.
- **Eine Stelle für die Logik:** `apps/konten/anmeldesperre.py` (zählen, prüfen, aufheben); der
  Zähler liegt weiter im gemeinsamen Datenbank-Cache.

## Begründung

Eine Tafel mit vielen gelegentlichen Nutzern braucht mehr Spielraum als fünf Versuche, ohne den
Schutz vor Durchprobieren aufzugeben; die untere Grenze von drei Versuchen und die Sperre bleiben
erhalten. Das Aufheben durch einen Admin erspart Wartezeit im Betrieb und ist an dieselben
Schutzregeln gebunden wie die übrige Kontoverwaltung.
