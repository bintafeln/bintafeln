# 0142 – Post der Verwaltung an die Ausgabestellen (die Eule)

## Problem

Die Verwaltung erreicht die Ausgabestellen bisher nur mit Notizen zu einzelnen Kunden oder als
Antwort auf deren Nachrichten (ADR 0070, 0140). Für allgemeine Mitteilungen („morgen keine
Kühlware“) fehlte ein Weg, der am Einlass – wo die Ausgabestellen den ganzen Tag arbeiten –
auch wirklich gesehen wird.

## Entscheidung

- Die Verwaltung (Recht `kunden.nachrichten`) schreibt unter „Ausgabestelle → Post an Ausgabestellen“
  an eine, mehrere oder alle aktiven Ausgabestellen: Betreff, Text, auf Wunsch „Wichtig“.
  `Rundschreiben` mit einem `PostEmpfang` je Ausgabestelle (Lesestand), Logik in
  `apps/kunden/eulenpost.py`.
- Bei der Ausgabestelle steht in der Kopfzeile jeder Seite ein Landeplatz (`_eulenpost.html`),
  der jede Minute nachfragt (HTMX). Neue Post: Eine selbst gezeichnete Eule (SVG, keine fremden
  Figuren oder Bilder) fliegt mit einem Brief von der Bildmitte dorthin und landet
  (`static/js/eulenpost.js`, Web Animations), die Zahl zeigt die ungelesene Post. Bei
  „Bewegung reduzieren“ entfällt der Flug.
- Ton: ein kurzes „Huhu“ über Web Audio (keine Tondatei), je Gerät auf der Seite „Post der
  Verwaltung“ abschaltbar (localStorage).
- Wichtige Post öffnet nach der Landung einen Hinweis über der Seite mit „✓ Gelesen“ und
  „Später“; er kommt bei jedem Seitenaufruf wieder, bis jemand gelesen bestätigt.
- „Gelesen“ gilt je Ausgabestelle; die Verwaltung sieht je Ausgabestelle, wann und von wem.
  Was schon angekündigt wurde, merkt sich der Browser für die Sitzung (sessionStorage), damit
  die Eule nicht bei jedem Seitenwechsel neu einfliegt.
- Gelesene Post wird 90 Tage nach dem Schreiben gelöscht; ungelesene bleibt.

## Begründung

Die Kopfzeile ist auf jeder Seite sichtbar, auch am Einlass, und braucht kein Neuladen. Eine
Bewegung über den Bildschirm fällt im Trubel der Ausgabe auf, ohne die Arbeit zu blockieren;
nur wirklich Wichtiges unterbricht mit einem Hinweis. Lesestand je Ausgabestelle (nicht je
Person) passt zu den gemeinsam genutzten Tablets.

## Nachtrag (2026-11-17)

- Der Menüpunkt steht unter „Ausgabestelle“ (Abschnitt Verwaltung), nicht unter „Kunden“: Die Post
  hat nichts mit einzelnen Kunden zu tun.
- Unter „Gesendet“ löscht „Löschen“ eine Post ganz – bei allen Ausgabestellen, gelesen oder nicht –
  über den Papierkorb (`eulenpost.loeschen()`, wiederherstellbar mit `kunden.nachrichten`).
