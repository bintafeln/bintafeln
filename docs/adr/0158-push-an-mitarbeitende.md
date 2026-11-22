# ADR 0158: Push-Nachrichten an Mitarbeitende, Technik im Kern

Ergänzt ADR 0134 (Push-Nachricht für „Wartezeit aufs Handy“).

## Problem

Manche Nachrichten an Mitarbeitende sind eilig und treffen sie unterwegs – etwa ein zusätzlicher
Stopp, den das Büro einer laufenden Tour gibt. Eine Mail liest unterwegs niemand rechtzeitig. Die
Technik für Push-Nachrichten gab es bereits, aber fest im Modul „Aufruf“ und nur für Kunden; andere
Module konnten sie nicht nutzen, ohne modulspezifischen Code zu verknüpfen.

## Entscheidung

- **Technik im Kern:** `apps/core/push.py` enthält Schlüssel der Tafel (VAPID), Verschlüsselung
  und Versand (`zustellen()`), dazu `nach_speichern()` für den Versand im Hintergrund.
  `apps/aufruf/push.py` behält nur, wann welches Handy eines Kunden welche Nachricht bekommt.
- **Ein Schlüssel:** `PushEinstellungen.schluessel` (verschlüsselt über `apps.core.geheimnis`).
  Der bisherige Schlüssel aus dem Modul „Aufruf“ zieht per Migration um, damit eingeschaltete
  Benachrichtigungen der Kunden weiter gelten.
- **Mitarbeitende schalten je Gerät ein**, nur auf „Mein Konto“ (Kachel „Nachrichten auf dieses
  Gerät“, `static/js/push.js`): `PushAbo` je Konto und Gerät, höchstens fünf Geräte je Konto. Ein
  Gerät gehört immer nur zu einem Konto – meldet sich dort jemand anderes an und schaltet ein,
  bekommt das vorige Konto dort nichts mehr. Konten einer Ausgabestelle bekommen die Kachel nicht.
- **Module rufen nur `push.an_benutzer(konten, titel, text, link, kennung)`** auf. Der Link darf
  nur auf die eigene Installation zeigen. Gesperrte Konten bekommen nichts; Adressen, die der
  Push-Dienst nicht mehr kennt, werden vergessen.
- **Eigener Service Worker** `/push-sw.js` (öffentlich, ohne Vertrauliches, speichert nichts
  zwischen): zeigt die Nachricht und öffnet beim Antippen die genannte Seite.
- **Probe-Nachricht** auf „Mein Konto“, damit jede und jeder prüfen kann, ob es klappt.
- Die Geräte stehen in der Auskunft nach Art. 15 (ohne die Adresse beim Push-Dienst).

## Begründung

- Kein modulspezifischer Code im Kern, keine zweite Push-Technik: ein Schlüssel, ein Versandweg.
- Persönliche Angaben werden nur auf „Mein Konto“ eingetragen und gelöscht (wie PIN, Zugangsdaten,
  Unterschrift).
- Web Push braucht keine App und keinen weiteren Dienst außer dem Push-Dienst des Browsers; der
  sieht nur verschlüsselte Daten. Auf dem iPhone geht es nur in der App vom Home-Bildschirm.
- Push ergänzt die Mail-Benachrichtigungen (ADR 0086), ersetzt sie nicht: nur für Eiliges.
