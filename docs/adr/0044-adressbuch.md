# 0044: Adressbuch als Grundlage für Modul 5

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Modul 5 (Spenden, Mitglieder, Serienbriefe) braucht Anschriften von Spendern, Märkten, Partnern,
Presse und Behörden. Kunden sind etwas anderes: Ihre Daten kommen aus dem Kundenstamm, haben
eigene Fristen und strengere Rechte.

## Entscheidung

- Neue App `adressen` mit `Adresse` (Art Person oder Organisation, Anschrift, Kontakt,
  Kategorien, Notiz, Einwilligungen Post/E-Mail/Veröffentlichen jeweils mit Datum) und frei
  pflegbaren `AdressKategorie`n (Vorgaben: Spender, Lieferant/Markt, Partner, Presse, Behörde).
- Spenden, Mitglieder und Serienbriefe verweisen später auf `Adresse`; Kunden bleiben getrennt.
- Rechte `adressen.sehen`, `.bearbeiten`, `.loeschen`, `.importieren` im neuen Bereich „Adressen
  und Verein“; das Büro bekommt sehen, bearbeiten und importieren.
- Import aus CSV in zwei Schritten (Prüfbericht, dann übernehmen), nur neue Adressen; gleicher
  Name mit gleicher PLZ oder gleiche E-Mail gilt als vorhanden. Der CSV-Export hat dieselben
  Spalten. Die geprüfte Datei liegt bis zum Übernehmen verschlüsselt in der Sitzung.
- Auskunft nach Art. 15 als PDF, Änderungsprotokoll, Suche im Seitenkopf (Kürzel `ad`),
  Datensicherung im eigenen Bereich „Adressbuch“.

## Begründung

Ein gemeinsames Adressbuch vermeidet doppelte Erfassung derselben Firma als Spender, Lieferant
und Empfänger von Serienbriefen. Einwilligungen mit Datum sind nachweisbar und steuern später,
wer Post oder E-Mails bekommt. Ein Import ohne Überschreiben ist sicher für Tafeln, die ihre
Adressen bisher in Excel führen.
