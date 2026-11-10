# ADR 0121: Die Suche findet auch Seiten hinter einem Knopf

## Problem

Die Suche im Seitenkopf fand nur Menüpunkte. Seiten, die nicht im Menü stehen, sondern über
einen Knopf auf einer anderen Seite erreichbar sind (z. B. „Online-Zugänge freigeben“ bei den
Mitarbeitenden), waren über die Suche nicht zu finden.

## Entscheidung

- `apps/core/unterseiten.py` führt diese Seiten in einer Liste: Titel, Adresse, nötiges Recht,
  der Weg zum Knopf, Stichwörter und gegebenenfalls das Modul.
- `suche._programm()` zeigt sie neben den Menüpunkten („Knopf auf: …“) – nur mit dem Recht dazu
  und nur, wenn das Modul eingeschaltet ist.
- Ein Test prüft, dass jede eingetragene Adresse existiert, vom Admin geöffnet werden kann und
  ohne das Recht gesperrt ist. **Neue Seiten mit eigenem Knopf werden dort eingetragen.**

## Begründung

Jede Seite ins Menü zu setzen, würde es überladen (jede Adresse steht dort nur einmal). Eine
gepflegte Liste hält die Suche vollständig, ohne das Menü zu verändern, und der Test verhindert,
dass ein Eintrag auf eine falsche Adresse oder ein falsches Recht zeigt.
