# 0100: Bexat-Import als zuschaltbares Modul

- Status: Angenommen
- Datum: 2026-11-02

## Problem

Mehrere Tafeln kommen vom **Bexat-Tafelprogramm** (Hersteller tafelarbeit.de) zu bintafeln. Sie
alle müssen ihren Bestand (Haushalte, Personen, Abholungen, Anträge, Mitarbeitende) übernehmen.
ADR 0006 hält Konverter für bestimmte Altsysteme aus dem Repository heraus; ein lokal auszuführendes
Python-Werkzeug setzt aber eine passende Umgebung auf dem Rechner der Tafel voraus und ist für viele
Tafeln eine Hürde.

## Entscheidung

- Die Umwandlung des Bexat-Exports (mehrblättrige Excel-Datei) in das neutrale Importformat wird
  ein **zuschaltbares Modul** `apps/bexat` (ADR 0049). ADR 0006 wird entsprechend ergänzt.
- Das Modul **erzeugt nur das neutrale Importformat** und übergibt es dem **normalen Import mit
  Abgleich**: „Kundenstamm prüfen und abgleichen“ führt direkt in den bekannten Abgleich des
  Kundenstamms; Anträge und Mitarbeitende werden als CSV heruntergeladen und wie gewohnt unter
  „Daten importieren“ eingespielt. Gespeichert wird nie ohne Abgleich.
- **Keine festen, tafelspezifischen Werte im Code.** Ausgabestellen und Kundengruppen kommen aus
  dem Export; Einkommensarten und (falls nötig) Ausgabestellen-Namen pflegt jede Tafel als
  Zuordnung „Nummer → Text“ in den Modul-Einstellungen (`BexatEinstellungen`). Fest sind nur die
  **herstellerweiten** Tabellen in `apps/bexat/codes.py` (Anrede, Wochentag, amtliche
  Staatsangehörigkeitsliste) – das ist Wissen über das Format, wie `docs/importformat.md`.
- **Keine Personendaten** im Repository: Die Umwandlung ist zustandslos, die hochgeladene Datei
  wird nur gelesen und nicht gespeichert; Tests nutzen ausschließlich erfundene Daten.

## Begründung

- Das Modul läuft auf dem Server der Tafel; niemand braucht mehr eine Python-Umgebung auf dem
  eigenen Rechner. Die Daten verlassen den Server nicht.
- Weil nur das neutrale Format erzeugt und durch den vorhandenen Import geschickt wird, bleibt die
  bewährte Prüfung samt Abgleich und Sicherung erhalten (ADR 0006, ADR 0078). bintafeln bleibt
  unabhängig vom Hersteller.
- Mehrere Tafeln mit demselben Altsystem teilen sich die Pflege eines Wegs statt vieler lokaler
  Skripte.

## Folgen

- Nur **offene** Anträge werden übernommen; **gelöschte** Haushalte bleiben außen vor
  (Datensparsamkeit). Die Höhe des Einkommens kommt nicht mit, nur die Einkommensart.
- Der Haushaltsvorstand steht in Bexat in `household_person` (type `householder`); `households.
  person_id` ist unbrauchbar. Angehörige (`relative`) und Abholberechtigte (`collector`) ebenso.
- Andere Tafeln mit anderem Altsystem bekommen bei Bedarf ein eigenes Modul nach demselben Muster.
