# ADR 0131: Angebote mit Anmeldung

## Problem

Tafeln bieten neben der Ausgabe gelegentlich etwas mit begrenzten Plätzen an, z. B. einen
Kochkurs mit 12 Plätzen. Teilnehmen sollen nur Kunden. Die Tafel will am Einlass sammeln, wer
Interesse hat – aber nicht 200 Menschen fragen, wenn 15 bis 20 Interessierte reichen.

## Entscheidung

Ein zuschaltbares Modul `angebote` (ADR 0049), allgemein gehalten („Angebot mit Anmeldung“),
damit es auch für einen Ausflug oder Nähkurs taugt.

- **`Angebot`:** Bezeichnung, Beschreibung, Zeitraum der Anmeldung, `plaetze` und `hoechstens`
  (Interessierte höchstens). Bei der Höchstzahl schließt die Liste von selbst; zusätzlich lässt
  sie sich von Hand schließen.
- **`Interesse`:** eine **Person** eines Haushalts, nicht der Haushalt – ein Platz im Kurs ist
  für einen Menschen. Mehrere Personen eines Haushalts werden einzeln eingetragen und zählen
  einzeln. Der Eintrag hängt an der **Kundennummer** und hält Vorname, Nachname, Geburtsdatum
  und Telefon fest, wie sie beim Eintragen im Kundenstamm standen: Personen haben nach einem
  Import andere Kennungen (wie bei Notizen und Teilnahmen, ADR 0026, 0032).
- **Eintragen nur am Einlass:** über den Hook `Modul.einlass` – ein Hinweis je laufendem
  Angebot mit Stand der Liste und einem Knopf. So ist sichergestellt, dass nur aufgerufene
  Kunden eingetragen werden; der Haushalt wird wie überall über `zugang.haushalt()` geprüft.
  Kein modulspezifischer Code im Kern.
- **Plätze:** Vorgabe ist die Reihenfolge der Anmeldung (`ablauf.plaetze_vergeben()`): die
  ersten bekommen „Platz zugesagt“, die übrigen werden „Nachrücker“. Das Büro kann jeden Stand
  von Hand ändern. Absagen zählen nicht mit; ihr Platz auf der Liste wird wieder frei.
- **Rechte:** `angebote.verwalten` (Büro: anlegen, Liste mit Telefon, Plätze) und
  `angebote.eintragen` (Büro und Ausgabe: am Einlass ein- und austragen). Der Einlass sieht die
  Liste der Interessierten nicht.
- **Frist:** Je Angebot eine Zahl von Tagen nach dem Ende; danach werden die Einträge der Kunden
  gelöscht (`ablauf.fristen_anwenden()`), das Angebot selbst bleibt. Die Einträge stehen in der
  Auskunft nach Art. 15 zum Haushalt.
- Anwesenheit an den Terminen wird in dieser Fassung nicht festgehalten.

## Begründung

- Die Höchstzahl hält die Liste klein: Datensparsamkeit und weniger Enttäuschung bei Kunden,
  die sich umsonst eintragen würden.
- Beim Eintragen wird die Zeile des Angebots gesperrt, damit zwei Einlass-Plätze gleichzeitig
  die Höchstzahl nicht überschreiten.
- Die Regeln liegen ohne Oberfläche in `apps/angebote/ablauf.py` und sind so testbar.
