# 0144: Schließzeiten der Ausgabestellen

- Status: Angenommen
- Datum: 2026-11-17
- Ergänzt: ADR 0014 (Kundenkonto, Vorauszahlung), ADR 0072 (Sonderausgaben)

## Problem

Ausgabestellen schließen zeitweise, z. B. drei Wochen im Sommer oder ein, zwei Wochen über
Weihnachten. bintafeln kannte das nicht: Der Vorschlag für die Vorauszahlung zählte die
ausfallenden Ausgabetage mit, Kunden zahlten also für Tage ohne Ausgabe im Voraus.

## Entscheidung

- Neues Modell `ausgabe.Schliesszeit`: Ausgabestelle, von, bis (einschließlich), Bezeichnung.
  Eingetragen wird unter „Einstellungen → Schließzeiten“ über die gemeinsamen Pflege-Listen,
  mit dem bestehenden Recht `einstellungen.listen` – also durch die Verwaltung, nicht durch die
  Ausgabestelle selbst.
- **Vorauszahlung:** `konto.vorschlaege()` lässt die geschlossenen Tage der Ausgabestelle der
  Kundengruppe aus (`Schliesszeit.tage()`) und nennt sie in der Rechnung.
- **Hinweis:** Am Einlass und auf der Startseite der Ausgabestelle steht ab 14 Tage vor Beginn
  und während der Schließzeit ein Hinweis (`Schliesszeit.hinweis()`, über den Kontext der
  aktuellen Ausgabestelle).
- **Kein Verbot:** Abholungen lassen sich in der Schließzeit weiter eintragen und nachtragen –
  eine Ausgabestelle kann ausnahmsweise doch öffnen, und die Ampel bleibt, wie sie ist.

## Begründung

- Je Ausgabestelle, nicht für die ganze Tafel: Die Stellen schließen unabhängig voneinander.
  Für die ganze Tafel gibt es weiter die beitragsfreien Zeiträume und die Feiertage.
- Hinweis statt Sperre vermeidet, dass ein falsch eingetragener Zeitraum den Einlass blockiert.

## Folgen

- Dienstplan und Fahrdienst beachten Schließzeiten (noch) nicht; dort werden ausfallende Tage
  weiter von Hand gepflegt.
- Schließzeiten gehören zum Bereich „Einstellungen“ der Datensicherung und stehen im
  Änderungsprotokoll.

## Nachtrag (2026-11-18): Beitragsfreie Zeiträume je Ausgabestelle

Auch ein beitragsfreier Zeitraum kann auf Ausgabestellen beschränkt werden
(`BeitragsfreierZeitraum.ausgabestellen`, Mehrfachauswahl; nichts angehakt = alle, so bleiben
bestehende Zeiträume unverändert). `BeitragsfreierZeitraum.am(tag, stelle)` und
`AusgabeEinstellungen.beitrag_fuer(..., stelle=…)` beachten das; es zählt die am Einlass gewählte
Ausgabestelle, sonst die der Kundengruppe (`models.stelle_von()`, dieselbe Regel wie bei den
Sonderaktionen), bei importierten Abholungen die Ausgabestelle der Abholung, im
Vorauszahlungs-Vorschlag die der Kundengruppe.
