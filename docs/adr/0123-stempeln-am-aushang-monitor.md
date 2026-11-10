# ADR 0123: Arbeitszeit am Aushang-Monitor stempeln

## Problem

Angestellte stempeln unter „Meine Arbeitszeit“ mit dem eigenen Konto – auch von zu Hause. Die
Tafel will sicher sein, dass vor Ort gestempelt wird, aber weder ein eigenes Stempel-Gerät
aufstellen noch ihr WLAN (auch kein Gast-WLAN) für Handys öffnen, und keinen ausgedruckten
QR-Code aufhängen, der sich abfotografieren ließe.

## Entscheidung

Gestempelt wird am **Aushang-Monitor** (ADR 0080), der ohnehin vor Ort hängt und ohne Anmeldung
läuft:

- **Knopf „Stempeln“** oben am Monitor, je Monitor einstellbar (`Aushang.stempeln`): Vorgabe,
  an, aus. In der Vorgabe nur an Monitoren mit einer Seite, die das vorsieht
  (`Aushangseite.stempeln_standard`, gesetzt vom Dienstplan) – der Kern kennt kein Modul beim
  Namen. Die Regel steht in `apps/aushang/stempeln.py` (`an()`).
- **Mit Name und PIN:** dieselbe persönliche PIN wie für das Ändern der Pläne
  (`apps/aushang/pin.py`, gehasht, Sperre nach Fehlversuchen). Erst wird die PIN geprüft, dann
  zeigt der Monitor Stand und passende Knöpfe; gestempelt wird über
  `apps.personal.arbeitszeit.stempeln()`.
- **Mit QR-Code:** Der Monitor zeigt eine unterschriebene, kurzlebige Marke
  (`django.core.signing`, 90 Sekunden gültig, alle 30 Sekunden neu). Das Handy löst sie ein und
  bekommt in seiner Sitzung für fünf Minuten die Freigabe (`arbeitszeit.freigeben()`); die
  Freigabe übersteht die Anmeldung. Gestempelt wird dann wie gewohnt unter „Meine Arbeitszeit“.
- **„Stempeln nur am Aushang-Monitor“** (`ArbeitszeitEinstellungen.nur_am_monitor`, Vorgabe aus):
  Ohne Freigabe fehlen die Knöpfe unter „Meine Arbeitszeit“, und die Stempel-Adresse lehnt ab
  (`arbeitszeit.hier_erlaubt()`). Nachtragen durch das Personal bleibt überall möglich.

## Begründung

Der Monitor ist der einzige Bildschirm, der an jedem Standort schon da ist; er macht einen
wechselnden Code möglich, ohne Netz-Freigaben und ohne Standortdaten der Handys. Die PIN gibt es
bereits, mit Schutz gegen Ausprobieren. Zur Auswahl am Monitor stehen nur Namen von Personen, die
Arbeitszeit erfassen und eine PIN haben – wie bei den Plänen zeigt der Monitor nie mehr als Namen.
Eine Prüfung der Netz-Adresse oder des GPS-Standorts wurde verworfen: wechselnde Adressen, nötiges
WLAN für Handys bzw. ungenaue, fälschbare und datenschutzrechtlich heikle Standortdaten.
