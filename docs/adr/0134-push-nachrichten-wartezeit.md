# ADR 0134: Push-Nachrichten für „Wartezeit aufs Handy“

## Problem

Kunden sehen unter `/warten/`, wie viele noch vor ihnen sind (ADR 0090). Dafür muss die Seite
offen bleiben. Wer das Handy wegsteckt oder die Seite schließt, verpasst den Aufruf. Gewünscht ist
eine Nachricht, die von selbst auf dem Handy erscheint.

## Entscheidung

- **Web Push** (RFC 8030) statt App oder SMS: Auf `/warten/` schaltet der Kunde „🔔 Benachrichtigung
  aufs Handy“ ein; der Browser fragt nach der Erlaubnis und meldet ein Abo beim Push-Dienst seines
  Herstellers an. Die Adresse dieses Abos speichert bintafeln am `HandyZugang`.
- **Zwei Nachrichten je Tag**, jede höchstens einmal (`HandyZugang.push_gesendet`):
  „Gleich sind Sie dran“, sobald nur noch `HandyEinstellungen.push_vorher` Nummern aufgerufen werden,
  bevor die eigene auf dem Monitor steht (Vorgabe 3, 0 = aus), und „Sie sind dran!“ beim Aufruf. In
  der Sprache, in der die Seite beim Einschalten angezeigt wurde.
- **Auslöser:** nach jedem `ablauf.weiter()` und `ablauf.starten()`, nach dem Speichern und **im
  Hintergrund**, damit der Aufruf am Schalter nicht wartet.
- **Ohne neue Abhängigkeit:** Verschlüsselung (RFC 8291, aes128gcm) und Unterschrift der Tafel
  (VAPID, RFC 8292) mit `cryptography`, Versand mit `urllib`. Der Schlüssel der Tafel entsteht beim
  ersten Bedarf und liegt verschlüsselt in `HandyEinstellungen.push_schluessel` (ADR 0016).
- **Nur an Push-Dienste der Browser** (Google/Android, Mozilla, Apple, Microsoft): Andere Adressen
  werden abgelehnt, damit niemand den Server dazu bringt, beliebige Adressen aufzurufen. Meldet der
  Dienst „gibt es nicht mehr“ (404/410), wird das Abo vergessen.
- **Service Worker** unter `/warten/sw.js` (Bereich `/warten/`) und ein eigenes Manifest
  (`/warten/manifest.json`, Start `/warten/`), damit die Wartezeit auf dem iPhone als Symbol auf dem
  Home-Bildschirm liegen kann – nur so erlaubt iOS (ab 16.4) Push-Nachrichten.

## Begründung

Web Push braucht weder App noch Konto noch Telefonnummer und funktioniert auf Android sofort, auf dem
iPhone nach „Zum Home-Bildschirm“. Der Inhalt ist Ende-zu-Ende verschlüsselt; der Push-Dienst sieht
nur, dass eine Nachricht kommt. Eine eigene Umsetzung mit der ohnehin vorhandenen Bibliothek hält
die Abhängigkeiten klein; die Tests prüfen Verschlüsselung und Unterschrift gegen die RFCs.

## Folgen

- Der Server muss die Push-Dienste der Browser über HTTPS erreichen können.
- Die Auskunft zum Haushalt nennt je Handy, ob die Benachrichtigung an ist.
- Abmelden des Handys oder „Handys zurücksetzen“ am Einlass löscht auch das Abo.
