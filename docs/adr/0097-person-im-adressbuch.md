# 0097: Die Person im Adressbuch als ein Datensatz

- Status: Angenommen
- Datum: 2026-10-31

## Problem

Die Daten einer mitarbeitenden Person liegen heute an bis zu vier Stellen, alle am Login-Konto
(`konten.Benutzer`) aufgehängt und nirgends an der Adresse:

- das **Konto** (Anmeldung, Rollen, Beschäftigung),
- die **Stammdaten** (`konten.Stammdaten`: Anschrift, Telefon, Notfallkontakt, Führerschein, IfSG),
- die **Personaldaten** (`apps/personal`: Verträge, Abwesenheiten, Urlaub, Stunden, Stempeln),
- die **Einteilung**: im Dienstplan ein eigenes `Helfer`-Modell (mit oder ohne Konto), im
  Fahrdienst direkt das Konto.

Dieselbe Person muss dadurch mehrfach erfasst werden. Wer als ehrenamtlicher Helfer im Adressbuch
steht, taucht im Dienstplan nicht von selbst auf. Und es fehlt die Möglichkeit, in der Adressliste
anzugeben, ob und ab wann eine Person eingeteilt werden kann.

## Entscheidung

Die **Adresse (Person) wird der zentrale Datensatz** für eine Person. Alles Übrige hängt künftig an
ihr:

- Wer sich anmeldet, bekommt ein **Konto, das 1:1 fest mit der Adresse verknüpft** ist
  (`Adresse.konto`). Anmeldung, Passwort, Zwei-Faktor und Rollen bleiben technisch am Konto; in der
  Oberfläche ist es **eine Maske** bei der Adresse.
- Stammdaten, Personaldaten (Führerschein, IfSG, Verträge, Arbeitszeit) und die Einteilung in
  Dienstplan und Fahrdienst beziehen sich auf die Person.
- Eine als **Helfer** markierte, **aktive** Person steht automatisch im Dienstplan und Fahrdienst
  zur Auswahl. Die Adressliste zeigt und filtert Helfer (aktiv/inaktiv).
- Ihre **Einsatztage** (feste Besetzungen) erscheinen bei der Person.

Das Adressbuch bleibt zugleich der Ort für externe Kontakte (Spender, Märkte, Behörden).

## Umsetzung in Schritten

Der Umbau berührt die sensibelsten Daten, die Auskunft nach Art. 15, die Datensicherung, den
Import, die Löschfristen und viele Tests. Er kommt deshalb – wie es die Grundregeln verlangen
(kleine PRs, Tests grün, Migrationen aus jeder Version und umkehrbar, keine Migration löscht Daten)
– als Folge fertiger PRs mit gleichem Endergebnis:

1. **Adresse ↔ Konto und Helfer-Kennzeichen** (dieser PR): `Adresse.konto` (1:1 zum Konto),
   `Adresse.helfer` und `Adresse.helfer_aktiv`. Die bisher über die Kategorie „Ehrenamtliche
   Helfer“ geführten Personen werden per Datenmigration auf `helfer=True` übernommen. In der
   Adress-Maske lässt sich das Konto verknüpfen; ist eines verknüpft, führt ein Verweis direkt zu
   dessen Stammdaten. Adressliste: Spalte und Filter „Helfer“.
2. **Dienstplan und Fahrdienst wählen Personen** aus den aktiven Helfern der Adressen; das alte
   `Helfer`-Modell und der direkte Konto-Bezug im Fahrdienst entfallen, eine Migration hängt
   bestehende Pläne, Ausfälle und Ersätze um.
3. **Einsatztage bei der Person** anzeigen; Auskunft Art. 15, Datensicherung, Import und
   Löschfristen auf den neuen Aufbau nachziehen.

## Begründung

Eine Person – ein Datensatz. Das Adressbuch ist schon heute die Liste aller Personen und kennt
bereits die Kategorie „Ehrenamtliche Helfer“. Die Einteilung an die Person zu binden, erspart die
Mehrfacherfassung und lässt Helfer ohne eigenes Konto genauso führen wie solche mit Anmeldung.
Login, Rollen und Zwei-Faktor bleiben am Konto, weil die Anmeldung technisch ein Konto braucht;
die feste 1:1-Verknüpfung macht daraus für die Nutzenden trotzdem eine Maske.
