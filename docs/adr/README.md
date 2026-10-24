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
| [0009](0009-zwei-faktor-pflicht-und-notfallcodes.md) | Zwei-Faktor: Selbsteinrichtung, Pflicht je Rolle, Notfallcodes | Angenommen |
| [0010](0010-kundenstamm-umfang-und-zusatzfelder.md) | Kundenstamm: Umfang, Zusatzfelder und eigene Daten im Snapshot | Angenommen |
| [0011](0011-abholungen-mit-aufbewahrungsfrist.md) | Abholungen und Ausnahmen mit Aufbewahrungsfrist | Angenommen |
| [0012](0012-zugriffsprotokoll.md) | Zugriffsprotokoll für Kundendaten | Angenommen |
| [0013](0013-empfang-erfasst-abholungen.md) | Der Empfang erfasst Abholungen schon im Snapshot-Betrieb | Angenommen |
| [0014](0014-kundenkonto-mit-buchungen.md) | Kundenkonto mit Buchungen | Angenommen |
| [0015](0015-mitarbeitende-verwalten.md) | Mitarbeitende in bintafeln verwalten | Angenommen |
| [0016](0016-mailserver-und-einladungen.md) | Mailserver in der Oberfläche, Einladungen per Link | Angenommen |
| [0017](0017-stammdaten-mitarbeitende.md) | Stammdaten der Mitarbeitenden, Wiedervorlagen und Löschfrist | Angenommen |
