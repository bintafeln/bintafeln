# ADR 0137: Stempel der Tafel auf Zuwendungsbestätigungen

## Problem

Neben der eingescannten Unterschrift (ADR 0130) soll auf den Zuwendungsbestätigungen auch der
Stempel der Tafel stehen, wie von Hand gestempelt. Hochgeladene Bilder haben meist einen weißen
Hintergrund; über dem Text der Bestätigung würde er Teile davon verdecken.

## Entscheidung

- Der Stempel gehört der Tafel, nicht einer Person: ein Bild in `SpendenEinstellungen.stempel`,
  verschlüsselt über `apps.core.privatdateien` (Ordner `stempel`). Hochladen und Entfernen unter
  „Einstellungen → Spenden und Zuwendungsbestätigungen“, Recht `einstellungen.spenden`.
- Auf der Bestätigung (`vordruck.stempel()`) steht er rechts neben der Unterschrift über der
  Linie, höchstens 95 × 62 pt, um 8° gedreht – wie von Hand gestempelt. Er steht auf jeder neu
  erzeugten Bestätigung, auch wenn sie von Hand unterschrieben wird.
- Unterschrift und Stempel werden beim Hochladen freigestellt (`unterschrift.freistellen()`):
  Helles wird durchsichtig, mit weichem Übergang, Tinte bleibt deckend. So verdeckt keines der
  Bilder Text der Bestätigung.
- Schon gespeicherte Ausfertigungen (ADR 0130) ändern sich nicht.

## Begründung

Ein Stempel ist das Zeichen der Einrichtung, deshalb eine Einstellung der Tafel und nicht wie die
Unterschrift an ein Konto gebunden. Das Freistellen beim Hochladen genügt einmal; das gespeicherte
PNG mit Alphakanal wird von ReportLab ohne weiteren Aufwand durchsichtig gezeichnet.
