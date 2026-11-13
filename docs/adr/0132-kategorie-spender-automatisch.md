# ADR 0132: Kategorie „Spender“ automatisch

## Problem

Der Abruf aus dem Vereinsportal (ADR 0126–0128) legt viele neue Adressen an. Sie haben keine
Kategorie, obwohl es die Kategorie „Spender“ seit Beginn gibt (ADR 0044). Im Adressbuch sieht man
nicht, wer Spender ist, und ein Serienbrief an die Kategorie „Spender“ erreicht sie nicht. Von Hand
nachzupflegen ist bei Hunderten Adressen unrealistisch.

## Entscheidung

- Jede gespeicherte Spende gibt ihrer Adresse die Kategorie „Spender“ – egal, ob von Hand, per
  CSV-Import oder aus dem Vereinsportal (`Spende.save()` → `adressen.models.als_spender_markieren()`).
- **Nur hinzufügen, nie entfernen.** Mitglieder und Helfer behalten ihre Kategorien und sind
  zusätzlich Spender. Wird eine Spende gelöscht, bleibt die Kategorie (wer einmal gespendet hat,
  bleibt im Spenderkreis; abwählen geht von Hand).
- **Reine Mitgliedsbeiträge** (Häkchen „Mitgliedsbeitrag“, ADR 0045) machen niemanden zum Spender.
- Hat die Tafel die Kategorie abgeschaltet, vergibt bintafeln sie nicht; fehlt sie, wird sie
  angelegt.
- Eine Datenmigration (`spenden/0007`) trägt die Kategorie einmal bei allen vorhandenen Spendern
  nach. Sie fügt nur hinzu; rückwärts bleibt alles, wie es ist.

## Begründung

Die Kategorie ist das, womit das Adressbuch einordnet und Serienbriefe Empfänger wählen. Sie aus der
Spende abzuleiten, erspart doppelte Pflege, und weil nichts entfernt wird, kann die Automatik keine
von Hand gepflegte Zuordnung kaputt machen.
