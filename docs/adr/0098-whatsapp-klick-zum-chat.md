# 0098: WhatsApp per „Klick zum Chat“

- Status: Angenommen
- Datum: 2026-10-31

## Problem

Für kurzfristige Absprachen im Dienst- und Fahrdienstplan („Kannst du am Freitag einspringen?“,
„Du bist morgen eingeteilt“) ist bei vielen Ehrenamtlichen WhatsApp der übliche Weg – nicht
E‑Mail oder Telegram. Es geht dabei nicht um einen Massenversand, sondern darum, **einzelne**
Helfer schnell zu erreichen.

Ein automatischer WhatsApp-Versand ginge nur über die kostenpflichtige WhatsApp-Business-Plattform
mit vorab freigegebenen Vorlagen und einem Dienstleister. Das ist für eine Tafel-Installation zu
schwer, zu teuer und datenschutzrechtlich heikel (Nummern und Texte lägen bei einem Dritten).

## Entscheidung

bintafeln verschickt **nichts selbst** über WhatsApp. Es baut nur einen **„Klick zum Chat“-Link**
(`https://wa.me/<Nummer>?text=…`), der auf dem Gerät der planenden Person WhatsApp mit
vorgefülltem Text zur jeweiligen Person öffnet. Abgeschickt wird erst mit einem Tippen in
WhatsApp.

- Hilfsfunktionen in `apps/core/whatsapp.py` (`nummer_bereinigen`, `link`, `fuer_person`).
- Die Handynummer kommt aus `Adresse.mobil`. Nummern mit führender 0 werden auf die
  **Ländervorwahl der Tafel** (`TafelEinstellungen.laendervorwahl`, Vorgabe „49“) gebracht;
  bereits internationale Nummern (`+…`, `00…`) bleiben.
- Ein WhatsApp-Knopf erscheint dort, wo man eine einzelne Person erreicht: auf der Platz-Seite im
  Dienst- und Fahrdienstplan (mit Text zum konkreten Tag) und bei der Handynummer im Adressbuch.

## Begründung

Kein Dienstvertrag, keine Schnittstelle, keine Kosten und keine Weitergabe echter Nummern oder
Texte an Dritte: Der Link entsteht erst im Browser, das Senden bleibt eine bewusste Handlung der
planenden Person. Das deckt den tatsächlichen Bedarf (einzelne Nachrichten) ab und bleibt im
Rahmen der Datensparsamkeit. Ein echter Massenversand ist damit bewusst nicht möglich.
