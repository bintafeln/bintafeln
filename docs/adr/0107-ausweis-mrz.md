# ADR 0107: Lokale Ausweisprüfung über die MRZ

## Problem

Antragstellende laden oft Fotos ihres Ausweises oder Passes als Nachweis hoch. Teils weicht die
Staatsangehörigkeit auf dem Dokument von der im Antrag angegebenen ab. Die Tafel möchte das beim
Bearbeiten und bei der Aufnahme leicht erkennen können. Ausweisbilder und Nationalität sind
besonders sensible Daten – sie dürfen nicht ungefragt an einen externen Dienst (KI, OCR-Cloud)
gesendet werden, und die Prüfung darf nicht automatisch über Menschen entscheiden.

## Entscheidung

bintafeln liest die **maschinenlesbare Zone (MRZ)** eines Ausweis-Fotos **lokal auf dem Server**
und zeigt das Ergebnis als Hinweis. Kein externer Dienst, keine KI – das Bild verlässt den Server
nicht.

- OCR mit **Tesseract** (im App-Image, Dockerfile), MRZ-Auswertung mit dem Paket **mrz** (ICAO
  9303, Prüfziffern). Logik in `apps/antraege/ausweis_pruefung.py`.
- Die MRZ liefert Dokumentart, ausstellendes Land und Staatsangehörigkeit als ISO-Code; über die
  vorhandene Länderliste (`apps/core/auswahl.STAATEN`, alpha-2 → alpha-3 im Modul) wird der
  deutsche Name gezeigt und mit der Angabe im Antrag verglichen.
- **Zuschaltbar**, standardmäßig aus (`AntragEinstellungen.ausweis_pruefen`); ein Knopf
  „Ausweis prüfen" je Nachweis-**Foto** auf der Antragsseite und im Aufnahme-Assistenten (Recht
  `antraege.sehen`). Nur **nach Klick**, nie automatisch; jeder Aufruf wird protokolliert (wie das
  Ansehen eines Nachweises).
- **Ehrlich bei Unsicherheit:** Fehlt die MRZ oder ist sie unleserlich, meldet bintafeln „kein
  maschinenlesbarer Ausweis erkannt" und rät nichts. Das Ergebnis ist nur ein Hinweis; die
  Entscheidung trifft ein Mensch.

## Begründung

Die MRZ ist standardisiert und mit Prüfziffern gesichert, daher lokal zuverlässig lesbar, wo sie
klar fotografiert ist. Lokal statt Cloud/KI schützt die sensiblen Daten (Datenschutz als
Fundament) und spart eine Rechtsgrundlage für die Übermittlung. Die leichte Variante (Tesseract +
mrz) kommt ohne schwere Bildbibliotheken aus; reicht die Trefferquote in der Praxis nicht, lässt
sie sich später um eine robustere MRZ-Erkennung (z. B. passporteye) ergänzen, ohne die Oberfläche
zu ändern.
