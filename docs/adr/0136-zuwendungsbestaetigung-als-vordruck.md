# ADR 0136: Zuwendungsbestätigung im Aufbau des bekannten Vordrucks

## Problem

Die Zuwendungsbestätigungen (ADR 0045) enthielten alle Pflichtangaben, waren aber als Fließtext
im allgemeinen PDF-Rahmen gesetzt (Kopf mit Tafel, „[x]“ statt Kästchen). Spender und Tafeln
kennen die Bestätigung als Vordruck nach den amtlichen Mustern mit gerahmten Kästen und
Ankreuzfeldern; so soll sie auch aus bintafeln kommen – genauso, wie die Belege aus anderen
Programmen aussehen.

## Entscheidung

- Die Bestätigung wird in `apps/spenden/vordruck.py` direkt auf die Seite gezeichnet (ReportLab
  Canvas), mit festen Maßen nach dem Vordruck, ohne Kopf und Fuß von `apps.core.pdf`. Texte laufen
  trotzdem durch `apps.core.pdf.text()` (maskiert, bereinigt).
- Aufbau: Kasten „Aussteller“ (Name und Anschrift in einer Zeile, Teile mit „ | “), Überschrift,
  Kasten „Name und Anschrift des Zuwendenden“, drei Felder Betrag in Ziffern | in Buchstaben |
  Tag der Zuwendung bzw. Zeitraum der Sammelbestätigung, bei Einzelbestätigungen „Verzicht auf
  Erstattung von Aufwendungen Ja ☐ Nein ☐“, bei Sachzuwendungen Bezeichnung und Herkunft zum
  Ankreuzen, die beiden Ankreuzfelder zur Steuerbegünstigung (das gewählte angekreuzt und fett
  ausgefüllt, das andere leer), Kasten zur Verwendung mit dem Satz zu Mitgliedsbeiträgen, Linie
  für Ort, Datum und Unterschrift, Hinweis.
- „In Buchstaben“ ziffernweise wie im Vordruck („fünf-null-null-komma-null-null“), Beträge ohne
  Euro-Zeichen („2.000,00“).
- Anlage zur Sammelbestätigung als Tabelle, neueste Spende zuerst, mit Gesamtsumme; bei vielen
  Spenden über mehrere Seiten.
- Unter der Unterschrift steht wie im Vordruck kein Name. Wer unterschrieben hat, steht in der
  `Ausfertigung` und in der Liste „Ausgestellt“ (ADR 0130 bleibt sonst unverändert). Die
  Einstellung „Unterschrift: Name und Funktion“ entfällt deshalb in der Oberfläche und ist keine
  Pflichtangabe mehr; die Spalte `unterzeichnet_von` bleibt, damit nichts verloren geht.
- Neue Einstellung `SpendenEinstellungen.maschinell_angezeigt`: Nur wenn die Tafel die
  maschinelle Erstellung dem Finanzamt angezeigt hat (R 10b.1 Abs. 4 EStR), steht der Satz dazu
  unten auf der Bestätigung.
- Die laufende Nummer steht klein unten rechts, damit sich jede Bestätigung wiederfinden lässt.
- Schon gespeicherte, unterschriebene Ausfertigungen bleiben, wie sie sind (ADR 0130); nur neu
  erzeugte PDFs haben den neuen Aufbau.

## Begründung

Der Vordruck ist das, was Finanzämter und Spender kennen; ein gleich aussehender Beleg wirft
keine Fragen auf, egal aus welchem Programm er kommt. Feste Maße lassen sich mit dem
Fließtext-Rahmen nicht einhalten, deshalb ein eigener, kleiner Zeichner nur für diesen Beleg.
Der Satz zur maschinellen Erstellung ist nur richtig, wenn die Anzeige beim Finanzamt wirklich
erfolgt ist – deshalb schaltet ihn die Tafel selbst ein.
