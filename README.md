# bintafeln

Freie Verwaltungssoftware für Tafeln – lizenziert unter der
[GNU Affero General Public License v3.0](LICENSE).

> **Stand:** Grundgerüst, Kundenstamm (Import, Bearbeiten durch den Admin), Einlass mit Ampel,
> Kundenkonto und Kasse, Mitarbeitende, Personal mit Arbeitszeiterfassung, PDFs (Kundenausweis,
> Kassenabschluss, Auskunft nach Art. 15 DSGVO), Online-Anträge in 29 Sprachen.

**Schnell zum Ziel**

- [Installation](#installation-auf-debian-13-trixie-mit-docker) – eine Tafel auf einem eigenen
  Server einrichten
- [Demoversion einrichten](docs/demo-einrichten.md) – mit erfundenen Daten ausprobieren, neben
  einer bestehenden Installation oder öffentlich unter eigener Domain
- [Mehrere Installationen auf einem Server](#mehrere-installationen-auf-einem-server)
- [Aktualisieren und Versionen](#aktualisieren)
- [Fachkonzept](docs/fachkonzept.md) · [Importformat](docs/importformat.md) ·
  [Entscheidungen (ADR)](docs/adr/README.md)

## Funktionen des Grundgerüsts

- **Einrichtung im Browser:** Solange es keinen Admin gibt, öffnet sich automatisch
  die Einrichtungsseite. Dort werden der Name der Tafel und das erste Admin-Konto angelegt.
  Danach ist die Seite gesperrt.
- **Rollen und Rechte:** Rollen sind frei anlegbar und löschbar; jede Rolle bekommt einzeln
  ausgewählte Rechte (rund 45, z. B. „Kundenliste“, „Anschrift sehen“, „Abholungen buchen“,
  „Dokumente hochladen“). Mitgeliefert: Admin, Büro, Ausgabe, Kiosk, Fahrer, Beifahrer,
  Personal (siehe „Rollen und Rechte“ unten). Konten bekommen ihre Rollen unter
  „Mitarbeitende“.
- **Tafel-Einstellungen:** Name, Logo, Farbe (voreingestellt Tafel-Orange) und Anschrift der
  Tafel – in der Datenbank, nicht im Code.
- **Änderungsprotokoll:** Wer hat wann welchen Datensatz geändert (mit Feldern vorher/nachher).
  Passwörter werden nie protokolliert.
- **Zwei-Faktor-Anmeldung:** Jede Person richtet sie unter „Mein Konto“ selbst ein
  (QR-Code für die Authenticator-App, dazu 10 Notfallcodes). Für welche Rollen sie Pflicht ist,
  steht in der jeweiligen Rolle; voreingestellt sind Admin, Büro und Personal.
- **Sicherung:** täglich und verschlüsselt, mit Wiederherstellung und Update per Befehl
  (`./betrieb`). Die Startseite zeigt Admins den Stand der Sicherung.
- **Kundenstamm (im Aufbau):** Datenmodell für Haushalte, Personen, Abholberechtigte, Sperren,
  Anmerkungen und Kundengruppen. Unter „Einstellungen → Kundenstamm“ legt ein Admin fest, welche
  Angaben erfasst werden, und richtet eigene **Zusatzfelder** ein (z. B. „Schwerbehindert“).
  **Import** mit Prüfbericht unter „Kunden“; Liste und Suche folgen.
- **Menü links** mit aufklappbaren Bereichen (Ausgabe, Kunden, Anträge, Team, Einstellungen);
  jede Rolle sieht nur, was sie darf. Auf Handys (unter 768 Pixel Breite) öffnet „☰ Menü“ das Menü.
- Deutsche, mobilfreundliche Oberfläche (Django-Templates + HTMX, ohne externe CDNs).

## Aufbau

| Dienst  | Aufgabe |
|---------|---------|
| `app`   | Django-Anwendung (gunicorn). Führt beim Start die Migrationen automatisch aus. |
| `db`    | PostgreSQL 17 |
| `proxy` | Caddy: liefert statische Dateien aus und sorgt im Produktionsmodus für TLS. |
| `backup` | Tägliche, verschlüsselte Sicherung von Datenbank und hochgeladenen Dateien. |

Die gesamte Konfiguration steht in der Datei `.env` (Vorlage: [`.env.example`](.env.example)).

## Installation auf Debian 13 (Trixie) mit Docker

Die folgenden Befehle als Benutzer mit `sudo`-Rechten ausführen.

### 1. Docker installieren

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Optional, damit `docker` ohne `sudo` funktioniert (danach ab- und wieder anmelden):

```bash
sudo usermod -aG docker "$USER"
```

### 2. bintafeln herunterladen

```bash
sudo git clone https://github.com/bintafeln/bintafeln.git /opt/bintafeln
sudo chown -R "$USER": /opt/bintafeln
cd /opt/bintafeln
```

### 3. Konfiguration anlegen

```bash
cp .env.example .env
chmod 600 .env
# Zufällige Schlüssel eintragen:
sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$(openssl rand -hex 32)|" .env
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" .env
```

Weitere Werte (Domain, Ports, Zeitzone) bei Bedarf in `.env` anpassen – siehe Kommentare
in der Datei.

### 4. Starten

```bash
docker compose up -d
```

Der erste Start baut das Image und dauert einige Minuten. Den Zustand zeigt
`docker compose ps`; alle Dienste sollten nach kurzer Zeit laufen (`app` als *healthy*).

### 5. Einrichten

Im Browser `http://<IP-des-Servers>` öffnen. Die Einrichtungsseite erscheint automatisch:
Namen der Tafel und das erste Admin-Konto eintragen. Direkt danach richtet der Admin die
[Zwei-Faktor-Anmeldung](#zwei-faktor-anmeldung) ein; dafür eine Authenticator-App auf dem Handy
bereithalten. Anschrift und Logo lassen sich danach unter **Einstellungen** ergänzen.

### 6. Sicherung einrichten

```bash
./betrieb schluessel
```

Den angezeigten privaten Schlüssel sicher und getrennt vom Server aufbewahren, siehe
[Sicherung einrichten](#sicherung-einrichten).

## Zwei-Faktor-Anmeldung

Bei der Anmeldung wird zusätzlich zum Passwort ein 6-stelliger Code aus einer
Authenticator-App verlangt (z. B. Aegis, FreeOTP, Google Authenticator).

- **Einrichten:** „Mein Konto“ → „Jetzt einrichten“, QR-Code scannen, Code eingeben. Danach
  erscheinen einmalig **10 Notfallcodes**. Jeder funktioniert einmal anstelle der App.
- **Pflicht je Rolle:** in der Rolle („Einstellungen → Rollen und Rechte“) per Häkchen.
  Voreingestellt: Admin, Büro und Personal.
  Wer eine Pflicht-Rolle hat, wird nach der Anmeldung direkt zur Einrichtung geleitet und kann
  bis dahin nichts anderes öffnen. Auch der erste Admin richtet sie direkt nach der
  Einrichtungsseite ein.
- **Handy verloren:**
  1. mit einem Notfallcode anmelden und unter „Mein Konto“ neu einrichten, oder
  2. ein Admin setzt sie unter „Mitarbeitende“ → Person → „Zwei-Faktor zurücksetzen“ zurück, oder
  3. als letzter Ausweg auf dem Server, falls sich kein Admin mehr anmelden kann:

     ```bash
     docker compose exec app python manage.py zwei_faktor_zuruecksetzen BENUTZERNAME
     ```

Einrichten und Entfernen stehen im Änderungsprotokoll, Schlüssel und Codes nie.

## Rollen und Rechte

„Einstellungen → Rollen und Rechte“ (Admin; andere nur mit dem Recht „Rollen und Rechte“):

- **Liste** aller Rollen mit Zahl der Rechte, Zahl der Konten und Pflichten.
- **Neue Rolle** oder eine Rolle öffnen: Name, Beschreibung, Pflichten (Zwei-Faktor-Anmeldung,
  Belehrung nach Infektionsschutzgesetz, Führerschein; die beiden letzten erzeugen
  Wiedervorlagen bei den Mitarbeitenden) und die **Rechte**, gruppiert nach Bereich (Einlass und
  Kasse, Kunden, Anträge, Mitarbeitende und Personal, Einstellungen) mit „alle“/„keine“ je
  Bereich.
- Seiten ohne Recht fehlen im Menü und lassen sich auch über die Adresse nicht öffnen; Teile
  einer Seite (z. B. Anschrift, Kundenkonto, Dokumente) erscheinen nur mit dem passenden Recht.
  Hat ein Konto mehrere Rollen, gelten alle ihre Rechte zusammen.
- **Admin** hat immer alle Rechte und lässt sich weder beschneiden noch löschen, damit sich
  niemand aussperrt.
- **Nur eigene Rechte weitergeben:** Wer nicht Admin ist, kann nur Rechte setzen oder entfernen,
  die er selbst hat (andere sind grau und bleiben), und nur Rollen löschen oder vergeben, deren
  Rechte er alle selbst hat.
- **Löschen** einer Rolle nimmt sie allen Konten weg.
- Die mitgelieferten Rollen haben nach dem Update genau die Rechte, die sie vorher hatten. Die
  früheren Schalter „Zwei-Faktor Pflicht für …“, „Büro darf Mitarbeitende verwalten“ und
  „Ausgabe sieht Zusatzfelder der besonderen Kategorie“ sind in die Rollen gewandert
  (ADR 0033).

## Mitarbeitende

„Mitarbeitende“ im Menü (mit dem Recht „Mitarbeitende anlegen, bearbeiten, sperren“; Admin
immer). Rollen vergeben kann man nur, wenn man selbst alle Rechte der Rolle hat; Admin-Konten
bearbeitet nur ein Admin. Rollen, die man nicht vergeben darf, bleiben beim Bearbeiten erhalten.

- **Anlegen:**
  - Benutzername, Name, E-Mail (optional), Beschäftigung (ehrenamtlich oder fest angestellt)
    und Rollen per Häkchen.
  - bintafeln zeigt danach **einmal** ein Startpasswort, das man persönlich weitergibt.
  - Bei der ersten Anmeldung muss die Person ein eigenes Passwort wählen, danach gegebenenfalls
    die Zwei-Faktor-Anmeldung einrichten.
- **Einladung per Mail** statt Startpasswort, wenn ein Mailserver eingerichtet ist (siehe
  „E-Mail“): Die Person bekommt einen Link, über den sie ihr Passwort selbst festlegt. Der Link
  gilt 3 Tage und nur einmal.
- **Bearbeiten:** Name, E-Mail, Beschäftigung, Rollen.
- **Passwort zurücksetzen** (neues Startpasswort), **Link zum neuen Passwort per Mail** und
  **Zwei-Faktor zurücksetzen** (z. B. Handy verloren).
- **Sperren statt löschen:** Die Person ist sofort abgemeldet und steht im **Archiv** mit „dabei
  seit“, „gesperrt am“ und „gesperrt von“. So bleibt auch Jahre später nachvollziehbar, wer was
  eingetragen hat. Ein gesperrtes Konto lässt sich wieder freischalten.
- **Schutzregeln:**
  - Niemand kann sich selbst sperren oder sich die Admin-Rolle nehmen.
  - Das Büro bearbeitet keine Admin-Konten.
- Jede Person kann unter „Mein Konto“ ihr **Passwort ändern**.
- **Stammdaten** (Person → „Stammdaten, Führerschein, Belehrungen, Schulungen“):
  - Anschrift, Telefon, Handy, Notfallkontakt, Eintritt und Austritt
  - Führerschein-Vermerk (Klassen, gültig bis, gesehen am / von)
  - Belehrung nach § 43 IfSG und Schulungen mit Ablaufdatum
- **Fällig:** Die Liste zeigt oben, wann ein Führerschein wieder angesehen werden muss, wann
  eine IfSG-Folgebelehrung fällig ist und welche Schulungen ablaufen. Die Startseite weist
  darauf hin.
- **Führerschein-Kopie** nur, wenn unter „Fristen einstellen“ erlaubt (Vorgabe: aus). Sie wird
  verschlüsselt gespeichert, und jeder Abruf wird protokolliert.
- Anrede, Führerscheinklassen (Mehrfachauswahl) und „gesehen von“ (registrierte Mitarbeitende)
  sind Auswahlfelder.
- **Dokumente** (z. B. Schulungsnachweise, Verträge):
  - je Person auf der Stammdaten- und der Personal-Seite
  - verschlüsselt gespeichert, jeder Abruf protokolliert
  - Kategorien unter „Fristen einstellen“ pflegbar; Kategorien „nur Personal“ (Vorgabe:
    Arbeitsvertrag, Lohnunterlagen) sehen nur Admin und die Rolle Personal
  - nach der Löschfrist gelöscht
- **Löschfrist:** 3 Jahre (einstellbar) nach Austritt bzw. Sperre werden die persönlichen
  Angaben geleert. Name, Rollen und Zeiträume bleiben im Archiv.

## Personal

„Personal“ im Menü (mit dem Recht „Personal“, vorgegeben für Admin und Rolle **Personal**):

- Liste der Festangestellten mit Tätigkeit, Wochenstunden, Vertragsende, Resturlaub und
  Stundenkonto.
- **Arbeitsvertrag:**
  - Beginn, Ende, Tätigkeit, Wochenstunden, Urlaubstage pro Jahr, Stundenlohn.
  - Das Vertragsdokument (PDF oder Foto) wird verschlüsselt gespeichert.
  - Bei einer Änderung den alten Vertrag beenden und einen neuen eintragen.
- **Urlaub und Krankheit:**
  - Zeitraum und Arbeitstage (ohne Angabe Mo–Fr ohne gesetzliche Feiertage; halbe Tage und
    regionale Feiertage selbst eintragen).
  - Bei Krankheit nur, ob eine AU-Bescheinigung vorliegt, nie eine Diagnose.
  - Der Anspruch wird anteilig berechnet.
  - Der Resturlaub wird automatisch übertragen und verfällt zum 31.03. Das Datum lässt sich
    unter „Mitarbeitende → Fristen einstellen“ und je Person und Jahr ändern.
- **Stundenkonto:**
  - Gestempelte Arbeitszeit (siehe unten) zählt automatisch. Stunden außerhalb der Stempeluhr
    (z. B. Dienstreise, Ausgleich) lassen sich von Hand nachtragen.
  - Soll (Wochenstunden ÷ 5 je Arbeitstag ohne Feiertage), Urlaub und Krankheit rechnet
    bintafeln je Monat.
  - Der Saldo läuft über die Jahre weiter.
- **Auskunft (PDF):** alle zu einer Person gespeicherten Daten nach Art. 15 DSGVO, auch unter
  „Mitarbeitende“. Jede Person ruft ihre eigene unter „Mein Konto → Meine Daten“ ab.

### Arbeitszeit

- Fest Angestellte stempeln unter **„Meine Arbeitszeit“** mit einem großen Knopf **Kommen** und
  **Gehen**, am eigenen Handy oder an einem gemeinsamen Gerät nach Anmeldung. Darunter stehen
  die Tage des Monats mit Pause und Arbeitszeit sowie der Stand des Stundenkontos.
- **Pausen:** Fehlt die gesetzliche Pause (mehr als 6 Stunden: 30 Minuten, mehr als 9 Stunden:
  45 Minuten), zieht bintafeln den Rest ab. Als Pause zählt die Zeit zwischen Gehen und erneutem
  Kommen.
- **Gehen vergessen?** Ein Kommen, das länger als 14 Stunden offen ist, zählt nicht. Die Person
  kann am nächsten Tag normal stempeln; die Personal-Seite listet es zum Nachtragen.
- **Korrigieren und nachtragen** nur durch Admin und Personal: bei der Person auf
  „Arbeitszeiten“, mit Grund. Die Korrektur trägt den Namen und steht im Änderungsprotokoll.
- Unter „Personal → Arbeitszeiterfassung einstellen“: auch Ehrenamtliche stempeln lassen,
  automatischen Pausenabzug ab- oder einschalten, Grenze für vergessenes Gehen.

**Feiertage:** Unter „Einstellungen“ das **Bundesland** der Tafel wählen. Dann zählen dessen
gesetzliche Feiertage weder als Arbeitstag (Urlaub, Krankheit, Stundenkonto) noch als Abholtag im
Vorschlag für Vorauszahlungen am Einlass.

## E-Mail

Unter „Einstellungen → E-Mail“ trägt ein Admin den Mailserver der Tafel ein: Server, Port,
Verschlüsselung, Benutzer, Passwort und Absender. Die Angaben gibt es beim Mail-Anbieter unter
dem Stichwort „SMTP“ – gemeint ist der Server zum **Senden** (z. B. `smtp.strato.de`, nicht
`imap.…`). Nach dem Speichern im Bereich **„Testen“**:

- **„Verbindung prüfen“** verbindet sich mit dem Server und meldet sich an, ohne eine Mail zu
  senden. Klappt es nicht, steht dort verständlich, woran es liegt (Adresse/Port,
  Verschlüsselung, Benutzername/Passwort).
- **„Testmail senden an“** schickt eine Testmail an eine frei wählbare Adresse (vorbelegt mit der
  eigenen, falls hinterlegt).

- Das Passwort wird **verschlüsselt** gespeichert und nie wieder angezeigt. Der Schlüssel
  stammt aus `DJANGO_SECRET_KEY` in `.env`. Wird dieser geändert, muss das Passwort neu
  eingegeben werden.
- Mit eingerichtetem Mailserver gibt es Einladungen per Mail und auf der Anmeldeseite
  **„Passwort vergessen?“**. Beides verschickt einen Link, nie ein Passwort.

## Kundenstamm importieren

Der Kundenstamm wird aus dem bisherigen Programm übernommen, im
[offenen Importformat](docs/importformat.md). Jeder Import ersetzt den Bestand vollständig.

1. Vorher unter „Einstellungen → Kundenstamm“ festlegen, welche Angaben erfasst werden, und
   benötigte **Zusatzfelder** anlegen (ihre Schlüssel bestimmen die Spalten `zusatz_…`).
2. „Kunden“ → „Neuen Stand importieren“ → CSV-Dateien auswählen → **Prüfen**.
3. Der **Prüfbericht** nennt Fehler (Import nicht möglich) und Warnungen (Import möglich), jeweils
   mit Datei und Zeile, aber ohne Inhalte.
4. Ohne Fehler: Vorschau mit „bisher / nach dem Import“ ansehen und **Import übernehmen**.
5. **Abgleich:** Die Vorschau zeigt, welche Haushalte neu sind, welche entfallen und was sich
   bei den übrigen ändert (z. B. „Anschrift: alt → neu“). Bei Haushalten, die in bintafeln
   geändert oder aufgenommen wurden, wählt man je Haushalt **bintafeln-Stand behalten** (der
   Import lässt ihn aus) oder **Import übernehmen**; Vorgabe ist „behalten“. „Für alle den Import
   übernehmen“ ersetzt alles, z. B. beim endgültigen Umstieg (ADR 0028).

Regeln:

- Übernehmen geht nur, wenn die letzte erfolgreiche Sicherung höchstens **24 Stunden** alt ist
  (sonst vorher `./betrieb sichern`).
- Die geprüften Daten liegen bis zur Bestätigung höchstens **eine Stunde** in der Datenbank und
  werden danach, beim Übernehmen oder beim Verwerfen gelöscht. Die hochgeladenen Dateien selbst
  werden nicht gespeichert.
- Jeder Import erscheint im Änderungsprotokoll und unter „Kunden“ (wer, wann, wie viele
  Datensätze), nicht jeder einzelne Datensatz.
- Importieren dürfen Admin und Büro.
- Abholungen und Ausnahmen werden nur innerhalb der **Aufbewahrungsfrist** übernommen
  („Einstellungen → Kundenstamm“, Vorgabe 3 Jahre). Ältere löscht bintafeln automatisch.

## Kunden ansehen und bearbeiten

Unter „Kunden“ stehen alle Haushalte des Kundenstamms.

- **Suche** nach Kundennummer oder Name; Status und Kundengruppe lassen sich filtern. Eine
  vollständige Kundennummer mit Enter (z. B. vom Scanner) öffnet den Haushalt direkt.
- Die **Detailseite** zeigt je nach Rechten unterschiedlich viel. Vorgaben der mitgelieferten
  Rollen (änderbar unter „Einstellungen → Rollen und Rechte“):

  | Rolle | sieht |
  |---|---|
  | Admin, Büro | alles: Anschrift, Kontakt, Personen, Abholberechtigte, alle Sperren, Ausnahmen, Abholungen, Kontostand, Anmerkungen, Notizen, Dokumente, Zusatzfelder |
  | Ausgabe | nur, was der Einlass braucht: Kundennummer, Haushaltsgröße, alle Personen des Haushalts und die Abholberechtigten mit Geburtsdatum, Ausgabestelle, Karte gültig bis, Kontostand (abschaltbar), aktive Sperren, die letzten 5 Abholungen, Notizen, freigegebene Zusatzfelder (Art. 9 nur mit dem Recht „besondere Kategorie“). Keine Anschrift, keine Kontaktdaten, keine Ausnahmen, keine internen Anmerkungen, keine Dokumente |
  | Kiosk | nichts |

- **Bearbeiten (nur Admin):** Auf der Haushaltsseite „Bearbeiten“ ändert alles zum Haushalt:
  Angaben und Zusatzfelder, Personen, Abholberechtigte, Sperren, Ausnahmen, Anmerkungen;
  Abholungen lassen sich löschen (eine zugehörige Buchung wird zurückgenommen), der ganze
  Haushalt ebenfalls. „Neuer Haushalt“ steht in der Kundenliste. Kundengruppen, Ausgabestellen
  und Einkommensarten pflegt der Admin unter „Einstellungen → Kundenstamm → Listen“.
  **Achtung:** Solange aus dem Altsystem importiert wird, ersetzt der nächste Import alle
  Änderungen; der Prüfbericht nennt die Zahl der geänderten Haushalte (ADR 0025).
- **Notizen:** Ausgabe, Büro und Admin schreiben Notizen zum Haushalt, auf der Haushaltsseite
  oder direkt am Einlass. **Notiz-Vorlagen** („Einstellungen → Kundenstamm → Listen →
  Notiz-Vorlagen“, Admin) erscheinen als Knöpfe: ein Klick speichert den Text als Notiz. Jede
  Notiz lässt sich einzeln löschen: Büro und Admin jede, die Ausgabe ihre eigenen vom selben
  Tag (Versehen). Notizen hängen an der Kundennummer und
  bleiben beim Import erhalten; gibt es die Kundennummer nicht mehr, werden sie gelöscht
  (ADR 0026). Die **internen Anmerkungen** aus dem Altsystem sehen nur Büro und Admin.
- **Dokumente** (Admin, Büro): Auf der Haushaltsseite unter „Dokumente“ Bescheide,
  Einwilligungen usw. als PDF oder Foto hochladen (höchstens 10 MB), mit Dokumentart, Titel und
  Dokumentdatum. Sie werden verschlüsselt gespeichert, nie öffentlich ausgeliefert, und jeder
  Abruf steht im Zugriffsprotokoll und im Änderungsprotokoll. Jede **Dokumentart** hat eine
  eigene Aufbewahrungsfrist („Einstellungen → Dokumentarten“, Admin; Vorgaben: Bescheid 24,
  Datenschutzeinwilligung 36, Sonstiges 12 Monate), gezählt ab dem Dokumentdatum, ohne Datum ab
  dem Hochladen. Danach löscht bintafeln das Dokument automatisch; die Tabelle zeigt den Tag.
  Dokumente hängen an der Kundennummer und überstehen den Import; wird der Haushalt gelöscht,
  werden sie mitgelöscht (ADR 0030).
- **Historie** (Admin, Büro): unten auf der Haushaltsseite, was sich wann geändert hat: neu im
  Kundenstamm bzw. aufgenommen (mit Antragsnummer), Status, Kundengruppe, Ausweis verlängert,
  Personen hinzugekommen oder entfallen, jeweils mit Quelle (Import, Aufnahme, Bearbeitung) und
  wer es war. Beim Import entsteht sie aus dem Vergleich mit dem vorherigen Stand. Sie hängt an
  der Kundennummer und wird nach 3 Jahren gelöscht (einstellbar unter „Einstellungen →
  Kundenstamm“; ADR 0031).
- Jeder Aufruf einer Detailseite steht im **Zugriffsprotokoll** („Kunden“ → „Zugriffsprotokoll“,
  nur Admin). Die Einträge werden nach 365 Tagen gelöscht, einstellbar unter
  „Einstellungen → Kundenstamm“.
- Oben auf der Detailseite stehen die wichtigsten Knöpfe: **Zum Einlass** (öffnet den Einlass
  mit diesem Kunden), **Ausweis drucken** (Admin, Büro), **Bearbeiten** und **Löschen …**
  (Admin). Löschen zeigt erst eine Seite, die aufzählt, was mitgelöscht wird; erst „Ja, …
  endgültig löschen“ löscht. Auch alle anderen Löschknöpfe fragen nach und nennen, was gelöscht
  wird.
- Admin und Büro finden auf der Detailseite zwei PDFs:
  - **Kundenausweis drucken:** Karte im Scheckkartenformat, mit Kundennummer als Barcode für den
    Scanner am Einlass. In 100 % Größe drucken. **Gestalten** (Admin): „Einstellungen →
    Kundenstamm → Kundenausweis gestalten“. Elemente (Ausweisname, Name der Tafel, Logo, Name,
    Kundengruppe, Ausgabestelle, Gültig bis, Kunde seit, Anzahl Personen, „Personen/Minderjährige“
    (z. B. 6/3: 6 Personen, davon 3 unter dem Alter aus „Kind bis“), freier Text mit
    Platzhaltern, farbige Fläche) einfügen, mit der Maus verschieben und in der Größe ändern;
    Hintergrundbild, optional eine Rückseite, Druck auf A4 mit Schnittmarken oder in
    Kartengröße für Kartendrucker. **Kundennummer und Barcode** sind immer auf der Vorderseite;
    der Barcode enthält nur die Kundennummer. „Vorschau als PDF“ zeigt den Ausweis mit
    erfundenen Daten.
  - **Sammeldruck:** In der Kundenliste druckt „Ausweise dieser … drucken (PDF)“ die Ausweise
    aller Haushalte der aktuellen Suche bzw. Filter (z. B. einer Kundengruppe), einen je Seite,
    höchstens 500 auf einmal.
  - **Auskunft nach Art. 15 DSGVO:** alle gespeicherten Daten des Haushalts samt Hinweisen zu
    Zweck, Speicherdauer und Rechten. Der Abruf steht im Zugriffsprotokoll.

## Online-Anträge

Menschen können sich online anmelden oder ihre Berechtigung verlängern (ADR 0024).

- **Einschalten:** „Anträge“ → „Formular einstellen“ (Admin). Dort je Feld wählen: nicht
  abfragen, freiwillig oder Pflicht; Links zu Datenschutzerklärung, Impressum, Erklärungen
  (z. B. Ablauf der Lebensmittelausgabe) und Voraussetzungen (wer berechtigt ist, welche
  Nachweise nötig sind) eintragen; die beiden letzten stehen gut sichtbar über dem Formular;
  festlegen, wer bei neuen Anträgen eine Mail bekommt. Danach „Online-Anträge annehmen“
  einschalten.
- **Adresse für die Webseite der Tafel:** `https://<domain>/antrag/`. Die Seite ist in
  **29 Sprachen** umstellbar und erkennt die Sprache des Browsers. Oben stehen Logo und Name
  der Tafel in der Farbe der Tafel (siehe Einstellungen).
- **Eigene Texte je Sprache** („Texte je Sprache“): Überschrift, Einleitung, Seite nach dem
  Absenden, Betreff und Inhalt der Antwortmail. Die Texte dürfen **HTML** enthalten
  (Überschriften, Absätze, Listen, Links, Bilder, Tabellen, Farben über `style="…"`);
  Skripte und Ähnliches werden beim Anzeigen entfernt. Platzhalter: `{nummer}`, `{tafel}`,
  in der Mail auch `{vorname}` und `{nachname}`. „Vorschau“ zeigt alles mit Beispielwerten,
  ohne zu speichern. Ohne eigene Texte gelten die mitgelieferten.
- **Staatsangehörigkeit** ist eine Auswahlliste aller Staaten (dazu „staatenlos“ und
  „ungeklärt“). Gespeichert wird der deutsche Name; in anderen Sprachen zeigt der Browser den
  Namen zusätzlich in der Sprache der Seite. Beim Bearbeiten von Personen gilt dieselbe Liste;
  importierte Werte, die nicht darin stehen, bleiben wählbar.
- **Eigene Gestaltung:** Im Feld „Eigene Gestaltung (CSS)“ lassen sich zusätzliche CSS-Regeln
  für das öffentliche Formular hinterlegen (nur für Kundige).
- Nach dem Absenden sehen Antragstellende eine Bestätigungsseite mit ihrer **Antragsnummer** und
  bekommen eine gestaltete **Antwortmail** (HTML mit Logo, dazu eine Klartextfassung) in ihrer
  Sprache, wenn sie eine Adresse angeben (Mailserver nötig).
- **Antragsliste** (Admin, Büro) unter „Anträge“: fortlaufende **Antragsnummern** (Startwert
  unter „Formular einstellen“ → „Nächste Antragsnummer ab“, z. B. 4201), neueste zuerst; Spalten
  #, Status, Kundennummer, Nachname, Vorname, Antrag vom, E-Mail, Telefon, Art,
  Staatsangehörigkeit, letzte Anmerkung; Klick auf eine Spaltenüberschrift sortiert; Suche;
  25/50/100/alle Zeilen; **CSV-Export** der angezeigten Liste. Je Zeile: Ansehen, Bearbeiten,
  Anmerkung, Löschen (Papierkorb, mit Rückfrage) und **Aufnehmen**. Reiter „Papierkorb“: dort
  endgültig löschen (Admin).
- **Aufnehmen** (Aufnahme-Assistent, ADR 0028) führt Schritt für Schritt:
  1. **Gibt es den Kunden schon?** Ähnliche Kunden mit Punkten, auch bei vertauschten Vor- und
     Nachnamen und Tippfehlern, dazu Geburtsdatum (auch mit vertauschtem Tag/Monat) und
     Anschrift. Bestehenden Kunden wählen oder „Neuer Kunde“.
  2. **Daten abgleichen:** je Angabe Kundenstamm oder Antrag wählen; Unterschiede sind markiert.
  3. **Angehörige** aus Haushalt und Antrag, ergänzen oder entfernen.
  4. **Bescheid und Gültigkeit:** Bescheidart (Liste „Einkommensarten“) und Gültigkeit des
     Ausweises; Vorschlag aus „Einstellungen → Kundenstamm“ (Vorgabe 12 Monate bis Monatsende).
  5. **Kundengruppe:** nur Gruppen mit freiem Platz (Höchstzahl Haushalte der Kundengruppe;
     beendete Haushalte zählen nicht).
  6. **Prüfen und speichern:** neuer Kunde mit der nächsten freien Kundennummer oder bestehender
     Kunde aktualisiert; der Antrag ist danach erledigt. Anschließend **Ausweis drucken** (PDF,
     auf jedem Drucker, z. B. einem Kartendrucker in Kartengröße).
- Die Übersetzungen stehen in `apps/antraege/uebersetzungen/`, eine Datei je Sprache.
  Korrekturen von Muttersprachlern sind willkommen.

## Einlass

„Einlass“ im Menü (Admin, Büro, Ausgabe):

1. Einmal die **Ausgabestelle** wählen, an der man arbeitet (gilt für die Sitzung).
2. Kundennummer **scannen** oder eintippen und Enter. Führende Nullen sind egal. Drei Wege,
   die sich beliebig mischen lassen; Eintippen geht immer:
   - **Handscanner** per USB oder Bluetooth (am PC oder Handy): Er arbeitet als Tastatur, das
     Feld hat den Fokus, der Scanner schickt die Nummer samt Enter. Im Scanner „Enter als
     Abschluss“ (Suffix CR) einstellen.
   - **Kamera** (Handy, Tablet oder Laptop): Knopf **📷 Kamera**, Barcode des Ausweises in den
     Rahmen halten; die Nummer wird eingetragen und geprüft. Beim ersten Mal fragt der Browser
     nach der Kamera-Erlaubnis. Der Browser erlaubt die Kamera nur über **https**, also im
     Produktionsmodus (im Entwicklungsmodus mit `http://IP` erscheint ein Hinweis). Die
     Erkennung läuft vollständig im Browser; es werden keine Bilder gespeichert oder versendet.
3. Die **Ampel** zeigt, ob abgeholt werden darf, und warum nicht:
   - 🔴 Sperre, Status gesperrt/beendet, Ausweis abgelaufen, heute schon so oft abgeholt wie
     erlaubt, Höchstzahl je Woche/14 Tage/Monat erreicht, keine Kundengruppe, heute nicht dran
     (einstellbar rot oder gelb)
   - 🟡 Ausweis läuft bald ab oder fehlt, andere Ausgabestelle, Status pausiert, heute schon
     abgeholt, wenn mehrfaches Abholen erlaubt ist
   - Unter „Einstellungen → Ausgabe und Ampel“: **Abholungen am selben Tag** (1 = einmal,
     2 = zweimal, 0 = beliebig oft) und **Höchstzahl je Zeitraum** (0 = keine Grenze).
   - 🟢 alles in Ordnung, oder eine Ausnahme für heute hebt eine Terminregel auf
   Daneben stehen Haushaltsgröße, alle Personen und Abholberechtigten mit Geburtsdatum,
   Ausgabestelle, Karte gültig bis, Kontostand, die letzten Abholungen und die **Notizen**;
   eine neue Notiz lässt sich gleich dort speichern. **Was der Einlass zeigt**, stellt der Admin
   unter „Einstellungen → Ausgabe, Ampel und Beiträge“ ein (Haken „Einlass zeigt: …“):
   Haushaltsgröße, Geburtsdaten, Abholberechtigte, Anschrift (Vorgabe aus), Begründung aktiver
   Sperren, letzte Abholungen, Farbe der Kundengruppe, Kontostand. Jede **Kundengruppe** kann eine
   **Farbe** bekommen („Einstellungen → Kundengruppen“); am Einlass erscheint dann ein farbiges
   Band mit dem Gruppennamen.
4. **Kunde anmelden:** Das Aufrufen allein trägt nichts ein. Erst der Knopf **„Kunde anmelden
   und Abholung buchen“** meldet den Kunden für heute an. Wird abgebrochen, einfach die nächste
   Nummer scannen; der Kunde lässt sich jederzeit wieder aufrufen. Ein Versehen lässt sich am
   selben Tag zurücknehmen. Admin und Büro können bei Rot wegen einer Terminregel eine
   **Ausnahme für heute** erteilen.
5. **Bezahlen:** Der Beitrag ist vorgeschlagen und änderbar. Im Pflichtfeld **„Gezahlt“** steht
   genau der Betrag, den der Kunde zahlt, **auch 0**. Vorgeschlagen ist, was nach Verrechnung des
   Guthabens fehlt (bei ausreichendem Guthaben also 0).
   - weniger als der Beitrag: Rest aus Guthaben, sonst angeschrieben (nur wenn in den
     Einstellungen erlaubt, sonst kommt eine Meldung und nichts wird gebucht)
   - mehr als der Beitrag: der Überschuss wird Guthaben
   - Danach steht groß da, was bar eingenommen, aus Guthaben verrechnet, angeschrieben oder
     gutgeschrieben wurde, und der neue Kontostand.
6. **Vorauszahlung:** läuft ebenfalls über „Gezahlt“: Was über den Beitrag hinaus gezahlt wird,
   wird Guthaben. Der Knopf **„Vorauszahlung Rest <Monat> eintragen“** setzt den passenden
   Betrag ins Feld (Abholtage bis Monatsende × Beitrag, abzüglich vorhandenen Guthabens) und
   erklärt die Rechnung. Ist heute keine Abholung möglich, gibt es stattdessen das Feld
   **„Gezahlt ohne Abholung“**. Eine Zahlung lässt sich am selben Tag zurücknehmen.
7. Den **Kontoverlauf** mit allen Buchungen und Korrekturbuchungen gibt es auf der Haushaltsseite
   (Admin, Büro).

Die Regeln stehen unter „Einstellungen → Ausgabe und Ampel“. Jeder Scan steht im
Zugriffsprotokoll. **Achtung:** Ein neuer Import des Kundenstamms ersetzt auch die am Einlass
eingetragenen Abholungen und Ausnahmen; der Prüfbericht warnt davor (ADR 0013).

### Beiträge

Unter „Einstellungen → Ausgabe, Ampel und Beiträge“:

- **Beitrag je zahlender Person** (Vorgabe 1,50 €) und **ab welchem Alter** gezahlt wird
  (Vorgabe 18). Personen ohne Geburtsdatum zahlen mit. Beispiel: 2 Erwachsene und 3 Kinder
  zahlen 2 × 1,50 € = 3,00 €.
- **Zusatzbeiträge** (je Abholung, je Erwachsenem, je Kind) gelten nur, wenn eingeschaltet
  (Vorgabe aus). Nach dem Update behalten Installationen mit bisher eingestellten Beträgen ihre
  Berechnung: Zusatzbeiträge sind dort eingeschaltet, der Beitrag je Person ist 0.
- **Beitragsfreie Zeiträume** („Einstellungen → Beitragsfreie Zeiträume“, z. B. vor
  Weihnachten): Der Einlass schlägt dann 0 € vor und zeigt „Heute beitragsfrei“; Vorschläge
  für Vorauszahlungen zählen diese Tage nicht.

### Sonderaktionen

„Ausgabe → Sonderaktionen“ (Admin, Büro): Aktionen neben der normalen Ausgabe, z. B.
Weihnachtsgutscheine oder Schulranzen.

- **Anlegen:** Bezeichnung, Zeitraum, wie viel je Haushalt (einmal je Haushalt, je Kind oder je
  Person), optional „nur Haushalte mit Kindern“, ein Hinweis für den Einlass und
  Auswahlmöglichkeiten (z. B. „Spielzeug“ und „Kleidung“, eine je Zeile).
- **Am Einlass:** Solange eine Aktion läuft, erscheint sie bei jedem Haushalt als eigene Karte mit
  Knöpfen („2× Spielzeug“, „2× Kleidung“). Ein Klick trägt die Teilnahme ein; jeder Haushalt kann
  je Aktion einmal teilnehmen. Am selben Tag lässt sich die Teilnahme zurücknehmen. Danach zeigt
  die Karte „✓ Erhalten am …“.
- **Auswertung:** Die Seite einer Aktion zeigt Teilnahmen und Stückzahlen je Auswahl, mit
  CSV-Export (nur Kundennummern, keine Namen).
- Teilnahmen hängen an der Kundennummer, überstehen den Import, stehen in der Auskunft nach
  Art. 15 und werden nach derselben Frist gelöscht wie Abholungen (ADR 0032).

## Kasse

„Kasse“ im Menü (Admin, Büro, Ausgabe) wertet die Kontobuchungen aus:

- **Tag** (je Ausgabestelle), **Monat** (je Tag) und **Jahr** (je Monat). Jeder Tag, Monat und
  jedes Jahr lässt sich rückwirkend wählen oder mit „früher“/„später“ durchblättern; ein Klick
  auf einen Tag oder Monat öffnet die feinere Ansicht.
- Filter nach Ausgabestelle.
- Kennzahlen:
  - **Bar eingenommen** (bar gezahlte Beiträge + Einzahlungen)
  - Abholungen mit Beitrag und Beiträge gesamt, aufgeteilt in bar, aus Guthaben und angeschrieben
  - Einzahlungen und Korrekturen
- Admin und Büro sehen in der Tagesansicht zusätzlich die einzelnen Buchungen mit Kundennummer.
- **Drucken (PDF):** Die Tagesansicht ergibt den **Kassenabschluss** mit Feldern für gezähltes
  Bargeld und Unterschriften, Monat und Jahr einen **Kassenbericht**. Der Filter nach
  Ausgabestelle gilt mit.

Die Kasse bleibt auch nach einem Neuimport des Kundenstamms vollständig (ADR 0014).

## Entwicklungs- und Produktionsmodus

Umgeschaltet wird über **eine** Zeile in `.env`:

| `BINTAFELN_DOMAIN` | Modus | Zugriff |
|---|---|---|
| leer | Entwicklung / internes Netz | `http://<IP>` ohne TLS |
| z. B. `tafel.example.org` | Produktion | `https://tafel.example.org` mit automatischem Zertifikat (Let's Encrypt) |

Für den Produktionsmodus:

1. Einen DNS-Eintrag (A/AAAA) der Domain auf den Server zeigen lassen.
2. Ports **80** und **443** aus dem Internet zum Server freigeben (80 wird für die
   Zertifikatsausstellung und die Weiterleitung auf HTTPS gebraucht).
3. `BINTAFELN_DOMAIN=tafel.example.org` in `.env` setzen.
4. `docker compose up -d` ausführen – Caddy holt das Zertifikat selbstständig.

Im Produktionsmodus setzt bintafeln zusätzlich sichere Cookies und HSTS und nimmt
Anfragen nur noch für die eingetragene Domain an.

> Der Entwicklungsmodus überträgt Passwörter unverschlüsselt. Er ist nur für Tests oder ein
> abgeschottetes internes Netz gedacht.

## Betrieb

Alle Betriebsaufgaben erledigt das Werkzeug `./betrieb` im Projektordner:

```bash
./betrieb status                  # Dienste, letzte Sicherung, vorhandene Sicherungen
./betrieb update                  # sichern, neuen Stand holen, neu bauen, starten
./betrieb sichern                 # sofort sichern
./betrieb schluessel              # Schlüsselpaar für die Sicherungen erzeugen
./betrieb wiederherstellen NAME   # eine Sicherung zurückspielen
```

Weitere nützliche Befehle:

```bash
docker compose logs -f app        # Protokoll der Anwendung
docker compose logs backup        # Protokoll der Sicherungen
docker compose down               # anhalten (Daten bleiben erhalten)
```

### Sicherung einrichten

Der Dienst `backup` sichert jeden Tag die Datenbank und die hochgeladenen Dateien
(Uhrzeit, Anzahl und Ablageort stehen in `.env`). Die Sicherungen werden mit
[age](https://age-encryption.org) verschlüsselt. Auf dem Server liegt nur der **öffentliche**
Schlüssel. Wer den Server oder die Sicherungen stiehlt, kann sie also nicht lesen. Ohne
Schlüssel wird nicht gesichert, unverschlüsselt wird nie gesichert.

Einmalig einrichten:

```bash
./betrieb schluessel
```

Das Werkzeug trägt den öffentlichen Schlüssel in `.env` ein und zeigt den **privaten**
Schlüssel an (eine Zeile, beginnt mit `AGE-SECRET-KEY-`). Diese Zeile:

- **nicht auf dem Server speichern**, sondern getrennt aufbewahren: im Passwortmanager,
  ausgedruckt im Tresor oder auf einem USB-Stick, am besten an zwei Orten;
- wird nur zum Wiederherstellen gebraucht. **Ohne sie lassen sich die Sicherungen nicht öffnen.**

Danach zeigt die Startseite allen Admins, wann zuletzt gesichert wurde, und warnt, wenn die
letzte erfolgreiche Sicherung älter als zwei Tage ist.

Jede Sicherung ist ein Ordner in `sicherungen/` (z. B. `2026-01-31_023000`) mit
`datenbank.dump.age`, `medien.tar.age` und `info.txt`. Ältere Stände als
`BINTAFELN_SICHERUNG_ANZAHL` werden automatisch gelöscht.

### Sicherungen auf einen anderen Rechner kopieren

Eine Sicherung auf demselben Server schützt nicht vor einem Plattenschaden oder Verlust des
Servers. Kopieren Sie den Ordner `sicherungen/` regelmäßig an einen anderen Ort. Weil die Dateien
verschlüsselt sind, darf das auch ein fremder Speicher sein. Beispiel mit `rsync` von einem
anderen Linux-Rechner aus, täglich per Cronjob:

```bash
rsync -a --delete benutzer@tafel-server:/opt/bintafeln/sicherungen/ /pfad/zu/tafel-sicherungen/
```

### Wiederherstellen

1. Die Zeile mit dem privaten Schlüssel in eine Datei auf dem Server schreiben,
   z. B. `schluessel.txt` (nach dem Wiederherstellen wieder löschen).
2. Die gewünschte Sicherung aussuchen: `./betrieb status`
3. Wiederherstellen:

   ```bash
   ./betrieb wiederherstellen 2026-01-31_023000 --schluessel schluessel.txt
   rm schluessel.txt
   ```

Das Werkzeug prüft zuerst, ob sich die Sicherung mit dem Schlüssel öffnen lässt, fragt nach,
**sichert den aktuellen Stand** und ersetzt dann Datenbank und hochgeladene Dateien vollständig.
Danach startet die Anwendung wieder, Migrationen laufen automatisch.

Auf einem **neuen Server**: bintafeln wie oben installieren, den Ordner `sicherungen/`
dorthin kopieren und dann wie beschrieben wiederherstellen.

### Aktualisieren

```bash
cd /opt/bintafeln
./betrieb update
```

Das Werkzeug zeigt die letzten Versionen mit Nummern:

```
Welche Version installieren?
  1) 2026.10.8  (neueste)
  2) 2026.10.7  (installiert)
  3) 2026.10.6
  m) Entwicklungsstand (main, zum Testen)
Auswahl [1, nach 3 Sekunden automatisch]:
```

Ohne Eingabe nimmt es nach **3 Sekunden die neueste Version**. Dann sichert es, holt den Stand,
aktualisiert die Images und startet neu; Migrationen laufen beim Start automatisch. Direkt geht
es auch mit `./betrieb update 2026.10.6` oder `./betrieb update main`.

**Zurück auf eine ältere Version:** einfach deren Nummer wählen. Nach einer Rückfrage wird
gesichert, dann setzt das noch laufende neuere Programm die Datenbank auf den Stand der älteren
Version zurück (Migrationen rückwärts), erst danach wird die ältere Version gebaut. Was nur die
neuere Version speichert, geht dabei verloren; alles andere bleibt. Klappt das Zurücksetzen nicht,
bleibt alles beim bisherigen Stand, und die Sicherung von eben lässt sich wiederherstellen.

**Versionen** heißen nach dem Kalender `JAHR.MONAT.NUMMER`, z. B. `2026.10.1`, `2026.10.2` …;
im nächsten Monat beginnt die Nummer wieder bei 1 (`2026.11.1`). Nach jedem Merge auf `main`
legt GitHub die nächste Version samt Release mit den Änderungen automatisch an (ADR 0023).
Die installierte Version zeigt `./betrieb status`, Admins sehen sie unten auf jeder Seite.

> **Einmalig beim Wechsel auf diese Version:** Das Werkzeug `./betrieb` gibt es erst ab hier.
> Deshalb dieses eine Mal `git pull && docker compose up -d --build` ausführen, danach
> `./betrieb schluessel`. Ab dann genügt `./betrieb update`.

## Mehrere Installationen auf einem Server

Auf einem Server können mehrere bintafeln laufen, z. B. `tafel.example.org` und eine Demo unter
`demo.example.org`, dazu eine einfache Webseite unter `example.org` (ADR 0022). Ein
**gemeinsamer Proxy** belegt die Ports 80 und 443 und holt für jede Domain das Zertifikat; jede
Installation hat ihren eigenen Ordner, ihre eigene Datenbank und ihre eigenen Sicherungen.

1. Bei jeder Domain per DNS-Eintrag (A-Record) auf die IP des Servers zeigen.
2. Den gemeinsamen Proxy einrichten (einmal):

   ```bash
   cd /opt/bintafeln/docker/gemeinsamer-proxy     # aus einer der Installationen
   cp Caddyfile.beispiel Caddyfile                 # Domains und Namen eintragen
   docker compose up -d
   ```

   Die Webseite liegt im Ordner `webseite/` daneben.
3. Jede Installation wie oben in einen **eigenen Ordner** klonen (z. B. `/opt/bintafeln-demo`)
   und in ihrer `.env` zusätzlich setzen:

   ```
   BINTAFELN_DOMAIN=demo.example.org
   COMPOSE_PROJECT_NAME=demo
   COMPOSE_FILE=docker-compose.yml:docker/hinter-proxy.yml
   ```

   `COMPOSE_PROJECT_NAME` ist der Name, unter dem der gemeinsame Proxy sie erreicht
   (`reverse_proxy demo:80` in seinem Caddyfile). Danach `docker compose up -d`; `./betrieb`
   funktioniert in jedem Ordner wie gewohnt.

Eine bestehende einzelne Installation lässt sich später so umstellen: Proxy einrichten, in ihrer
`.env` die drei Zeilen ergänzen (Name z. B. `tafel`) und `docker compose up -d`.

### Öffentliche Demo

**Schritt für Schritt:** [docs/demo-einrichten.md](docs/demo-einrichten.md) – zum Ausprobieren
neben der Dummy-Tafel (`http://IP:8080`) oder öffentlich unter einer eigenen Domain.

Kurzfassung: Für eine Demo mit erfundenen Daten in deren `.env` zusätzlich:

```
BINTAFELN_DEMO=true
BINTAFELN_DEMO_PASSWORT=ein-eigenes-passwort   # steht öffentlich auf der Anmeldeseite
```

Dann einmal und danach jede Nacht (Cronjob auf dem Server, z. B. `crontab -e`) zurücksetzen:

```bash
cd /opt/bintafeln-demo && docker compose exec -T app python manage.py demo_zuruecksetzen
# Cronjob, täglich 3:15 Uhr:
# 15 3 * * * cd /opt/bintafeln-demo && docker compose exec -T app python manage.py demo_zuruecksetzen
```

Das **löscht alle Daten** der Demo und legt die Beispieldaten aus `docs/beispiele/import` sowie
die Konten `demo-admin`, `demo-buero`, `demo-ausgabe`, `demo-personal` und `demo-fest` an. Jede
Seite zeigt einen Hinweis „Demoversion“; Passwort ändern, Zwei-Faktor und Mailserver sind
gesperrt, damit niemand andere Besucher aussperrt. Der Befehl läuft nur mit
`BINTAFELN_DEMO=true` und bricht ab, wenn es Konten gibt, die nicht mit `demo-` beginnen
(Schutz vor dem Aufruf im Ordner einer echten Installation). Für die Demo keine Sicherung einrichten.

## Entwicklung

Voraussetzungen: Python 3.12+, eine erreichbare PostgreSQL-Datenbank.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

# Tests (erwartet PostgreSQL auf localhost, Benutzer "bintafeln" mit Recht CREATEDB;
# Passwort über POSTGRES_PASSWORD, Standard in bintafeln/settings_test.py)
.venv/bin/pytest

# Linter
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Einen passenden Datenbank-Container für die Tests startet z. B.:

```bash
docker run -d --name bintafeln-testdb -p 5432:5432 \
  -e POSTGRES_USER=bintafeln -e POSTGRES_PASSWORD=nur-lokal-test postgres:17-alpine
```

GitHub Actions führt bei jedem Pull Request ruff, shellcheck und pytest aus und spielt mit
`tests/sicherung_e2e.sh` eine echte Sicherung und Wiederherstellung im Docker-Aufbau durch.
Dieses Skript überschreibt `.env`, lokal also nur in einer Wegwerf-Kopie starten.

### Verzeichnisstruktur

```
bintafeln/          Django-Projekt (Einstellungen, URLs)
apps/core/          Tafel-Einstellungen, Einrichtung, Startseite, Änderungsprotokoll
apps/konten/        Benutzer, Rollen, Anmeldung, Zwei-Faktor
apps/kunden/        Kundenstamm: Haushalte, Personen, Zusatzfelder, Einstellungen
templates/          Django-Templates
static/             CSS und HTMX
docker/             Caddyfile und Start-Skript des App-Containers
docker/backup/      Dienst "backup" (Sicherungsskript)
betrieb             Betriebswerkzeug: Update, Sicherung, Wiederherstellung
docs/adr/           Architekturentscheidungen (warum bintafeln so gebaut ist)
docs/               fachkonzept.md (kommende Module), importformat.md (Import des
                    Kundenstamms), beispiele/ mit erfundenen Beispieldateien
tests/              pytest-Tests und Ende-zu-Ende-Test der Sicherung
```

## Grundsätze

- Keine echten Daten, Passwörter oder Schlüssel im Repository – `.env` ist ausgeschlossen.
- Keine festen IP-Adressen, Pfade oder Tafel-Namen im Code; alles kommt aus `.env` oder der
  Datenbank.

## Lizenz

bintafeln ist freie Software unter der [GNU AGPL v3.0](LICENSE). Wer eine veränderte Version
als Netzdienst betreibt, muss den Nutzerinnen und Nutzern den Quelltext zugänglich machen.
