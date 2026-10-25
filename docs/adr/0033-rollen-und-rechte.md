# 0033: Frei anlegbare Rollen mit fein einstellbaren Rechten

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Bisher gab es feste Rollen (Admin, Büro, Ausgabe, Kiosk, Fahrer, Beifahrer, Personal), und jede
Ansicht prüfte Rollennamen. Tafeln arbeiten unterschiedlich: Sie brauchen eigene Rollen (z. B.
„Telefondienst“, „Lager“) und wollen sehr fein festlegen, was jemand sehen und tun darf.

## Entscheidung

- **Rechtekatalog** in `apps/konten/rechte.py`: rund 45 Rechte mit Code, Bereich und
  Bezeichnung. Ansichten prüfen nur Rechte (`recht_erforderlich`, `hat_recht`), Templates über
  die Variable `rechte`. Teile einer Seite (Anschrift, Konto, Dokumente …) haben eigene Rechte.
- **Rolle** = Django-Gruppe + `konten.Rolle` mit Rechteliste und Pflichten (Zwei-Faktor,
  Belehrung, Führerschein). Jede neu angelegte Gruppe bekommt automatisch eine Rolle ohne
  Rechte. Rollen sind über „Einstellungen → Rollen und Rechte“ anlegbar, änderbar, löschbar.
- **Admin** hat immer alle Rechte, ist nicht löschbar und nicht beschneidbar (kein Aussperren).
- **Keine Rechteausweitung:** Wer nicht Admin ist, gibt nur Rechte weiter, die er selbst hat,
  und vergibt nur Rollen, deren Rechte er vollständig hat.
- **Migration:** Die mitgelieferten Rollen erhalten genau ihr bisheriges Verhalten. Die
  Schalter „Zwei-Faktor Pflicht für …“, „Büro darf Mitarbeitende verwalten“ und „Ausgabe sieht
  besondere Kategorie“ wandern in die Rollen; beim Zurückgehen auf eine ältere Version schreibt
  die Rückwärtsmigration sie zurück.

## Begründung

Ein fester Katalog im Code (statt Django-Permissions je Modell) bildet fachliche Rechte ab, nicht
Datenbanktabellen, und bleibt für Nicht-Techniker verständlich. Die Rechteliste als JSON an der
Rolle ist einfach zu migrieren; unbekannte Codes werden ignoriert, fehlende Rechte sind
„nicht erlaubt“. Neue Rechte brauchen eine Datenmigration für bestehende Rollen.
