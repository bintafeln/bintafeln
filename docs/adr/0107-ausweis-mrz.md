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

- Erkennung in zwei Stufen (Logik in `apps/antraege/ausweis_pruefung.py`):
  1. **PassportEye** (bevorzugt) findet die MRZ-Zone selbst im Foto, schneidet nur dieses Band aus,
     vergrößert es und liest es mit **Tesseract**; die zeichenweise Auswertung kennt die festen
     Positionen der MRZ und korrigiert typische OCR-Verwechslungen (O/0, B/8).
  2. **Tesseract über das ganze Bild** + Paket **mrz** als Rückfall, falls kein Band gefunden wird.
  Beide nutzen Tesseract (im App-Image, Dockerfile) und werten nach ICAO 9303 mit Prüfziffern aus.
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
Fundament) und spart eine Rechtsgrundlage für die Übermittlung.

Die erste, leichte Variante (Tesseract über das ganze Bild + mrz) scheiterte in der Praxis an
echten Handy-Fotos: Tesseract fand die MRZ-Zeilen neben Gesicht, Rand und Muster meist gar nicht,
und selbst bei sauberen Bildern verwechselte es O/0, sodass die Prüfziffern scheiterten. Darum
liest jetzt **PassportEye** zuerst: Es grenzt die MRZ-Zone im Bild ein und liest nur dieses Band –
der entscheidende Schritt, der auf realen Fotos erst Treffer bringt. Das zieht als feste
Abhängigkeiten scikit-image/scipy/numpy u. a. nach (bewusst die „größere" Variante, da
Zuverlässigkeit hier wichtiger ist als ein schlankes Image); alle permissiv lizenziert (MIT/BSD),
AGPL-verträglich. Der bisherige Weg bleibt als Rückfall erhalten.
