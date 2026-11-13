# ADR 0135: Monitor „Fortschritt der Ausgabe“

## Problem

In der Verteilung soll ein Monitor hängen, der nur zeigt, wie weit die Ausgabe ist, z. B.
„200 von 225“. Manche Ausgabestellen nutzen den Aufruf (ADR 0050), andere nicht; den Monitor
sollen alle haben können.

## Entscheidung

- Eine neue Seitenart **„Fortschritt der Ausgabe“** der Aushang-Monitore (ADR 0080), je
  Ausgabestelle wählbar. Ein Aushang mit nur dieser Seite ist der Monitor für die Verteilung –
  ohne Anmeldung, über den geheimen Link, wie jeder Aushang.
- **Zählung** (`apps/aushang/fortschritt.py`, `zahlen()`):
  - Ist heute an der Ausgabestelle der **Aufruf gestartet** (Modul `aufruf` an): aufgerufene
    Nummern von allen Nummern der Aufrufliste („aufgerufen“). Wer vorher schon eingelassen wurde,
    zählt als aufgerufen.
  - **Sonst** (ohne Aufruf oder vor dem Start): Abholungen heute von den heute erwarteten
    Haushalten („da gewesen“) – dieselbe Rechnung wie der Fortschritt in der Kopfzeile
    (`apps/ausgabe/stelle.fortschritt()`, ADR 0067).
  - Heute keine Ausgabe: „Heute keine Ausgabe“.
- Nur Zahlen, keine Namen oder Kundennummern; kein QR-Code (nichts zu ändern).
- Folien mit `data-schnell` lädt der Monitor alle 20 Sekunden neu statt einmal in der Minute.

## Begründung

Die Aushang-Monitore bringen Link, Vollbild, Neuladen und Abschalten schon mit; ein eigener
Monitor wäre dasselbe noch einmal. Die Rückfallrechnung ist die schon vorhandene, damit Kopfzeile
und Monitor dieselben Zahlen zeigen.
