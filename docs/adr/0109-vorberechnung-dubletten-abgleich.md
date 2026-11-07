# 0109: „Doppelte Anträge“ und „Abgleich mit Kundenstamm“ vorberechnen

- Status: Angenommen
- Datum: 2026-11-05

## Problem

Die beiden Seiten der Warteliste **„Doppelte Anträge“** und **„Abgleich mit dem Kundenstamm“**
rechnen teuer: Die Dubletten vergleichen jeden offenen Antrag mit jedem (bei vielen Anträgen eine
O(n²)-Suche), der Abgleich sucht je Antrag über den Trigramm-Index (ADR 0102) ähnliche Haushalte im
ganzen Kundenstamm. Bisher begann diese Rechnung **erst beim Öffnen** der Seite (per htmx
nachgeladen, ADR-Vorarbeit „Ergebnis im Hintergrund laden“), sodass man jedes Mal 10–20 Sekunden auf
das Ergebnis wartete – auch wenn sich seit dem letzten Aufruf nichts geändert hatte.

## Entscheidung

- Das **Ergebnis** beider Seiten wird im **gemeinsamen Datenbank-Cache** (ADR 0093) gehalten:
  `apps/warteliste/vorberechnung.py`. Der Cache liegt in der Datenbank und **überlebt einen
  Neustart** (Update), die Seiten sind also auch danach sofort da.
- Gespeichert werden **render-fertige einfache Daten** (Listen aus Dicts mit Kundennummern, Daten,
  Punkten, Hinweisen – keine Modell-Objekte), damit die Templates unverändert bleiben und der Cache
  stabil und klein ist.
- **Warm halten statt dauernd rechnen:** Zu jedem Stand gehört eine **Signatur** (Zahl offener
  Anträge, letzte Änderung, Entscheidungen; beim Abgleich zusätzlich Kundenstamm-Größe und dessen
  letzte Änderung). Passt der Cache zur Signatur, kommt das Ergebnis sofort. Ist noch keins da (erstes
  Mal oder nach einer Entscheidung, die den Cache verwirft), wird **einmal** gerechnet. Hat sich etwas
  geändert (neue Anträge, Kundenstamm), zeigt die Seite sofort das **zuletzt** berechnete Ergebnis und
  frischt es **im Hintergrund** auf (Daemon-Thread, schließt seine DB-Verbindung selbst – kein Celery,
  wie bei der Ausweisprüfung ADR 0107); der Ergebnis-Block lädt sich per htmx kurz darauf noch einmal
  nach. **Neue Anträge kommen so von selbst dazu**, ohne dass jemand darauf wartet.
- Entscheidungen, die das Ergebnis sofort ändern (Treffer bestätigen/verwerfen, „keine Dublette“,
  Streichen), **verwerfen** den Cache gezielt (`veraltet()`), damit die nächste Anfrage frisch
  rechnet. Die htmx-Aktionen auf einzelne Treffer/Paare tauschen weiterhin nur ihren Block aus und
  rechnen nicht die ganze Liste neu.

## Begründung

- Die Seiten sind im Normalfall **sofort** da (der häufige Fall: seit dem letzten Mal hat sich nichts
  geändert). Die teure Rechnung läuft nur noch, wenn sich wirklich etwas geändert hat – und dann im
  Hintergrund, nicht im Weg des Nutzers.
- Der Datenbank-Cache ist schon da (ADR 0093) und über mehrere gunicorn-Prozesse und Neustarts
  hinweg gültig; dasselbe bewährte Hintergrund-Muster nutzt die Ausweisprüfung (ADR 0107).
- Einfache Daten statt Modell-Objekte im Cache vermeiden veraltete Objekte und halten die Templates
  unverändert.

## Folgen

- Beim **allerersten** Aufruf (leerer Cache) bzw. direkt nach einer Entscheidung wird einmal synchron
  gerechnet; danach ist die Seite warm. Der Cache überlebt Neustarts, also bleibt es dabei auch nach
  einem Update.
- Ein kurzer Moment „Ergebnis leicht veraltet“ ist möglich, während die Hintergrund-Auffrischung
  läuft; die Seite kennzeichnet das („Wird im Hintergrund aktualisiert …“) und lädt sich selbst nach.
- Der Abgleich hängt am Kundenstamm: Nach einem Kundenstamm-Import wird er beim nächsten Aufruf neu
  gerechnet (die Signatur ändert sich).

## Nachtrag: nie synchron blockieren, beim Betreten vorwärmen

Das allererste Öffnen (kalter Cache) rechnete bisher synchron und ließ die Seite 10–20 s hängen.
Jetzt blockiert `_holen()` nie: Ist noch kein Ergebnis da, wird die Rechnung in den Hintergrund
gelegt und `daten=None` geliefert; die Ergebnis-Seite zeigt „wird im Hintergrund vorbereitet …“ und
lädt sich selbst nach, sobald es fertig ist (`None` = noch nichts, `[]` = gerechnet, keine Treffer).
Zusätzlich wärmt `vorwaermen()` beide Auswertungen schon beim Betreten des Warteliste-Bereichs
(`warteliste:liste`) im Hintergrund vor, sodass „Doppelte Anträge“ und „Abgleich mit dem
Kundenstamm“ beim Öffnen meist ohne Warten da sind.
