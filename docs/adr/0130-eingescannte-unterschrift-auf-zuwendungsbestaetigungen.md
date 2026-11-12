# ADR 0130: Eingescannte Unterschrift auf Zuwendungsbestätigungen

## Problem

Zuwendungsbestätigungen wurden gedruckt und von Hand unterschrieben; für alle galt ein
gemeinsamer Text „Name und Funktion“. Beim Versand im großen Stil (Dankesbriefe per E-Mail) ist
das nicht praktikabel. Eine hinterlegte, eingescannte Unterschrift löst das – aber eine
Unterschrift ist persönlich: Niemand darf mit der Unterschrift einer anderen Person eine
Bestätigung ausstellen, für die diese Person dann haftet (§ 10b Abs. 4 EStG).

## Entscheidung

- **Unterschrift je Konto:** `Unterschrift` (Bild, verschlüsselt über `privatdateien`, dazu
  Name und Funktion) gehört zu genau einem Konto. Hinterlegt, angesehen, geändert und gelöscht
  wird sie nur auf der eigenen Seite. Die Vorschau hat keine Kennung in der Adresse, sie zeigt
  immer die des angemeldeten Kontos. Es gibt keine Ansicht und keine Funktion, die die
  Unterschrift eines anderen Kontos liefert – auch nicht für den Admin.
- **Nur wer ausstellt, unterschreibt:** `bestaetigung.unterschreiben(b, benutzer)` nimmt die
  Unterschrift der Person, die ausstellt. Es gibt keine Auswahl „unterschreiben als …“.
- **Name und Funktion persönlich:** Unter dem Bild stehen Name und Funktion aus der eigenen
  Unterschrift. Der gemeinsame Text aus den Spenden-Einstellungen gilt nur noch für
  Bestätigungen ohne Bild (Linie zum Unterschreiben von Hand).
- **Das unterschriebene PDF wird gespeichert, nicht neu berechnet:** `Ausfertigung` hält das
  fertige PDF fest (verschlüsselt). Ausgegeben wird ab dann genau dieses. Dadurch bleibt das
  Dokument, wie es ausgestellt wurde, und die Unterschrift muss dafür nicht aufbewahrt werden –
  etwa wenn jemand aus dem Vorstand ausscheidet und seine Unterschrift löscht.
- **Neu ausfertigen statt ändern:** Eine andere Person mit eigener Unterschrift kann dieselbe
  Bestätigung (gleiche Nummer, gleicher Inhalt) mit ihrer Unterschrift neu ausfertigen. Es
  entsteht eine weitere `Ausfertigung`; die frühere bleibt unverändert gespeichert, die neueste
  gilt.
- Stornierte Bestätigungen werden wie bisher neu erzeugt: mit Vermerk, ohne Unterschrift.
- Bestätigungen ohne Bild entstehen weiter bei jedem Aufruf neu aus den Daten (wie bisher).
- Kein neues Recht: Wer „Zuwendungsbestätigungen ausstellen und stornieren“ darf, kann seine
  Unterschrift hinterlegen.

## Begründung

- Die Trennung nach Konto ist im Datenmodell und in den Wegen dorthin verankert, nicht nur in
  der Oberfläche: Ohne das angemeldete Konto kommt man an keine Unterschrift.
- Gelöscht wird eine Unterschrift endgültig, nicht in den Papierkorb (ADR 0073): Niemand soll
  sie wiederherstellen können.
- Die Unterschrift steht (ohne Bild) in der Auskunft nach Art. 15 zum Konto.
- **Steuerlich:** Zuwendungsbestätigungen ohne eigenhändige Unterschrift erkennt das Finanzamt
  nur an, wenn das maschinelle Verfahren dort angezeigt wurde (R 10b.1 Abs. 4 EStR). Das kann
  bintafeln nicht prüfen; Seite und Handbuch weisen darauf hin.
