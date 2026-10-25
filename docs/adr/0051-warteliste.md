# 0051: Warteliste mit Einladungen

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Neuanmeldungen liefen bisher über ein eigenes Programm (Flask, SQLite): Es lud die Anträge von einem
Fremdsystem herunter, verschickte Einladungen zu Terminen, führte Status, Streichungs- und
Druckliste und glich Namen mit dem Kundenstamm des Fremdsystems ab. Daten lagen doppelt, Kommentare
mussten zurückgeschrieben werden, und es gab keine Anmeldung.

## Entscheidung

- Modul `warteliste` (ADR 0049) auf den Anträgen von bintafeln (ADR 0024); kein Import, kein
  Zurückschreiben. Jeder Antrag außerhalb des Papierkorbs hat einen `Wartestand`.
- Status wie bisher: neu → wartend (nach einem Tag), Wartezeit bis → Wartezeit abgelaufen,
  eingeladen (Termin) → erschienen / entschuldigt / nach N Tagen „Streichen möglich“ oder direkt
  gestrichen (einstellbar), aufgenommen (Aufnahme-Assistent). Gestrichen lehnt den Antrag ab und
  kommt auf die Streichungsliste (`Streichung`, nach einstellbaren Tagen gelöscht). Anmerkungen
  (z. B. „entschuldigt für den Termin …“) stehen beim Antrag.
- `Termin` mit Datum, Zeit und Ort; Einladung und Absage per Mail (`apps.core.mail`), Texte mit
  Platzhaltern in `WartelisteEinstellungen`; ohne E-Mail-Adresse wird nur eingetragen.
  Verlauf in `Einladung`. Druckliste und Streichungsliste als PDF.
- Abgleich mit dem eigenen Kundenstamm über die Dublettenprüfung des Aufnahme-Assistenten, mit
  Hinweisen zur Sperrzeit nach Ablauf des Ausweises (Monate einstellbar; keine Sperrzeit ab
  einstellbarem Alter oder bei einem Ja/Nein-Zusatzfeld).
- Doppelte Anträge: Namensähnlichkeit wie im Aufnahme-Assistenten; streichen mit Vermerk oder
  „keine Dublette“.
- Modulrahmen ergänzt: `Modul.fristen` (Automatik beim Aufruf der Startseite) und
  `Modul.auskunft_antrag` (eigener Abschnitt in der Auskunft nach Art. 15 zum Antrag).
- Rechte `warteliste.sehen`, `warteliste.bearbeiten` (Büro) und `einstellungen.warteliste`.

## Begründung

Die Anträge liegen schon in bintafeln; die Warteliste darauf aufzubauen spart Import, doppelte Daten
und Abgleich der Kommentare. Status und Ablauf bleiben, wie das Team sie kennt.
