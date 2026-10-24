# 0021: PDFs mit ReportLab, Auskunft nach Art. 15 DSGVO

- Status: Angenommen
- Datum: 2026-10-24

## Problem

Gedruckt wird in bintafeln nur über erzeugte PDFs. Gebraucht werden zuerst der
Kassenabschluss, der Kundenausweis mit Barcode und die Auskunft nach Art. 15 DSGVO für Kunden
und Mitarbeitende.

## Entscheidung

- PDFs erzeugt **ReportLab** (feste Version) im Programm, ohne HTML-Umweg und ohne
  Systempakete. `apps/core/pdf.py` liefert einen einheitlichen Rahmen: Kopf mit Name und
  Anschrift der Tafel, Fuß mit Erstellungszeit und Seitenzahl, Tabellen und Angabenlisten.
- PDFs werden für jeden Abruf neu erzeugt, nie gespeichert und nie zwischengespeichert.
- **Kundenausweis:** Karte im Scheckkartenformat auf A4 mit Schnittmarken. Der Barcode
  (Code 128) enthält nur die Kundennummer, damit der Scanner am Einlass sie eintippt.
- **Auskunft:** vollständig, also auch mit Angaben der besonderen Kategorie und mit Feldern, die
  inzwischen abgeschaltet sind. Für Kunden erzeugen Admin und Büro sie (Eintrag im
  Zugriffsprotokoll). Für Mitarbeitende Admin und die Rolle Personal, weil sie Personaldaten
  enthält (Eintrag im Änderungsprotokoll). Jede Person kann ihre eigene unter „Mein Konto“
  abrufen. Dokumente werden nur mit Titel aufgeführt.
- **Kasse:** Jede Ansicht lässt sich drucken: Tag als Kassenabschluss mit Feldern für
  Zählung und Unterschriften, Monat und Jahr als Kassenbericht.

## Begründung

ReportLab ist seit Jahrzehnten gepflegt, reines Python und erzeugt Barcodes selbst. Eine
HTML-zu-PDF-Lösung bräuchte einen Browser oder Systembibliotheken im Container. Eine
vollständige Auskunft auf Knopfdruck erfüllt die Pflicht nach Art. 15 DSGVO ohne Handarbeit.
