# 0057: Links auf der Startseite

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Die bisherige „App-Übersicht“ war eine eigene kleine Anwendung ohne Anmeldung. Ihre Kacheln standen
fest im Code, Änderungen brauchten einen Entwickler, und interne Adressen (Serververwaltung) waren
für jeden im Netz sichtbar.

## Entscheidung

- Zuschaltbares Modul `links` (ADR 0049) mit den Modellen `LinkGruppe` und `Link` (Symbol, Titel,
  Untertitel, Beschreibung, Adresse, Warnhinweis, neuer Tab, Reihenfolge, aktiv). Statt des
  Symbols geht ein eigenes Bild (`Link.bild`, öffentlich unter `media/oeffentlich/links/`):
  PNG/JPG/WebP werden auf 128 Pixel verkleinert, SVG schreibt `apps/core/svg.py` nach einer
  festen Liste von Elementen und Attributen neu (keine Skripte, Ereignisse oder fremden
  Verweise); zusätzlich sendet Caddy für öffentliche Uploads eine Content-Security-Policy mit
  `sandbox`.
- Sichtbarkeit über ein Recht aus dem Rechtekatalog (`Link.recht`, leer = alle Angemeldeten), nie
  über Rollennamen (ADR 0033). Pflege mit dem neuen Recht `einstellungen.links` (Vorgabe: Admin).
- Neuer Modul-Hook `startseite(request)`: HTML unter der Begrüßung. Die Suche findet Links über
  `Modul.suchen`.
- Erlaubt sind nur http(s)-Adressen und Pfade in bintafeln, damit keine `javascript:`-Links
  entstehen.

## Begründung

Die Tafel pflegt ihre Links selbst, sieht sie nach dem Anmelden auf der Startseite, und Adressen
interner Systeme bleiben den Personen vorbehalten, die sie brauchen.
