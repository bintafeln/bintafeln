# ADR 0166: Grafiken frei auf der Seite eines Serienbriefs

## Problem

Ein Serienbrief soll mehrere Unterschriften tragen, z. B. die des ganzen Vorstands. Grafiken
standen bisher nur im Text (ADR 0138): jede in einer eigenen Zeile, nebeneinander oder
überlappend ging nicht. Eingescannte Unterschriften haben außerdem einen weißen Hintergrund, der
andere Unterschriften und den Text verdeckt.

## Entscheidung

- Eine Vorlage hat neben dem Text eine Liste **frei gesetzter Grafiken**
  (`Vorlage.freie_grafiken`, JSON): je Eintrag Grafik, Abstand von links und oben, Breite (alles
  in Millimetern ab der linken oberen Ecke von A4) und Seite (`erste` oder `letzte` Seite des
  Briefs, Vorgabe `letzte`). Geprüft wird nur über `apps/serienbriefe/frei.py` (`lesen()`:
  nur vorhandene Grafiken, Maße innerhalb der Seite, höchstens 20; Unlesbares fällt weg).
- **Brief (PDF):** `frei.zeichnung()` legt die Grafiken je Brief an ihre feste Stelle über den
  Text, auf die erste bzw. letzte Seite des Briefs. Sie wandern nicht mit dem Text.
- **E-Mail:** Es gibt keine Seite; `frei.fuer_mail()` stellt die Grafiken nebeneinander unter den
  Text (von links nach rechts, oben vor unten), eingebettet wie in ADR 0138.
- **Bedienung:** In der Live-Vorschau liegen die Grafiken verschiebbar über dem Bild der ersten
  Seite (`static/js/brief_frei.js`): ziehen, an der Ecke die Größe ändern, mit Pfeiltasten
  verschieben. Die Vorschau zeichnet sie deshalb nicht selbst mit. Eine Tabelle zeigt dieselben
  Maße zum Eintragen, auch ohne Vorschau (Handy). Gespeichert wird sofort wie die übrige Vorlage.
- **Hochladen:** PNG, JPG oder PDF (davon die erste Seite). Mit „Hintergrund durchsichtig machen“
  wird Weiß durchsichtig (dasselbe Verfahren wie für Unterschrift und Stempel der
  Spendenbestätigung, ADR 0130/0137) und der leere Rand abgeschnitten; gespeichert als PNG.
  Mehrere Unterschriften auf einem Blatt werden nicht automatisch zerlegt: eine Datei je
  Unterschrift ist zuverlässiger.

## Begründung

Eine feste Stelle auf der Seite ist das, was man von Briefpapier kennt, und erlaubt Überlappen und
beliebige Anordnung. Dass die Grafik nicht mit dem Text wandert, ist der Preis dafür; die Vorgabe
„letzte Seite“ hält Unterschriften auch bei längeren Briefen am Ende. Millimeter statt Pixel
machen die Lage unabhängig von Bildschirm und Vorschau. Das automatische Zerlegen eines Blatts mit
mehreren Unterschriften wäre unsicher, sobald sich Unterschriften berühren oder aus mehreren
Teilen bestehen.
