# 0099: Team getrennt in Angestellte und Ehrenamtliche

- Status: Angenommen
- Datum: 2026-11-01

## Problem

Bisher zeigte das Menü „Team“ eine Sammelliste **„Mitarbeitende“** (alle Konten) und daneben das
Modul **„Personal“** (Verträge, Abwesenheiten, Stunden der Festangestellten). Dadurch tauchten
Angestellte an zwei Stellen auf, und die Begriffe „Mitarbeitende“ und „Personal“ waren unklar –
obwohl bintafeln die beiden Gruppen längst über das Feld **Beschäftigung** (ehrenamtlich / fest
angestellt) unterscheidet.

## Entscheidung

Im Menü „Team“ gibt es zwei nach Beschäftigung getrennte Listen:

- **Ehrenamtliche** – Konten mit Beschäftigung „ehrenamtlich“.
- **Angestellte** – Konten mit Beschäftigung „fest angestellt“.

Beide nutzen dieselbe Konten-Verwaltung (`konten:mitarbeitende`), nur gefiltert; eine aus einer
Liste angelegte Person ist dort schon passend vorbelegt. Die bisherige Sammelansicht bleibt intern
erreichbar.

Das frühere Modul „Personal“ heißt in der Oberfläche **„Verträge & Zeiten“** und gehört zum Bereich
der Angestellten; die mitgelieferte Rolle **„Personal“ heißt jetzt „Angestellte“** (Datenmigration
`konten.0031` benennt die Gruppe um, die interne Konstante und die Rechte-Namen bleiben). Das Wort
„Personal“ verschwindet aus der Oberfläche.

## Begründung

Angestellte und Ehrenamtliche sind die beiden tatsächlichen Gruppen einer Tafel; sie getrennt zu
zeigen beseitigt die Doppelung und ist selbsterklärend. Da die Unterscheidung schon im
Beschäftigungs-Feld steckt, braucht es dafür nur gefilterte Listen, kein neues Modell. Technische
Namen (URLs, Rechte, App-Label `personal`, Importformat) bleiben, damit Links und Migrationen
stabil bleiben.
