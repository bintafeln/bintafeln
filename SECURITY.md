# Sicherheit

bintafeln verwaltet Daten von Menschen, die eine Tafel besuchen – Namen, Anschriften, Bescheide.
Sicherheitslücken nehmen wir deshalb besonders ernst.

## Eine Lücke melden

Bitte **nicht** als öffentliches Issue, Diskussion oder Pull Request, solange die Lücke nicht
behoben ist. Stattdessen vertraulich über GitHub:

1. Im Repository oben auf **„Security“** gehen.
2. **„Report a vulnerability“** wählen und die Lücke beschreiben: was betroffen ist, wie man sie
   nachstellt (mit erfundenen Daten) und welche Version betroffen ist (steht unter
   „Einstellungen → Systemsteuerung → Update“ bzw. in der Datei `VERSION`).

Echte Personendaten, Passwörter oder Schlüssel bitte nie mitschicken.

Wir bestätigen den Eingang so bald wie möglich und halten Sie über den Stand auf dem Laufenden.
bintafeln wird ehrenamtlich gepflegt; feste Fristen können wir nicht zusagen, Sicherheitslücken
haben aber Vorrang vor allem anderen.

## Welche Versionen Updates bekommen

Behoben wird immer in der **neuesten Version** (`JJJJ.M.N`). Ältere Versionen bekommen keine
eigenen Korrekturen; jede Tafel aktualisiert mit einem Befehl (`./betrieb update`) oder über
„Einstellungen → Systemsteuerung → Update“.

## Wie Tafeln von einer Lücke erfahren

- Updates, die eine Lücke schließen, tragen die Stufe **„sicherheit“**. Die Update-Seite jeder
  Installation hebt sie hervor (ADR 0084).
- Wird eine Lücke erst später bekannt, steht sie in
  [`docs/sicherheitshinweise.txt`](docs/sicherheitshinweise.txt). Jede Installation liest diese
  Datei, warnt auf der Startseite und schickt einmal eine Mail, solange eine betroffene Version
  läuft.

## Was Tafeln selbst tun sollten

- Regelmäßig aktualisieren, Sicherheitsupdates sofort.
- Im Produktivbetrieb eine Domain setzen (`BINTAFELN_DOMAIN`), damit TLS erzwungen wird.
- Zwei-Faktor-Anmeldung für alle Rollen mit Zugriff auf Kundendaten verlangen.
- Verschlüsselte Sicherungen einrichten und den Schlüssel getrennt aufbewahren
  (`./betrieb schluessel`).
