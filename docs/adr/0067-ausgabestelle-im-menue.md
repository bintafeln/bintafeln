# 0067: Ausgabestelle oben im Menü, Fortschritt in der Kopfzeile

- Status: Angenommen
- Datum: 2026-10-26

## Problem

Die Ausgabestelle wurde auf der Einlass-Seite gewählt und galt nur für die Sitzung. Wer an
mehreren Stellen arbeitet, musste sie nach jeder Anmeldung neu wählen; andere Seiten (Nachricht
an die Verwaltung, Abrechnung) kannten sie nicht oder fragten selbst nach. Außerdem fehlte am
Einlass der Überblick, wie viele Haushalte heute schon da waren.

## Entscheidung

- `apps/ausgabe/stelle.py` bestimmt die aktuelle Ausgabestelle: beim Konto einer Ausgabestelle
  (ADR 0059) dessen Stelle, sonst `Benutzer.gewaehlte_stelle`, sonst die einzige wählbare.
  Wählbar sind die zugeordneten Stellen, ohne Zuordnung alle.
- Wer das Recht „Einlass nutzen“ hat und mehrere Stellen wählen kann, sieht oben im linken
  Menü ein Auswahlfeld. Die Wahl wird am Benutzer gespeichert und gilt bis zur nächsten Wahl,
  auch nach dem Abmelden. Das Auswahlfeld im Einlass entfällt.
- Einlass, Nachrichten an die Verwaltung und Abrechnung nehmen diese Stelle. Filter in Listen
  und Statistik bleiben eigene Auswahlen, weil man dort bewusst mehrere oder alle Stellen sieht.
- Oben rechts steht `abgeholt/erwartet` für heute: erwartet sind die aktiven Haushalte, deren
  Kundengruppe an dieser Stelle heute ihren Ausgabetag hat; abgeholt sind alle Haushalte mit
  einer heute dort eingetragenen Abholung, auch mit Ausnahme. Nach jeder Abholung tauscht der
  Einlass die Zahl per `hx-swap-oob` aus. Ohne Ausgabetag bleibt die Stelle leer.
- Ergänzt 2026-10: Gruppen, aus denen heute dort jemand abgeholt hat, zählen hinten mit, auch wenn
  sie laut Plan nicht dran sind (z. B. reguläre Kunden an einem Tag mit Sonderausgabe, oder der
  Aufruf hatte die Gruppen schon vor dem Eintragen der Sonderausgabe übernommen); Abholungen ohne
  Gruppe ebenso. Sonst stand vorne mehr als hinten. Die Erklärung zeigt je Gruppe abgeholt/erwartet
  und Ausnahmen.

## Begründung

Eine Wahl an einer Stelle statt auf jeder Seite ist einfacher und vermeidet Abholungen, die der
falschen Ausgabestelle zugeordnet werden. Am Benutzer gespeichert, überlebt sie die automatische
Abmeldung. Ausnahmen zählen nur vorne, damit die zweite Zahl der planbare Umfang bleibt.
