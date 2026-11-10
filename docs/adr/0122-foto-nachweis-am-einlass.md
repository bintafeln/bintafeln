# ADR 0122: Foto eines Nachweises am Einlass

## Problem

Die Ausgabestellen sehen am Einlass Bescheide und Behindertenausweise, konnten sie aber
nicht festhalten: Dokumente zum Haushalt hochladen darf nur die Verwaltung (ADR 0030). Der
Nachweis musste deshalb später noch einmal vorgelegt oder auf anderem Weg ins Büro gebracht werden.

## Entscheidung

- **Eigenes Recht** `kunden.dokument_foto` („Foto eines Nachweises aufnehmen“): Es erlaubt nur
  das Ablegen, nicht das Ansehen oder Löschen. Die Vorgaben geben es den Rollen mit Einlass; eine
  Datenmigration gibt es allen bestehenden Rollen, die Notizen schreiben dürfen.
- **Knopf „📷 Foto aufnehmen …“** bei den Notiz-Vorlagen (am Einlass und auf der Haushaltsseite):
  Art wählen (Dokumentart, z. B. „Bescheid“ oder die neu mitgelieferte
  „Behindertenausweis“) und fotografieren. Mehrere Seiten sammelt
  `static/js/foto_seiten.js` (ein Dateifeld ersetzt sonst seine Auswahl), höchstens zehn.
- **Ablage wie jedes Dokument zum Haushalt** (`HaushaltDokument`, verschlüsselt, an der
  Kundennummer, Löschfrist der Dokumentart, in der Auskunft): je Seite ein Dokument mit
  „(Seite n von m)“. Dazu entsteht eine Notiz „Foto abgelegt: … (n Seiten)“, damit die Verwaltung
  es bemerkt.

## Begründung

Das getrennte Recht hält die Datensparsamkeit ein: Wer am Einlass steht, kann einen Nachweis
abgeben, sieht aber weder frühere Dokumente noch das eben aufgenommene Foto wieder. Die Ablage
über die vorhandenen Dokumente vermeidet einen zweiten Speicherort mit eigener Frist und Auskunft.
