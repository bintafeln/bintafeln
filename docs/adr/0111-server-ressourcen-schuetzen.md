# ADR 0111: Kleinen Server vor Überlastung schützen

## Problem

bintafeln läuft je Tafel auf einem eigenen, oft kleinen VPS (z. B. 2 GB RAM bei Strato). Mehrere
Dienste teilen sich diesen Speicher: der Webserver (`app` mit mehreren gunicorn-Arbeitsprozessen,
die jeweils Django samt numpy/scikit-image laden), PostgreSQL, Caddy, der Sicherungs- und der
Update-Dienst. Dazu kommt rechen- und speicherintensive Hintergrundarbeit, allen voran die
**Ausweisprüfung** (ADR 0107): Sie liest Ausweis-Fotos mit `passporteye`/`tesseract`/`scipy` und
braucht dabei kurzzeitig viel Speicher – bei vielen Nachweisen am Stück über längere Zeit.

Ohne Grenzen kann eine solche Spitze den gesamten Arbeitsspeicher aufbrauchen. Gibt es keinen
Swap, beginnt Linux nicht zu swappen, sondern die Maschine wird unbrauchbar langsam
(„thrashing“) und reagiert auf gar nichts mehr – auch nicht auf das Neuladen der Seite. In der
Praxis half nur ein harter Neustart des Servers beim Hoster. Das darf einer Tafel im laufenden
Ausgabebetrieb nicht passieren.

## Entscheidung

Mehrere einfache, robuste Maßnahmen, damit ein Ausreißer nie den ganzen Server lahmlegt – kein
zusätzlicher Dienst, keine neue Abhängigkeit:

- **Speicherobergrenze je Container** (`mem_limit` in `docker-compose.yml`): Jeder Dienst bekommt
  eine Obergrenze. Läuft ein Prozess aus dem Ruder, beendet das Betriebssystem ihn **innerhalb
  seines Containers** (statt den ganzen Server zu erdrücken); `restart: unless-stopped` startet den
  Container automatisch neu. Der `app`-Dienst (Webserver samt Hintergrundarbeit) bekommt den
  größten Anteil und ist über `BINTAFELN_APP_SPEICHER` in der `.env` an die Servergröße anpassbar
  (Vorgabe `1280m`, passend für 2 GB; db 512m, backup 256m, proxy 256m, updater 512m).
- **gunicorn anpassbar** (`bintafeln/gunicorn.conf.py` statt fester Kommandozeile): Worker-Zahl
  (`BINTAFELN_WORKER`, Vorgabe 3), Timeout (`BINTAFELN_TIMEOUT`, Vorgabe 120 s) und ein
  **Worker-Recycling** (`BINTAFELN_MAX_REQUESTS`, Vorgabe 1000) kommen aus der `.env`. Das Recycling
  startet einen Arbeitsprozess nach einer Weile neu und gibt langsam angewachsenen Speicher
  zuverlässig wieder frei.
- **Ausweisprüfung ausbremsen** (`ausweis_scan.ressourcen_begrenzen()`, aufgerufen im Prüf-Prozess
  des Management-Befehls `ausweise_pruefen`): Der Prüf-Prozess läuft mit niedriger CPU-Priorität
  (`nice`, `BINTAFELN_AUSWEIS_NICE`, Vorgabe 10), damit der Einlass flüssig bleibt, und – wenn
  gesetzt – mit einem harten Speicherdeckel (`RLIMIT_AS`, `BINTAFELN_AUSWEIS_SPEICHER_MB`, Vorgabe
  0 = aus). Läuft der Prozess in den Deckel, wird er beendet und der betroffene Antrag wie bei einem
  Absturz übersprungen (ADR 0107). Weil der Prüf-Prozess im selben Container wie der Webserver läuft,
  schützt ihn die Container-Grenze ohnehin; der Deckel ist die feinere, freiwillige Zusatzstufe.
- **Swap-Datei** (Betrieb, nicht Code): In der Installationsanleitung (README) steht, wie man auf
  kleinen Servern einmalig eine Swap-Datei einrichtet (mit niedrigem `vm.swappiness`). Swap fängt
  kurze Spitzen ab und verwandelt den harten Freeze in „kurz langsam“.

## Begründung

Die Container-Grenze ist der entscheidende Schutz: Sie begrenzt den bekannten „Ausreißer“ (den
`app`-Dienst) hart, sodass selbst im schlimmsten Fall nur dieser neu startet und der Server – und
damit der Einlass an anderen Geräten – erreichbar bleibt; ein Neustart beim Hoster von Hand ist
nicht mehr nötig. gunicorn- und Ausweis-Einstellungen glätten den Normalbetrieb und verhindern das
langsame Volllaufen. Alle Werte haben sinnvolle Vorgaben für einen 2-GB-Server und sind ohne
Neubau des Abbilds über die `.env` anpassbar. Bewusst **kein** zusätzlicher Überwachungs- oder
Neustart-Dienst: Das Zusammenspiel aus Container-Grenze und `restart: unless-stopped` genügt und
hält die Installation einfach.
