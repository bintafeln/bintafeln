# 0060: Abrechnung der Ausgabestellen

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Die Ausgabestellen rechnen jeden Monat ab: Den Beiträgen der Kunden stehen eigene Ausgaben
gegenüber (Fahrtkosten, Reinigung, Müll, Miete, Anschaffungen …). Bisher geschieht das auf
Papier; Quittungen gehen verloren, und das Büro tippt die Einnahmen aus der Kasse ab.

## Entscheidung

- Zuschaltbares Modul `abrechnung` (ADR 0049). Je Ausgabestelle und Monat eine
  `Monatsabrechnung` mit dem Status offen → eingereicht → bestätigt. Das Büro kann eine
  eingereichte oder bestätigte Abrechnung mit Grund zurückgeben; dann ist sie wieder offen.
- **Einnahmen** kommen allein aus den Kontobuchungen der Ausgabestelle (Kasse, ADR 0014). Als
  Einnahme zählt das Bargeld („Bar eingenommen“: bar gezahlte Beiträge und Einzahlungen).
  Verrechnetes Guthaben und Angeschriebenes stehen nur zur Information da. Beim Einreichen werden
  die Zahlen in der Abrechnung festgehalten, weil Buchungen nach ihrer Frist gelöscht werden und
  spätere Buchungen eine eingereichte Abrechnung nicht verändern dürfen.
- **Ausgaben** (`Posten`) trägt die Ausgabestelle selbst ein: Datum (nicht nach Monatsende),
  Betrag, Art aus einer pflegbaren Liste, „Bezahlt an“, Anmerkung und eine Quittung. Das Feld
  „Quittung fotografieren“ öffnet am Handy oder Tablet die Kamera (`capture="environment"`),
  alternativ Foto oder PDF wählen. Quittungen liegen verschlüsselt über `apps.core.privatdateien`.
- Nach dem Einreichen sind Ausgaben gesperrt, bis das Büro zurückgibt.
- Das Büro sieht je Monat alle Ausgabestellen mit Einnahmen, Ausgaben, Saldo und Status und lädt
  die Quittungen als ZIP herunter (je Ausgabestelle ein Ordner, Dateiname mit Datum, Art und
  Betrag). Jede Abrechnung gibt es als PDF mit Unterschriftsfeldern.
- Rechte: „Abrechnung der eigenen Ausgabestelle führen“ (Vorgabe Ausgabe und Büro; gilt nur für
  die zugeordneten Ausgabestellen, ADR 0034, also auch für die Konten der Ausgabestellen,
  ADR 0059) und „Abrechnungen aller Ausgabestellen prüfen“ (Vorgabe Büro).
- Aufbewahrung einstellbar, Vorgabe 5 volle Kalenderjahre nach dem Jahr der Abrechnung; danach
  löscht `Modul.fristen` Abrechnungen samt Quittungen.
- Das Menü zeigt eine Adresse, die unter mehreren Rechten eingetragen ist, nur einmal.

## Begründung

Die Einnahmen stehen schon in der Kasse; sie noch einmal einzugeben, wäre doppelte Arbeit und
eine Fehlerquelle. Das Festhalten beim Einreichen macht die Abrechnung prüfbar und unabhängig von
Löschfristen. Fotos direkt aus dem Browser brauchen keine App und funktionieren auf den Tablets
am Einlass. Steuerliche Aufbewahrungsfristen hängen vom Verein ab, deshalb ist die Frist
einstellbar.
