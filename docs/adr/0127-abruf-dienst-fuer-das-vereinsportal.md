# ADR 0127: Eigener Dienst für den Abruf aus dem Vereinsportal

## Problem

Das Modul „Spendenbelege aus dem Vereinsportal“ (ADR 0126) braucht den Finanzexport und die
Liste „Spender mit E-Mail“. Das Vereinsportal bietet dafür keine Schnittstelle; das bisherige
Programm der Tafel bediente die Seiten mit einem ferngesteuerten Browser und fragte nur nach
dem 2FA-Code. Das soll auch in bintafeln gehen. Ein Browser im Programm selbst würde aber jede
Installation um rund ein Gigabyte vergrößern und fremde Webseiten in den Prozess holen, der die
Kundendaten verarbeitet.

## Entscheidung

Ein eigener Dienst `abruf` (`docker/abruf/`, Playwright mit Chromium) übernimmt den Browser.

- Er steht im Compose-Profil `abruf` und läuft nur, wenn die Tafel `COMPOSE_PROFILES=abruf` und
  einen `BINTAFELN_ABRUF_SCHLUESSEL` in die `.env` einträgt. Ohne Schlüssel zeigt bintafeln nur
  das Hochladen von Hand.
- bintafeln spricht ihn im internen Netz über eine kleine HTTP-Schnittstelle an
  (`apps/vereinsportal/abruf.py`): Auftrag starten, 2FA-Code weiterreichen, Stand abfragen,
  abbrechen, Dateien abholen. Jede Anfrage trägt den gemeinsamen Schlüssel.
- Der Stand des Auftrags liegt im Dienst, nicht in bintafeln. So sehen alle Serverprozesse
  dasselbe, und die Seite fragt ihn alle zwei Sekunden ab.
- Adressen der Portal-Seiten, E-Mail und Passwort stehen in `PortalEinstellungen`, das Passwort
  verschlüsselt über `apps.core.geheimnis`. Der Dienst bekommt sie mit dem Auftrag und hält sie
  nur im Arbeitsspeicher; die Dateien liegen in einem vorübergehenden Ordner, bis bintafeln sie
  abgeholt hat.
- Eingelesen wird mit denselben Regeln wie beim Hochladen (`einlesen.py`).

## Begründung

- **Getrennt wie der `updater` (ADR 0043):** Der Teil mit besonderen Fähigkeiten (dort Docker,
  hier ein Browser auf fremden Seiten) läuft für sich; bintafeln tauscht nur Aufträge aus.
- **HTTP statt gemeinsamem Ordner:** Anders als beim Update gehen hier Zugangsdaten und ein
  2FA-Code über die Leitung. Im Arbeitsspeicher und im internen Netz bleiben sie nicht als
  Datei liegen.
- **Kein Produktname, keine festen Adressen:** Die Tafel trägt die Adressen ihres
  Vereinsportals selbst ein (nur `https://`). Im Code stehen nur die Namen der Felder und
  Knöpfe, die der Ablauf bedient.
- **Zerbrechlich und deshalb zweitrangig:** Der Ablauf hängt an den Seiten des Vereinsportals.
  Er ist gegen eine nachgebaute Seite getestet (`tests/e2e/test_abruf_dienst.py`), nicht gegen
  das echte Portal. Scheitert er, steht die Meldung auf der Seite, und das Hochladen von Hand
  bleibt.
- **Derselbe Ablauf wie bisher:** Anmeldung, 2FA, Spenderliste über den Export-Knopf, vorhandenen
  Finanzexport wiederverwenden oder neu erzeugen, höchstens drei Monate.
