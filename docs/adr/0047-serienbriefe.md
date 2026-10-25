# 0047: Serienbriefe und Serien-E-Mails

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Tafeln schreiben regelmäßig viele Menschen an: Dank an Spender, Beitragserinnerungen,
Einladungen zur Mitgliederversammlung, Informationen an Kunden. Bisher ging das nur mit Export
und Textverarbeitung.

## Entscheidung

- Neue App `serienbriefe` mit `Vorlage` (Name, Betreff, Text mit Platzhaltern) und `Versand`
  (wann, wer, Art, Vorlage, Betreff, Beschreibung der Auswahl, Anzahl, Empfänger-Schlüssel
  `a:<Adresse>`/`k:<Kundennummer>` für die Auskunft). Drei Vorlagen kommen per Migration mit.
- Empfänger-Quellen (`empfaenger.py`): Adressen nach Kategorie, Mitglieder (Arten, nur offener
  Beitrag), Spender eines Jahres (Mindestsumme), Kunden (aktive Haushalte, Kundengruppen,
  Zugang nach ADR 0034). Für Adressen und Spender ist „nur mit Einwilligung“ vorgewählt.
- Text ist reiner Text (kein HTML); Platzhalter `{name}` werden ersetzt, unbekannte bleiben
  stehen, damit Tippfehler auffallen.
- Briefe als ein PDF über ReportLab, Anschriftfeld nach DIN 5008 Form B (Fensterumschlag DIN
  lang), Faltmarken. E-Mails einzeln über `apps.core.mail.senden()`, nie mehrere Empfänger in
  einer Mail; in der Demo gesperrt.
- Rechte `serienbriefe.erstellen` (Büro) und zusätzlich `serienbriefe.kunden` (nur Admin).

## Begründung

Platzhalter in einfachem Text sind für Ehrenamtliche verständlich und sicher (keine
Formatierungs- oder Skriptprobleme). Der Vermerk je Versand hält Datensparsamkeit und
Auskunftspflicht zusammen, ohne die Briefe selbst zu speichern.
