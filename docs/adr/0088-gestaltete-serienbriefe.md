# 0088: Gestaltete Serienbrief-Vorlagen

- Status: Angenommen
- Datum: 2026-10-29

## Problem

Serienbrief-Vorlagen (ADR 0047) waren ein graues Textfeld: Absätze per Leerzeile, Platzhalter
wie `{anrede}` musste man abtippen. Fett, Überschriften, Listen oder ein farbiger Hinweis waren
nicht möglich, ein Logo im Brief und eine Fußzeile mit Bankverbindung ebenso wenig. Dieselben
Vorlagen nutzen die Dankesbriefe (ADR 0056).

## Entscheidung

- Text und Fußzeile der Vorlage bearbeitet derselbe Editor wie die Antragstexte
  (`static/js/html_editor.js`, Reiter „Gestalten“/„HTML“), dazu Schriftgröße klein/normal/groß.
  Gespeichert wird HTML, bereinigt über `apps.core.html.bereinigen()` (nh3).
- Platzhalter stehen im gespeicherten HTML weiter als `{anrede}`. Im Reiter „Gestalten“ zeigt der
  Editor sie als farbiges, nicht editierbares Feld mit verständlichem Namen
  (`empfaenger.NAMEN`); neben dem Editor stehen sie als Kärtchen zum Ziehen oder Antippen
  (Einfügen an der Schreibmarke, wichtig fürs iPad).
- Beim Einsetzen (`apps/serienbriefe/gestaltung.py: einsetzen()`) werden die Werte immer
  maskiert und das Ergebnis erneut bereinigt: Empfängerdaten sind Fremddaten.
- Das PDF übersetzt das HTML selbst in ReportLab-Bausteine (`gestaltung.flowables()`): fett,
  kursiv, unterstrichen, Farben, Schriftgröße, Ausrichtung, Überschriften, Listen, farbige Kästen
  als Tabelle mit Hintergrund. Unbekanntes erscheint als normaler Text, Bilder aus dem Netz werden
  nicht geladen.
- Je Vorlage: `briefkopf` (Logo aus `TafelEinstellungen.logo` und Kontakt oben rechts, abschaltbar
  für eigenes Briefpapier) und `fusszeile` (auf jeder Seite und unter jeder E-Mail).
- E-Mails gehen als HTML mit Klartext-Fassung.
- Ältere Vorlagen aus reinem Text wandelt die Migration `0003_gestaltung` in Absätze um
  (umkehrbar); `gestaltung.als_html()` erkennt reinen Text zusätzlich zur Laufzeit.
- „Vorschau (PDF)“ beim Bearbeiten zeigt den Brief mit einem erfundenen Empfänger, ohne zu
  speichern.

## Begründung

Der vorhandene Editor ist erprobt und hält die Oberfläche einheitlich, eine fremde
Editor-Bibliothek ist nicht nötig. `{name}` im gespeicherten Text hält Vorlagen lesbar, im
HTML-Reiter bearbeitbar und kompatibel mit Betreff, Dankesbriefen und älteren Vorlagen. Eine
eigene, kleine HTML-Umsetzung für ReportLab vermeidet eine weitere Abhängigkeit (etwa ein
HTML-zu-PDF-Werkzeug mit Browser-Engine) und kann nur, was bereinigt wurde.
