# 0002: Eine Installation je Tafel

- Status: Angenommen
- Datum: 2026-10-23

## Problem

Mehrere Tafeln sollen bintafeln nutzen. Entweder verwaltet eine Installation viele Tafeln
(mandantenfähig), oder jede Tafel betreibt ihre eigene.

## Entscheidung

Jede Tafel betreibt **ihre eigene Installation** auf eigener Infrastruktur (VPS oder VM im
eigenen Netz). Der Code enthält **keine Mandantenlogik**. Die Stammdaten der Tafel (Name, Logo,
Anschrift) liegen als **ein einziger Datensatz** (`TafelEinstellungen`) in der Datenbank.

## Begründung

- Die Kundendaten einer Tafel verlassen nie deren eigene Infrastruktur. Jede Tafel bleibt
  Verantwortliche im Sinne der DSGVO, ohne gemeinsamen Betreiber.
- Ein Fehler in der Zugriffskontrolle kann nie Daten einer anderen Tafel offenlegen.
- Der Code bleibt einfacher: keine Mandanten-ID in jeder Tabelle und jeder Abfrage.

## Folgen

- Jede Tafel braucht jemanden, der Installation, Updates und Sicherungen betreut. Installation,
  Update und Sicherung müssen deshalb besonders einfach sein.
- Nichts Tafel-Spezifisches darf im Code stehen (Name, Logo, Adressen, IPs, Hostnamen).
