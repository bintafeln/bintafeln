# ADR 0157: Touren – Statistik

## Problem

Für Vorstand, Verband und die eigene Planung braucht die Tafel Zahlen zu den Touren: wie viel
abgeholt wurde, von wem (Märkte, Ketten), mit wie vielen Fahrten und Kilometern. Die Daten
liegen seit den Lieferscheinen (ADR 0149) und dem Fahrtenbuch (ADR 0151) vor, ausgewertet wurden
sie nicht.

## Entscheidung

- **Eine Seite „Touren → Statistik“** je Jahr (`apps/touren/statistik.py`,
  `views_statistik.py`, Recht `touren.statistik`, Vorgabe Büro): Kennzahlen mit Vergleich zum
  Vorjahr, darunter Abschnitte je Monat, Warengruppe, Tour, Fahrzeug, Station und Handelskette,
  dazu die Stationen ohne Lieferschein im Jahr. Aufbau und Darstellung wie die übrige Statistik
  (ADR 0036): jede Grafik auch als Tabelle und CSV, gezeichnet mit `apps.statistik.diagramme`.
- **Kisten werden in Kilogramm umgerechnet**, damit es eine Gesamtzahl gibt: „kg je Kiste“ der
  Warengruppe (`Warengruppe.kiste_kg`), sonst das allgemeine Durchschnittsgewicht
  (`TourenEinstellungen.kiste_kg`, Vorgabe 10 kg). Die Tabellen zeigen Kisten und gewogene
  Kilogramm weiter getrennt, damit die Schätzung erkennbar bleibt. Umgerechnet wird beim
  Auswerten; ein geändertes Gewicht wirkt auch rückwirkend.
- **Keine Auswertung je Person.** Wer wie oft, wie lange oder wie weit gefahren ist, wertet
  bintafeln nicht aus – weder als Abschnitt noch als Spalte. Fahrten zählen je Tour und je
  Fahrzeug.
- **Stunden** zählen nur Fahrten, die am Handy beendet wurden; im Büro nachgetragene haben keine
  verlässliche Endzeit.

## Begründung

- Eine Statistik je Fahrer wirkt beobachtend und passt nicht zu ehrenamtlicher Arbeit; für die
  Fragen der Tafel genügen Tour und Fahrzeug.
- Die Umrechnung beim Auswerten statt beim Speichern hält die Lieferscheine unverändert (was
  unterschrieben wurde, bleibt) und lässt das Durchschnittsgewicht nachträglich verbessern.
- Ein Gewicht je Warengruppe ist die einfachste Verfeinerung, die spürbar genauer ist: Eine
  Kiste Brot wiegt deutlich weniger als eine Kiste Gemüse.
