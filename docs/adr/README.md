# Architekturentscheidungen (ADR)

Hier halten wir grundlegende Entscheidungen fest, damit auch in Jahren noch nachvollziehbar ist,
**warum** bintafeln so gebaut ist. Eine ADR (Architecture Decision Record) ist kurz und beantwortet
drei Fragen: Was war das Problem? Was haben wir entschieden? Warum?

## Regeln

- Eine Datei je Entscheidung: `NNNN-kurzer-titel.md`, fortlaufend nummeriert.
- Neue ADRs kommen per Pull Request, wie jede andere Änderung.
- Angenommene ADRs werden nicht umgeschrieben. Ändert sich eine Entscheidung, entsteht eine neue
  ADR, und die alte bekommt den Status „Ersetzt durch NNNN“.

## Vorlage

```markdown
# NNNN: Titel

- Status: Vorgeschlagen | Angenommen | Ersetzt durch NNNN
- Datum: JJJJ-MM-TT

## Problem
## Entscheidung
## Begründung
## Folgen
```

„Folgen“ ist optional: Was wird dadurch leichter, was schwerer, was ist zu beachten?

## Übersicht

| Nr. | Titel | Status |
|---|---|---|
| [0001](0001-technische-grundlage.md) | Technische Grundlage | Angenommen |
| [0002](0002-eine-installation-je-tafel.md) | Eine Installation je Tafel | Angenommen |
| [0003](0003-konfiguration-und-betriebsmodus.md) | Konfiguration über .env, Betriebsmodus über die Domain | Angenommen |
| [0004](0004-anmeldung-rollen-zwei-faktor.md) | Anmeldung, Rollen und Zwei-Faktor | Angenommen |
| [0005](0005-aenderungsprotokoll.md) | Änderungsprotokoll mit django-auditlog | Angenommen |
| [0006](0006-kundenstamm-als-snapshot.md) | Kundenstamm als Snapshot mit Vollaustausch | Angenommen |
| [0007](0007-lizenz-agpl.md) | Lizenz AGPL-3.0 | Angenommen |
| [0008](0008-sicherung-und-update.md) | Sicherung und Update | Angenommen |
