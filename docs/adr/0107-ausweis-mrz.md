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
- **PDF-Nachweise werden einbezogen** (`apps/antraege/pdf_bilder.py`, PDFium über `pypdfium2`): Viele
  laden ihren Ausweis als PDF hoch (oft mit sehr guten Scans). Für die Prüfung werden die ersten
  Seiten lokal in Bilder gerendert und wie Fotos behandelt (`ausweis_pruefung.pruefen_datei`). In
  der Oberfläche zeigt die Nachweis-Kachel eines PDFs eine kleine Vorschau der ersten Seite
  (`nachweis_vorschau`, lokal gerendert, nicht serverseitig zwischengespeichert, da der Nachweis
  verschlüsselt liegt); ein Klick öffnet weiterhin das vollständige PDF.
- Die MRZ liefert Dokumentart, ausstellendes Land und Staatsangehörigkeit als ISO-Code; über die
  vorhandene Länderliste (`apps/core/auswahl.STAATEN`, alpha-2 → alpha-3 im Modul) wird der
  deutsche Name gezeigt und mit der Angabe im Antrag verglichen.
- **Zuschaltbar**, standardmäßig aus (`AntragEinstellungen.ausweis_pruefen`); ein Knopf
  „Ausweis prüfen" je Nachweis-**Foto** auf der Antragsseite und im Aufnahme-Assistenten (Recht
  `antraege.sehen`). Jeder Aufruf wird protokolliert (wie das Ansehen eines Nachweises).
- **Automatischer Abgleich über alle Nachweise** (`apps/antraege/ausweis_scan.py`): Ein Antrag wird
  über **alle** Bild-Nachweise geprüft; eine **Abweichung** liegt nur vor, wenn die erkannte
  Staatsangehörigkeit zu **keiner** angegebenen passt (Hauptperson + Angehörige). Das Ergebnis steht
  am Antrag (`ausweis_staat`, `ausweis_abweichung`, `ausweis_anhang`, `ausweis_geprueft_am`). **Neue
  Anträge** werden beim Eingang automatisch geprüft (ein Daemon-Thread, der seine DB-Verbindung
  selbst schließt – kein Celery, passend zu den gunicorn-Prozessen); über die Antragsliste lassen
  sich auf Befehl **alle** Anträge prüfen (ebenfalls im Hintergrund, Fortschritt im gemeinsamen
  Datenbank-Cache, ADR 0093). Die Sammelprüfung arbeitet nur noch **noch nicht geprüfte** Anträge
  (ohne `ausweis_geprueft_am`) ab und ist damit **fortsetzbar**: Beendet ein App-Neustart (z. B.
  ein Update) den Hintergrund-Thread, bleibt der Fortschritt im Cache, der Lauf gilt ohne frisches
  Lebenszeichen (`aktualisiert`, Schwelle `VERWAIST_SEKUNDEN`) als **unterbrochen**, und der nächste
  Aufruf der Antragsliste bzw. das Fortschritt-Polling setzt ihn automatisch an der Abbruchstelle
  fort (`fortsetzen_wenn_unterbrochen()`). Ein verwaister Lauf blockiert den Start-Knopf nicht mehr.
  **Robust gegen einzelne kaputte Nachweise:** Die Sammelprüfung läuft in einem **eigenen Prozess**
  (Management-Befehl `ausweise_pruefen`, getrieben von `alle_pruefen_jetzt`), mit einem **Zeitlimit
  je Antrag** (`ZEIT_JE_ANTRAG`, SIGALRM). So hält ein Nachweis, der eine Bild-/PDF-Bibliothek zum
  **Absturz** (Segfault) bringt oder **endlos hängen** lässt – was Python im laufenden Prozess nicht
  abfangen kann – den Lauf nicht mehr an: Bei einem Hänger greift das Zeitlimit, bei einem Absturz
  erkennt der Treiber den fehlenden Fortschritt; der Antrag wird übersprungen (als geprüft markiert)
  und der Lauf läuft weiter. Zusätzlich meldet `apps.core.privatdateien.lesen()` eine nicht lesbare
  Datei als `None` (statt zu werfen), wie sein Docstring zusagt. Lässt sich der Unterprozess nicht
  starten, rechnet der Treiber im selben Prozess weiter (dann ohne Absturz-/Hänger-Schutz).
  Gefunden wird nur ein **Hinweis**: in der Liste ein Marker „Ausweis ≠"
  neben der Nummer, auf der Antragsseite ein Banner **mit Bild** und – mit `antraege.bearbeiten` –
  die Übernahme der erkannten Staatsangehörigkeit in den Antrag. Wird kein Ausweis gefunden oder
  passt alles, gibt es **keinen** Hinweis. Es wird nie etwas automatisch geändert.
- **Ehrlich bei Unsicherheit:** Fehlt die MRZ oder ist sie unleserlich, meldet bintafeln „kein
  maschinenlesbarer Ausweis erkannt" und rät nichts. Das Ergebnis ist nur ein Hinweis; die
  Entscheidung trifft ein Mensch.
- **Darstellung:** Das Ergebnis erscheint in voller Breite unter den Nachweis-Kacheln (nicht im
  schmalen Vorschaukästchen). Im Mittelpunkt steht die erkannte **Staatsangehörigkeit**; weicht sie
  von der Antragsangabe ab, kommt ein deutlicher Hinweis. Wer bearbeiten darf, kann die
  Staatsangehörigkeit im Antrag über ein Auswahlmenü direkt überschreiben
  (`nachweis_staat_uebernehmen`, Recht `antraege.bearbeiten`).

- **Sammel-Prüfseite** (`antraege:ausweis_pruefung_liste`, Recht `antraege.bearbeiten`): Nach einem
  großen Lauf müssen Abweichungen nicht mehr Antrag für Antrag geöffnet werden. Eine eigene Seite
  listet alle offenen Abweichungen (`ausweis_abweichung=True`, noch nicht erledigt) mit kleiner
  Vorschau des beim Scan gewählten Nachweises (`ausweis_miniatur`, lokal gerendert – Bild verkleinert
  oder erste PDF-Seite, nichts zwischengespeichert), der angegebenen und der erkannten
  Staatsangehörigkeit und je Zeile drei Aktionen (`ausweis_entscheiden`): **Übernehmen** (erkannten
  Staat in den Antrag schreiben, wie das Auswahlmenü auf der Antragsseite), **Nicht übernehmen**
  (Antrag bleibt, Hinweis erledigt) und **Ansehen** (Antrag in neuem Tab). Eine abgeschlossene
  Abweichung merkt sich das neue, abgeleitete Feld `Antrag.ausweis_erledigt`; sie verschwindet sofort
  aus der Liste und aus dem Menü-Zähler. Weiterhin nur ein Hinweis, die Entscheidung trifft ein
  Mensch.

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

## Nachtrag: Staatsangehörigkeit aus dem Textfeld, wenn keine MRZ (Stufe 3)

Die MRZ steht nur auf **einer** Seite des Ausweises. Lädt jemand nur die andere Seite hoch, fanden
Stufe 1 (PassportEye) und Stufe 2 (ganzes Bild) nichts. Als **dritte Stufe** liest `_staat_aus_text`
den freien OCR-Text (deutsch+englisch) und sucht die Beschriftung
**„Staatsangehörigkeit / Nationality"**; im Ausschnitt dahinter (Zeile + zwei Folgezeilen) erkennt
`_code_aus_fenster` einen **alpha-3-Ländercode** (z. B. `SYR`), einen **deutschen Ländernamen** oder
das Adjektiv **„deutsch"** und macht daraus einen Code. Gewertet wird nur, was zu einem **gültigen
Land** (`ALPHA3_NAME`/`STAATEN`) gehört; Alltagswörter wie „and"/„are" (Andorra/VAE) sind gesperrt,
um Fehltreffer zu vermeiden.

Der so gewonnene Befund ist bewusst als **schwächerer Hinweis** markiert (`nur_feld=True`, keine
Prüfziffern geprüft) und im Ergebnis entsprechend gekennzeichnet. Das hebt die Trefferquote
deutlich, ohne je etwas automatisch zu entscheiden – die MRZ-Prüfung bleibt die erste Wahl.
