# 0101: Gemeinsame Personennummern-Reihe für Mitarbeitende und Mitglieder

- Status: Angenommen
- Datum: 2026-11-02

## Problem

Mitarbeitende brauchen eine feste, eindeutige Nummer (für eine ausdruckbare Mitarbeitendenliste).
Ist eine Person zugleich Vereinsmitglied, soll ihre Nummer der Mitgliedsnummer entsprechen – es
soll also keine zweite, abweichende Nummer für dieselbe Person geben, und keine Nummer darf doppelt
vergeben werden.

## Entscheidung

- Es gibt **eine gemeinsame Nummernreihe** für Mitarbeitende und Mitglieder. Mitgliedsnummern und
  **Personalnummern** (`Stammdaten.personalnummer`) stammen aus derselben fortlaufenden Reihe und
  sind damit nie doppelt.
- Die Reihe führt der vorhandene Mitglieder-Zähler (`MitgliederEinstellungen.naechste_nummer`,
  gesperrt über `naechste_nummer()`); beim Anlegen eines Mitarbeitenden wird die nächste freie
  Nummer **automatisch** aus dieser Reihe vergeben. Jede Vergabe (Mitglied oder Mitarbeiter)
  schiebt den Zähler weiter.
- **Anzeige:** Ist die Person Mitglied (über ihren Adressbuch-Eintrag), gilt ihre Mitgliedsnummer;
  sonst die Personalnummer (`verwaltung.personennummer()`). Mitglieder bekommen keine zweite
  Nummer.
- Eine von Hand eingetragene Mitgliedsnummer, die schon als Personalnummer vergeben ist, wird
  abgelehnt.

## Begründung

- Der Mitglieder-Zähler sperrt die Zeile beim Vergeben und überspringt belegte Nummern; er eignet
  sich damit als einzige Quelle der Reihe, ohne einen zweiten Zähler, der auseinanderlaufen könnte.
- `konten` greift lazy auf `mitglieder` zu (wie `adressen` es schon tut); das Modul ist immer
  installiert, auch wenn es in den Tafel-Einstellungen ausgeschaltet ist.

## Folgen

- Eine Datenmigration gibt bereits vorhandenen, aktiven Mitarbeitenden (die keine Mitglieder sind)
  fortlaufende Personalnummern und setzt den Zähler darüber. Nichts wird gelöscht; die Migration ist
  umkehrbar (Personalnummern werden wieder entfernt).
- Wird jemand erst Mitarbeiter und später Mitglied, zählt dann die Mitgliedsnummer; die vergebene
  Personalnummer bleibt bestehen (sie wird nicht neu genutzt, damit keine Dopplung entsteht).
- Die Personalnummer wird normalerweise automatisch vergeben. Mit dem Recht
  „mitarbeitende.nummer“ (Vorgabe: nur Admin) kann man sie im Mitarbeiter-Profil auch von Hand
  setzen; sie muss eindeutig bleiben (nicht schon als Personal- oder Mitgliedsnummer vergeben),
  und die gemeinsame Reihe rückt über eine von Hand gesetzte Nummer hinaus. Wer das Recht nicht
  hat, legt Mitarbeitende an wie bisher – die Nummer kommt dann automatisch. Die Nummer steht im
  Mitarbeiter-Profil und in der Mitarbeitendenliste (Spalte „Nummer“, auch im CSV-/PDF-Export).
