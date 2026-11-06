# ADR 0113: Altersangabe am Einlass farbig nach Geschlecht und Altersband

## Problem

Am Einlass steht bei jeder Person das Geburtsdatum mit Alter (wenn eingeblendet). Beim schnellen
Durchsehen eines Haushalts ist es mühsam, aus den Zahlen herauszulesen, wer Kind, Erwachsener oder
Senior ist und welches Geschlecht vorliegt. Eine farbige Orientierung hilft, ohne eine Zahl zu
verdecken.

## Entscheidung

Die Altersangabe wird als kleines farbiges „Chip" gezeigt. Die Farbe ergibt sich aus:

- **Geschlecht** aus der Anrede: „Frau" → Rosa (`w`), „Herr" → Blau (`m`), „Divers"/leer → neutral
  grau (`n`). Es wird nichts geraten – nur die ausdrücklich gewählte Anrede zählt.
- **Altersband**: unter 18 hell, 18–65 kräftig, über 65 sehr dunkel.

Die CSS-Klasse liefert `Person.alter_farbklasse()` (z. B. `alter-w-jung`, `alter-m-alt`); die Farben
stehen in `bintafeln.css` als feste Werte mit eigener Schriftfarbe, damit sie in hellem wie dunklem
Modus lesbar sind. Ohne Geburtsdatum gibt es keine Farbe (dann steht ohnehin kein Alter da).

## Begründung

Die reine Alterszahl bleibt im Text stehen; die Farbe ist nur eine zusätzliche, schnelle
Orientierung und trägt keine Information allein. Das Geschlecht kommt aus der schon vorhandenen
Anrede – kein neues Feld, keine Datenerhebung. Feste Farben mit eigener Schriftfarbe sind
theme-unabhängig und barrierearm (ausreichender Kontrast). Die Logik sitzt in einer kleinen
Modell-Methode und ist damit testbar, statt in der Vorlage.
