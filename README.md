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
  Tafel – in der Datenbank, nicht im Code. Dazu ein **Hintergrundbild** für die Anmeldeseite
  (volle Stärke) und wahlweise ein eigenes für die übrigen Seiten; dort regelt ein Schieber die
  Stärke von 0 % (nicht sichtbar) bis 100 %. Die Inhalte stehen weiter auf weißen Karten.
  Hintergrundbilder und Logo werden beim Hochladen verkleinert (`apps/core/bilder.py`: längste
  Seite 1920 bzw. 800 Pixel, ohne Bilddaten wie den Aufnahmeort); große, schon vorhandene Bilder
  verkleinert das Update einmalig (das Original bleibt als Datei liegen). Caddy lässt sie einen
  Tag zwischenspeichern. Vorher dauerte das Anmelden mit einem Handyfoto als Hintergrund über
  eine langsame Leitung viele Sekunden.
- **Speicher und Fotos** (ADR 0064, „Einstellungen → Systemsteuerung → Speicher und Fotos“):
  Hochgeladene Fotos (Quittungen, Dokumente, Belege, Führerscheinkopien, Antragsanhänge) werden
  beim Speichern verkleinert – Größe (Vorgabe 1600 Pixel), Qualität (Vorgabe 75 %) und
  Graustufen sind einstellbar, PDFs bleiben unverändert. Die Seite zeigt den belegten Platz,
  verkleinert vorhandene Fotos nachträglich (Originale bleiben daneben) und löscht die Originale
  erst, wenn eine Sicherung höchstens 24 Stunden alt ist.
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
- **Hilfe im Programm:** ein ausführliches Handbuch („Hilfe“ im Menü), das nur die Kapitel
  zeigt, die zu den Rechten des Kontos passen (ADR 0038).
- **Menü links** mit aufklappbaren Bereichen (Ausgabe, Kunden, Anträge, Team, Einstellungen);
  die Einstellungen haben Untermenüs (Tafel, Kunden, Ausgabe, Verein, Mitarbeitende,
  Systemsteuerung). Jede Rolle sieht nur, was sie darf. Auf Handys (unter 768 Pixel Breite) öffnet „☰ Menü“ das Menü.
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

### Testen im Heimnetz mit https (für die Kamera am Handy)

Im Entwicklungsmodus läuft bintafeln über `http://IP`. Browser geben die Kamera aber nur über
https frei. Für Tests im Heimnetz in der `.env` die IP des Servers eintragen:

```bash
BINTAFELN_HEIMNETZ_ADRESSE=192.168.178.20   # Beispiel, eigene IP einsetzen
docker compose up -d
```

Dann ist bintafeln zusätzlich unter `https://192.168.178.20` erreichbar; `http://` geht weiter.
Caddy stellt das Zertifikat selbst aus, deshalb warnt der Browser beim ersten Aufruf: „Erweitert“
→ „Weiter zu …“ wählen. Danach fragt das Handy wie gewohnt nach der Kamera. Im Produktionsmodus
(`BINTAFELN_DOMAIN` gesetzt) wird die Variable nicht gebraucht (ADR 0041).

### 6. Sicherung einrichten

```bash
./betrieb schluessel
```

Den angezeigten privaten Schlüssel sicher und getrennt vom Server aufbewahren, siehe
[Sicherung einrichten](#sicherung-einrichten).

## Zwei-Faktor-Anmeldung

Bei der Anmeldung wird zusätzlich zum Passwort ein 6-stelliger Code aus einer
Authenticator-App verlangt (z. B. Aegis, FreeOTP, Google Authenticator). Das Anmeldefenster
fragt zuerst nur Benutzername und Passwort; ist Zwei-Faktor eingerichtet, folgt ein eigenes
Fenster für den Code (5 Minuten gültig, höchstens 5 Versuche).

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

- **Gerät merken:** Unter „Einstellungen → Systemsteuerung → Anmeldung und Zwei-Faktor“ stellt
  ein Admin ein, wie lange ein Gerät vertraut werden darf (aus, 1, 7, 14, 30 oder 90 Tage; gilt
  für alle Rollen). Wer bei der Anmeldung mit Code „Diesem Gerät … vertrauen“ anhakt, braucht auf
  diesem Browser so lange keinen Code, das Passwort weiterhin. Im Browser liegt nur ein
  signiertes Cookie, in der Datenbank eine Prüfsumme. Ungültig wird das Gerät nach Ablauf, nach
  einer Passwortänderung, nach neuer Einrichtung oder Zurücksetzen der Zwei-Faktor-Anmeldung und
  wenn es unter „Mein Konto“ (eigene Geräte) oder bei „Mitarbeitende“ (Admin) entfernt wird.
  „Aus“ entfernt alle vertrauten Geräte.

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

### Mitarbeitende einer Ausgabestelle

Unter „Team → Mitarbeitende“ lässt sich jedes Konto einer oder mehreren **Ausgabestellen**
zuordnen. Wer zugeordnet ist, ruft nur Kunden auf, deren Kundengruppe zu einer dieser
Ausgabestellen gehört: in der Kundenliste, auf der Haushaltsseite und am Einlass. Bei einem
anderen Kunden erklärt bintafeln, warum („Kunde 200 gehört zur Ausgabestelle „Nord“ …
Sie sind der Ausgabestelle „Mitte“ zugeordnet …“). Ohne Zuordnung gibt es keine Einschränkung;
mit dem Recht „Kunden aller Ausgabestellen aufrufen“ (Vorgabe: Admin und Büro) ebenfalls nicht
(ADR 0034).

Gibt eine Ausgabestelle an mehreren Tagen aus, filtert die Kundenliste nach **Ausgabetag**. Sie
startet mit dem eigenen Tag (Feld „Ausgabetage“ bei den Mitarbeitenden; sonst der heutige, falls
an dem Tag Ausgabe ist). Mit dem Recht „Kundenliste als CSV-Datei exportieren“ (Vorgabe: Büro und
Ausgabe) lädt „Als CSV exportieren (Excel)“ die gefilterte Liste herunter; die Spalten wählt der
Admin unter „Einstellungen → Kunden → Kundenstamm“, Kontaktdaten, Kontostand und Art.-9-Felder
bleiben ohne das passende Recht leer, und jeder Export steht im Zugriffsprotokoll (ADR 0058).
Die Kundenliste zeigt dieselben Spalten wie der Export (Einstellung „Spalten der Kundenliste und
des Exports“); unter „Spalten wählen“ blendet jede Person einzelne für ihr Konto aus
(`Benutzer.kundenliste_aus`). Die Spalten sind per Klick sortierbar (der Export übernimmt die
Sortierung; Spalten mit Recht nur mit diesem Recht),
„Letzter Besuch“ steht wie überall mit Uhrzeit der letzten Abholung, und in allen Listen mit
mehreren Seiten steht die Blätterleiste oben und unten (`{% blaettern seite %}` aus
`apps/core/templatetags/liste.py`). Kundenliste, Anträge, Adressen, Spenden, Mitglieder und das
Modul Listen haben ganz links ein **Auswahlkästchen** je Zeile (im Kopf: alle/keine); Export und
Druck nehmen die angehakten Zeilen, ohne Haken alle (`{% auswahl_formular %}`,
`apps/core/listenauswahl.py`, `static/js/auswahl.js`).

## Mitarbeitende

**Konten der Ausgabestellen** (ADR 0059): Für Einlass-Tablets, die wechselnde Personen bedienen,
bekommt jede Ausgabestelle unter „Team → Ausgabestellen-Konten“ ein eigenes Konto. Anmeldung mit
dem **Namen der Ausgabestelle** und Passwort, ohne Zwei-Faktor; Rolle Ausgabe, nur Kunden dieser
Ausgabestelle; Abmeldung nach 30 Minuten ohne Eingabe. Nach 5 falschen Passwörtern ist die
Anmeldung eines Kontos 15 Minuten gesperrt (gilt für alle Konten). Zwei-Faktor sehen diese
Konten nur, wenn unter „Einstellungen → Systemsteuerung → Anmeldung und Zwei-Faktor“ freigeschaltet
(Vorgabe aus; beim Ausschalten werden eingerichtete Geräte dieser Konten entfernt). „Meine Daten“
(Auskunft) gibt es für sie nicht.

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

## Suche

Im Seitenkopf steht auf jeder Seite ein **Suchfeld**. Ab 3 Zeichen erscheinen die Treffer
darunter, Enter öffnet eine Ergebnisseite. Ohne Kürzel sucht es **Seiten des Programms**
(Menüpunkte, z. B. „ausgabestellen“ führt zu „Kunden → Ausgabestellen“), **Listen und
Einstellungen** (Ausgabestellen, Kundengruppen, Einkommens- und Dokumentarten, Notiz- und
Serienbrief-Vorlagen, Rollen, Mitgliedsnummern, Belegnummern von Spenden, aus Modulen z. B.
Selbstabholer und Termine), Kunden (Vor- und
Nachname, auch Teile wie „mül“, Kundennummer, Abholberechtigte), Anträge, Adressen,
Mitarbeitende und **Abschnitte des Handbuchs**. Ein Kürzel mit Leerzeichen davor sucht nur in
einem Bereich:

| Kürzel | Bereich | Beispiel |
|---|---|---|
| `k` | Kunden | `k müller` |
| `n` | Notizen (Text) | `n bescheid` |
| `a` | Anmerkungen zu Haushalten und Anträgen | `a deutsch` |
| `s` | Anschrift (Straße, PLZ, Ort) | `s linden` |
| `t` | Telefon und E-Mail | `t 0171` |
| `d` | Dokumente zum Haushalt (Titel) | `d jobcenter` |
| `an` | Anträge (Name, Antragsnummer) | `an müller` |
| `m` | Mitarbeitende | `m anna` |
| `p` | Programm (Menüpunkte) | `p ausgabestellen` |
| `l` | Listen und Einstellungen | `l zentrale` |
| `h` | Handbuch | `h ampel` |

`?` im Suchfeld zeigt die Kürzel. Jeder Bereich erscheint nur mit dem passenden Recht; wer einer
Ausgabestelle zugeordnet ist, findet nur deren Kunden (ADR 0040).

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
  Haushalt ebenfalls. „Neuer Haushalt“ steht in der Kundenliste und im Menü. Die Seite folgt
  der Reihenfolge im Büro: 1. Hauptperson (deren Name auf den Ausweis kommt), 2. Anschrift und
  Kontakt, 3. weitere Angaben (Zusatzfelder der Tafel, z. B. Ernährung), 4. Angehörige (Nachname
  leer = wie Hauptperson), 5. Bescheid und Gültigkeit des Ausweises, 6. Kundengruppe (nur mit
  freiem Platz). Die **Kundennummer** vergibt bintafeln (nächste freie Zahl); ändern darf sie nur,
  wer das Recht „Kundennummer vergeben und ändern“ hat (Vorgabe nur Admin), auch beim Bearbeiten.
  Mitgeliefert sind ausgeschaltete Zusatzfelder als Vorschlag (Ernährung, kein Schweinefleisch,
  Allergien, Haustiere, keine Kochmöglichkeit), einzuschalten unter „Einstellungen → Kundenstamm
  und Zusatzfelder“; die zwei mit Art.-9-Bezug sind entsprechend markiert. Kundengruppen, Ausgabestellen
  und Einkommensarten pflegt der Admin unter „Einstellungen → Kundenstamm → Listen“.
  **Achtung:** Solange aus dem Altsystem importiert wird, ersetzt der nächste Import alle
  Änderungen; der Prüfbericht nennt die Zahl der geänderten Haushalte (ADR 0025).
- **Ausgabestellen** („Kunden → Ausgabestellen“, ADR 0048): Übersicht und eigene Seite je
  Ausgabestelle mit Anschrift, Telefon, E-Mail, allgemeinen Anmerkungen, Zeiten (Ausgabe,
  Anlieferung, Sortieren …), Ansprechpartnern (Mitarbeitende per Auswahl oder extern) und ihren
  Kundengruppen. „In Google Maps öffnen“ zeigt den Weg; die eingebettete Karte lädt erst nach
  Klick auf „Karte anzeigen“, vorher gehen keine Daten an Google. Pflegen mit dem Recht
  „Kundengruppen, Ausgabestellen …“ („Bearbeiten“ auf der Seite).
- **Notizen:** Ausgabe, Büro und Admin schreiben Notizen zum Haushalt, auf der Haushaltsseite
  oder direkt am Einlass. **Notiz-Vorlagen** („Einstellungen → Kundenstamm → Listen →
  Notiz-Vorlagen“, Admin) erscheinen abgesetzt unter den Notizen als umrandete „+“-Knöpfe (deutlich anders als Notizen): ein Klick speichert den Text als Notiz. Jede
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
- **Nachrichten der Ausgabestellen** (ADR 0062): Gehört ein gesuchter Kunde nicht zur eigenen
  Ausgabestelle, schreibt man mit „✉ Nachricht an die Verwaltung“ (Einlass und Kundenliste) eine
  Nachricht zur Kundennummer, ohne Daten des Kunden zu sehen. Das Büro (Recht „Nachrichten der
  Ausgabestellen zu Kunden lesen“) sieht sie unter „Kunden → Nachrichten der Ausgabestellen“, auf
  der Startseite und auf der Haushaltsseite; erledigte werden nach 90 Tagen gelöscht.
- **Kundengruppe nur mit gültigem Ausweis** (ADR 0061): Pausierte, gesperrte, beendete Kunden
  und Kunden mit abgelaufenem Ausweis fallen automatisch aus der Kundengruppe, bei Änderungen
  sofort, sonst täglich und beim Import. Abschaltbar unter „Einstellungen → Kunden →
  Kundenstamm“. Die Haushaltsseite zeigt unter der Historie, von wann bis wann ein Kunde in
  welcher Kundengruppe war (auch in der Auskunft; gelöscht wie die Historie).
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
  importierte Werte, die nicht darin stehen, bleiben wählbar. Wird sie abgefragt, hat auch jede
  weitere Person im Haushalt ihre eigene Staatsangehörigkeit (im Antrag, in der Bearbeitung durch
  das Büro und im Aufnahme-Assistenten; sie geht mit in den Kundenstamm).
- **Eigene Gestaltung:** Im Feld „Eigene Gestaltung (CSS)“ lassen sich zusätzliche CSS-Regeln
  für das öffentliche Formular hinterlegen (nur für Kundige).
- Nach dem Absenden sehen Antragstellende eine Bestätigungsseite mit ihrer **Antragsnummer** und
  bekommen eine gestaltete **Antwortmail** (HTML mit Logo, dazu eine Klartextfassung) in ihrer
  Sprache, wenn sie eine Adresse angeben (Mailserver nötig).
- **Antragsliste** (Admin, Büro) unter „Anträge“ (die Zahl im Menü zeigt die offenen Anträge): fortlaufende **Antragsnummern** (Startwert
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
  3. **Angehörige** aus Haushalt und Antrag (mit eigener Staatsangehörigkeit), ergänzen oder
     entfernen.
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
     nach der Kamera-Erlaubnis; bintafeln kündigt das an. Ist die Kamera gesperrt, zeigt
     bintafeln passend zum Gerät, wo man sie freigibt, und „Erneut versuchen“. Der Browser
     erlaubt die Kamera nur über **https**: im Produktionsmodus immer, im Heimnetz mit
     `BINTAFELN_HEIMNETZ_ADRESSE` (siehe „Testen im Heimnetz mit https“). Über `http://IP`
     erscheint ein Hinweis, mit https im Heimnetz ein Knopf „Über https öffnen“. Die Erkennung
     läuft vollständig im Browser; es werden keine Bilder gespeichert oder versendet.
3. Die **Ampel** zeigt, ob abgeholt werden darf, und warum nicht:
   - 🔴 Sperre, Status gesperrt/beendet, Ausweis abgelaufen, heute schon so oft abgeholt wie
     erlaubt, Höchstzahl je Woche/14 Tage/Monat erreicht, keine Kundengruppe, heute nicht dran
     (einstellbar rot oder gelb)
   - 🟡 Ausweis läuft bald ab oder fehlt, andere Ausgabestelle, Status pausiert, heute schon
     abgeholt, wenn mehrfaches Abholen erlaubt ist, Kundengruppe ohne Wochentage (dann lässt sich
     nicht prüfen, ob heute dran ist; für „jeden Tag“ alle Tage anhaken)
   - Unter „Einstellungen → Ausgabe und Ampel“: **Abholungen am selben Tag** (1 = einmal,
     2 = zweimal, 0 = beliebig oft) und **Höchstzahl je Zeitraum** (0 = keine Grenze).
   - **Eigene Texte der Ampel:** Ebenda lässt sich jede Meldung in eigenen Worten formulieren
     (leer = Standardtext), mit Platzhaltern wie `{datum}`, `{gruppe}` oder `{tage}`; welche
     es gibt, steht unter jedem Feld. Farbe und Regel bleiben gleich, nur der Text ändert sich.
   - 🟢 alles in Ordnung, oder eine Ausnahme für heute hebt eine Terminregel auf
   Daneben stehen Haushaltsgröße, alle Personen und Abholberechtigten mit Geburtsdatum,
   Ausgabestelle, Karte gültig bis, Kontostand, die letzten Abholungen und die **Notizen**;
   eine neue Notiz lässt sich gleich dort speichern. **Was der Einlass zeigt**, stellt der Admin
   unter „Einstellungen → Ausgabe, Ampel und Beiträge“ ein (Haken „Einlass zeigt: …“):
   Haushaltsgröße, Geburtsdaten, Abholberechtigte, Anschrift (Vorgabe aus), Begründung aktiver
   Sperren, letzte Abholungen, Farbe der Kundengruppe, Kontostand. Jede **Kundengruppe** kann eine
   **Farbe** bekommen („Einstellungen → Kundengruppen“); am Einlass erscheint dann ein farbiges
   Band mit dem Gruppennamen.
4. **Kunde anmelden:** Solange ein Kunde angezeigt wird, ist das Suchfeld ausgeblendet. Oben
   rechts stehen Beitrag, „Gezahlt“ und die Knöpfe **„Abholung eintragen“** und **„Abbrechen“**.
   Das Aufrufen allein trägt nichts ein; erst „Abholung eintragen“ meldet den Kunden für heute
   an, danach erscheint sofort wieder das Suchfeld mit einer Bestätigung (und einem Link zurück
   zum Kunden). „Abbrechen“ führt ohne Eintrag zurück zur Suche; der Kunde lässt sich jederzeit
   wieder aufrufen (ADR 0039). Ein Versehen nimmt nur
   zurück, wer das Recht dazu hat (Admin immer); alle anderen schicken einen **Korrekturwunsch**
   (siehe unten). Entschiedene Korrekturwünsche der letzten 14 Tage stehen auf der Einlass-Karte;
   eine zurückgenommene Abholung von heute bringt die Nummer im Aufruf an ihren alten Platz. Admin und Büro können bei Rot wegen einer Terminregel eine
   **Ausnahme für heute** erteilen.
   Unter dem Suchfeld klappt **„Letzte Kunden heute“** die letzten 20 Kunden auf: an dieser
   Ausgabestelle eingetragene Abholungen und die selbst aufgerufenen Kunden, mit Uhrzeit und
   „abgeholt“ oder „aufgerufen“; ein Klick öffnet den Kunden wieder.
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
   **„Gezahlt ohne Abholung“**. Auch eine Zahlung nimmt nur zurück, wer das Recht dazu hat;
   sonst geht ein Korrekturwunsch.
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

### Korrekturwünsche

Am Einlass sollen Kunden nicht nachträglich verändert werden. Wer eine Abholung, Zahlung oder
Sonderaktion zurücknehmen will, aber nicht das Recht „Abholungen, Zahlungen und Sonderaktionen
selbst zurücknehmen“ hat (Vorgabe: nur Admin), klickt **„Korrektur beantragen“**, wählt einen
Grund (z. B. „Versehentlich gebucht“, „Falscher Kunde aufgerufen“) und schreibt optional eine
Anmerkung.

- Alle mit dem Recht „Korrekturwünsche vom Einlass entscheiden“ (Admin immer; z. B. dem Büro
  geben) bekommen eine Mail, wenn ein Mailserver eingerichtet ist, und sehen auf der Startseite
  die Zahl der offenen Wünsche.
- „Ausgabe → Korrekturwünsche“: **Zurücknehmen** führt die Korrektur aus (Kundenkonto und Kasse
  werden mitkorrigiert), **Ablehnen** lässt alles, wie es ist; beides optional mit Antwort.
- Am Einlass steht beim Eintrag „Korrektur beantragt …, wartet auf Entscheidung“.
- Wer das Recht zum Zurücknehmen hat, kann es direkt tun, auch an späteren Tagen.
- Entschiedene Wünsche werden nach der Frist für Abholungen gelöscht (ADR 0035).

### Sonderaktionen

„Ausgabe → Sonderaktionen“ (Admin, Büro): Aktionen neben der normalen Ausgabe, z. B.
Weihnachtsgutscheine oder Schulranzen.

- **Anlegen:** Bezeichnung, Zeitraum, wie viel je Haushalt (einmal je Haushalt, je Kind oder je
  Person), optional „nur Haushalte mit Kindern“, ein Hinweis für den Einlass und
  Auswahlmöglichkeiten (z. B. „Spielzeug“ und „Kleidung“, eine je Zeile).
- **Am Einlass:** Solange eine Aktion läuft, erscheint sie bei jedem Haushalt als eigene Karte mit
  Knöpfen („2× Spielzeug“, „2× Kleidung“). Ein Klick trägt die Teilnahme ein; jeder Haushalt kann
  je Aktion einmal teilnehmen. Danach zeigt die Karte „✓ Erhalten am …“. Zurücknehmen wie bei
  Abholungen nur mit Recht, sonst per Korrekturwunsch.
- **Auswertung:** Die Seite einer Aktion zeigt Teilnahmen und Stückzahlen je Auswahl, mit
  CSV-Export (nur Kundennummern, keine Namen).
- Teilnahmen hängen an der Kundennummer, überstehen den Import, stehen in der Auskunft nach
  Art. 15 und werden nach derselben Frist gelöscht wie Abholungen (ADR 0032).

## Zusätzliche Module

Programme, die nicht jede Tafel braucht, sind **zuschaltbare Module** (ADR 0049). Ein Admin
schaltet sie unter „Einstellungen → Tafel → Tafel und Module → Zusätzliche Module“ ein. Ausgeschaltete Module
erscheinen nirgends (kein Menü, keine Seiten, keine Rechte, keine Hilfe); ihre Daten bleiben
erhalten. Welche bisherigen Zusatzprogramme als Module kommen, steht in `docs/altprogramme.md`.

### Aufruf (Monitor, Handy, Kiosk)

Ruft die Kundinnen und Kunden im Wartebereich der Reihe nach auf (ADR 0050). Die Kundennummern
kommen direkt aus dem Kundenstamm, ein Download von Listen entfällt.

- **Reihenfolge:** alle aktiven Haushalte der Kundengruppen, die heute an der Ausgabestelle dran
  sind, Gruppe für Gruppe nach Uhrzeit, in der Gruppe zufällig gemischt. Haushalte mit Vorrang
  (ein Ja/Nein-Zusatzfeld, z. B. „Schwerbehindert“) zuerst.
- **Immer aktuell:** Neue Haushalte werden während des Tages fair einsortiert, entfernte fallen
  heraus. Wer heute schon am Einlass war (Abholung gebucht, z. B. mit Ausnahme vorgezogen),
  verschwindet aus der Warteschlange.
- **Steuern** (Recht „Kunden aufrufen“, Vorgabe Büro und Ausgabe): Menü
  „Kundennummernanzeige“ (öffnet einen neuen Tab) am PC oder die Handy-Steuerung. Weiter, Zurück, Abfrage einer Nummer und „zu spät
  gekommen“ (so viele wartende Plätze nach hinten wie eingestellt). Reihenfolge des Tages als CSV.
- **Geräte im Wartebereich:** Monitor (Nummern, Infos im Wechsel, Ton, Layout per Zahnrad),
  Nummern-Anzeige, Kiosk (Karte scannen, Antwort auf Deutsch und in der Sprache zur
  Staatsangehörigkeit) und Abfrage. Sie brauchen keine Anmeldung, sondern den geheimen Link aus
  „Einstellungen → Aufruf, Monitor und Kiosk“; „Neue Links erzeugen“ sperrt alte Links.
- **Am Einlass:** Die Einlass-Karte zeigt beim Scannen, ob und wann die Nummer aufgerufen
  wurde, „Zu spät“ (ab einstellbarer Minutenzahl nach dem Aufruf, Vorgabe 15) oder wie viele
  Nummern noch davor sind.
- **Einstellungen je Ausgabestelle:** Nummern je Aufruf (Vorgabe 3), Vorrang-Feld und Symbol,
  schon Eingelassene herausnehmen, Plätze für zu spät Gekommene, „zu spät“ am Einlass nach
  Minuten, Infos ein/aus, Probelauf als anderer Wochentag. **Infos:** Text, Bild, PDF oder Webseite mit Anzeigedauer, für alle oder
  bestimmte Ausgabestellen.
- Die Geräte zeigen nur Kundennummern. Die Reihenfolge eines Tages wird nach vier Wochen
  gelöscht.

### Warteliste mit Einladungen

Ersetzt das bisherige Neuanmeldungs-Programm (ADR 0051) und arbeitet direkt mit den Anträgen.

- **Status** je Antrag: neu → wartend → eingeladen (mit Termin) → erschienen oder entschuldigt;
  „Wartezeit bis“ ein Datum; ohne Rückmeldung nach einstellbaren Tagen „Streichen möglich“ oder
  direkt gestrichen; aufgenommen, sobald der Aufnahme-Assistent den Antrag übernommen hat.
- **Einladen:** Anträge auswählen (Filter nach Status, Art, Termin, Staatsangehörigkeit „nur“ oder
  „nicht“), Termin wählen oder neu anlegen. Einladung per Mail mit eigenen Texten und
  Platzhaltern; ohne E-Mail-Adresse nur eintragen (anrufen oder Brief).
- **Termine:** Liste der Eingeladenen, Druckliste (PDF), Status für mehrere setzen, **Absagen**
  per Mail (danach wieder „wartend“).
- **Abgleich mit dem Kundenstamm:** ähnliche Haushalte mit Hinweis, ob der Ausweis noch gilt oder
  die Sperrzeit nach Ablauf läuft (Monate, Altersgrenze und Ausnahme-Zusatzfeld einstellbar).
- **Doppelte Anträge** erkennen und mit Vermerk streichen; **Streichungsliste** (PDF), nach
  einstellbaren Tagen gelöscht.
- Rechte „Warteliste ansehen“ und „Einladen, absagen …“ (Vorgabe Büro), Einstellungen unter
  „Einstellungen → Kunden → Warteliste und Einladungen“. Einladungen stehen in der Auskunft zum
  Antrag.

### Wochenübersicht der Ausgabestellen

Ersetzt die bisherige „Ausgabestellen-Übersicht“ (ADR 0054) und rechnet direkt mit dem
Kundenstamm, ohne Import aus anderen Programmen.

- Je Wochentag und Ausgabestelle: **Soll Haushalte** („Maximum“ der Kundengruppen), **Ist
  Haushalte** (aktiv), Erwachsene, Kinder, Gesamt; Tagessummen und „GESAMT ALLE PERSONEN“. Alle
  Kundengruppen einer Ausgabestelle an einem Tag ergeben eine Zeile; eine Gruppe zählt an jedem
  ihrer Wochentage.
- **Selbstabholer** (Einrichtungen mit Tagen und Personenzahl) zählen nur zu „alle Personen“.
- Wahlweise die **Abholungen einer Kalenderwoche** je Tag und Ausgabestelle aus dem Einlass.
- Druck als PDF im Hochformat (je Tag) oder Querformat (alles auf einem Blatt wie die bisherige
  Excel-Liste). Rechte „Wochenübersicht ansehen“ und „… pflegen“ (Vorgabe Büro).

### Abrechnung der Ausgabestellen

Jede Ausgabestelle macht ihre Monatsabrechnung in bintafeln (ADR 0060), Menü „Abrechnung“.

- **Einnahmen** automatisch aus der Kasse am Einlass der Ausgabestelle: bar gezahlte Beiträge und
  Einzahlungen; Guthaben und Angeschriebenes zur Information.
- **Ausgaben** trägt die Ausgabestelle selbst ein (Datum, Betrag, Art, bezahlt an, Anmerkung), mit
  **Foto der Quittung** direkt aus der Handy- oder Tablet-Kamera oder als Datei (verschlüsselt
  gespeichert).
- **Einreichen** hält die Einnahmen fest und sperrt die Ausgaben; das Büro **bestätigt** oder
  **gibt zurück** (mit Grund). Übersicht aller Ausgabestellen je Monat mit Saldo, **Quittungen als
  ZIP** (alle Ausgabestellen fürs Büro; je Abrechnung auch für die Ausgabestelle selbst), jede
  Quittung einzeln zum Herunterladen, jede Abrechnung als **PDF**.
- Rechte „Abrechnung der eigenen Ausgabestelle führen“ (Vorgabe Ausgabe und Büro, nur für die
  zugeordneten Ausgabestellen) und „Abrechnungen aller Ausgabestellen prüfen“ (Vorgabe Büro).
  Arten der Ausgaben und Aufbewahrung (Vorgabe 5 Jahre) unter „Einstellungen → Ausgabe →
  Abrechnung“.

### Listen

Zuschaltbares Modul „Listen“ (ADR 0063): fertige Listen zum Kundenstamm, jede mit Filtern,
wählbaren und sortierbaren Spalten, Gliederung mit Anzahl und Summen, Auswahlkästchen je Zeile
und Ausgabe als CSV (Excel) oder PDF (Auswahl oder alles; jeder Export im Zugriffsprotokoll).

- **Kunden:** Kundenliste einer Ausgabestelle, alle Kunden, nach Einkommensart, Bürgergeld,
  Rentnerinnen und Rentner, Ausweis läuft ab, lange nicht gekommen, neue Kunden, große Haushalte,
  Haushalte mit Kindern unter 6, ohne Kundengruppe, pausiert/gesperrt/beendet, Abholungen im
  Zeitraum, Anschriftenliste, offene Beträge (Kontostand im Minus).
- **Personen:** nach Staatsangehörigkeit, Kinder unter 6, Kinder und Jugendliche (Alter von–bis),
  Schulanfänger, Seniorinnen und Senioren, nach Altersgruppen, alle Personen.
- **Zählungen:** je Staatsangehörigkeit, je Altersgruppe, je Ausgabestelle, je Kundengruppe, je
  Einkommensart, nach Haushaltsgröße, neue Kunden je Monat.
- Nur Kunden der eigenen Ausgabestellen; Listen mit Staatsangehörigkeit oder Einkommensart nur
  mit „Stammdaten sehen“, Kontaktdaten und Kontostand nur mit den Rechten dazu.
- **Eigene Listen** speichern die Einstellungen unter einem Titel (privat oder für alle).
- Rechte „Listen ansehen, drucken und exportieren“ (Vorgabe Büro und Ausgabe) und „Eigene Listen
  für alle speichern“ (Büro). Neue Listen sind ein Eintrag in `apps/listen/katalog.py`.

### Links auf der Startseite

Ersetzt die bisherige „App-Übersicht“ (ADR 0057): Kacheln mit Symbol, Titel, Untertitel,
Beschreibung und Adresse unter der Begrüßung, in Gruppen geordnet, auf Wunsch mit rotem
Warnhinweis. „Sichtbar für“ zeigt eine Kachel nur Personen mit einem bestimmten Recht (z. B.
Serververwaltung nur für Admins). Pflege unter „Einstellungen → Tafel → Links auf der Startseite“
(Recht „Links auf der Startseite pflegen“, Vorgabe nur Admin). Nur http(s)-Adressen und Pfade in
bintafeln; die Suche findet die Links mit.

### Wetter in der Kopfzeile

Zeigt rechts in der Kopfzeile Außentemperatur und Wetter der Ausgabestelle, z. B. „☁️ 12 °C
bedeckt“ (ADR 0053). Ort ist die Ausgabestelle, der die angemeldete Person zugeordnet ist, sonst
die erste aktive mit PLZ oder Ort.

- Quelle: [Open-Meteo](https://open-meteo.com/) (kostenlos, ohne Schlüssel). Der **Server** fragt
  an, höchstens alle 30 Minuten je Ausgabestelle, und übermittelt nur PLZ und Ort. Der App-Container
  braucht dafür Zugang ins Internet (https); ohne ihn fehlt die Anzeige einfach.
- Die Anzeige wird nachgeladen; die Seiten werden dadurch nicht langsamer.

### Kopfzeile

Links Menü, Name der Tafel und Suche, daneben der Programmname (einstellbar an einer Stelle:
`bintafeln/programm.py`), rechts Beiträge der Module (Wetter) und „Abmelden“. Reicht der Platz
nicht, kürzt `static/js/kopfzeile.js` die Zeile nach und nach: Untertitel des Programms,
Wettertext, Programmname, Name der Tafel (wenn ein Logo da ist), das Wort „Menü“.

## Adressbuch

„Adressen → Adressbuch“ (Rechte „Adressbuch ansehen …“, „Adressen anlegen und bearbeiten“,
„Adressen löschen“, „Adressen importieren“; Büro hat alle außer Löschen) sammelt Spender, Märkte,
Lieferanten, Partner, Presse und Behörden. Es ist die Grundlage für Spenden, Mitglieder und
Serienbriefe (Modul 5, ADR 0044); Kunden stehen weiter im Kundenstamm.

- **Adresse**: Organisation (mit Ansprechperson) oder Person, Anschrift, Telefon, Mobil, E-Mail,
  Webseite, Kategorien (Mehrfachauswahl, gepflegt unter „Einstellungen → Adresskategorien“),
  Notiz.
- **Einwilligungen** jeweils mit Datum: Post, E-Mail, Name veröffentlichen.
- **Liste** mit Suche und Filtern, Export als CSV (Excel), **Auskunft** nach Art. 15 als PDF,
  jede Änderung im Änderungsprotokoll. Im Suchfeld oben mit dem Kürzel `ad`.
- **Import** aus CSV (Semikolon, UTF-8 oder Windows-1252): Prüfbericht, dann übernehmen. Nur neue
  Adressen werden angelegt; gleicher Name mit gleicher PLZ oder gleiche E-Mail gilt als
  vorhanden. Spalten: `art;organisation;ansprechperson;anrede;vorname;nachname;strasse;plz;ort;`
  `land;telefon;mobil;email;webseite;kategorien;notiz;einwilligung_post;einwilligung_email;`
  `veroeffentlichen` (alle freiwillig außer `organisation` oder `nachname`; Kategorien durch Komma
  getrennt, unbekannte werden angelegt; Daten als TT.MM.JJJJ). Der CSV-Export hat dieselben
  Spalten.

## Mitglieder

„Mitglieder“ (Rechte „Mitglieder und Beiträge ansehen …“ und „Mitglieder anlegen, bearbeiten
und löschen“; Büro hat beide) führt die Mitglieder des Trägervereins (ADR 0046). Jedes Mitglied
ist eine Adresse aus dem Adressbuch.

- **Mitglied**: fortlaufende Mitgliedsnummer (Vorschlag), Art (Auswahl: ordentlich, aktiv,
  Förder-, Ehrenmitglied, juristische Person), Eintritt, Austritt mit Grund, Jahresbeitrag,
  Zahlweise, Zahlungsart, optional verknüpftes Konto (zugleich Mitarbeiter/in), Notiz.
- **Beiträge**: Liste je Jahr mit Soll, gezahlt und offen, Filter „nur mit offenem Beitrag“,
  CSV-Export. Beitragszahlungen sind Spenden mit dem Häkchen „Mitgliedsbeitrag“ („Zahlung
  erfassen“ auf der Seite des Mitglieds belegt alles vor) und lassen sich daher auch mit
  Zuwendungsbestätigungen bestätigen.
- **Einstellungen → Mitglieder** (nur Admin): „Mitglieder zahlen Beiträge“ (Vorgabe aus, weil
  die meisten Tafeln keine Beiträge erheben), nächste Nummer; bei Beiträgen zusätzlich Vorgabe
  Jahresbeitrag und Beitrag im Ein-/Austrittsjahr anteilig oder voll. Ist „Mitglieder zahlen
  Beiträge“ aus, erscheint nirgends etwas zu Beiträgen: kein Jahresbeitrag im Formular, kein
  Soll/gezahlt/offen in Liste, Mitgliedsseite und CSV, kein Häkchen „Mitgliedsbeitrag“ bei
  Spenden, keine Beitrags-Platzhalter und kein Filter „offener Beitrag“ bei Serienbriefen.
  Bereits erfasste Werte bleiben gespeichert und erscheinen nach dem Einschalten wieder. Beim
  Update wird die Einstellung eingeschaltet, wenn schon Beiträge erfasst sind.
- Mitgliedschaft steht in der Auskunft der Adresse (und als Hinweis in der Auskunft eines
  verknüpften Kontos). SEPA-Lastschriften folgen später.

## Serienbriefe

„Serienbriefe“ (Recht „Serienbriefe und -mails …“, Büro; an Kunden zusätzlich „Serienbriefe
auch an Kunden“, nur Admin) schreibt viele Empfänger auf einmal an (ADR 0047).

- **Vorlagen** mit Betreff und Text, Platzhalter in geschweiften Klammern: `{anrede}`
  (automatisch „Sehr geehrte Frau …,“ usw.), `{name}`, `{vorname}`, `{nachname}`,
  `{organisation}`, `{mitgliedsnummer}`, `{jahresbeitrag}`, `{beitrag_offen}`,
  `{spendensumme}`, `{kundennummer}`, `{jahr}`, `{datum}`, `{tafel}`. Mitgeliefert: Dank für
  Spenden, Erinnerung Mitgliedsbeitrag, Einladung Mitgliederversammlung.
- **Empfänger**: Adressen nach Kategorie, Mitglieder (Arten, nur offener Beitrag), Spender eines
  Jahres (Mindestsumme), Kunden (aktive Haushalte, Kundengruppen). Für Adressen und Spender ist
  „nur mit Einwilligung“ (Post bzw. E-Mail) vorgewählt.
- **Vorschau** mit Empfängerliste, Übersprungenen (ohne Anschrift/E-Mail) und Beispielbrief.
- **Briefe** als ein PDF (Anschrift für Fensterumschlag DIN lang, Faltmarken) oder **E-Mails**
  einzeln über den eingerichteten Mailserver. Jeder Versand wird vermerkt und erscheint in der
  Auskunft der Empfänger.

## Spenden und Zuwendungsbestätigungen

„Spenden“ (Rechte „Spenden ansehen …“, „Spenden erfassen …“, „Zuwendungsbestätigungen ausstellen
und stornieren“; Büro hat alle drei) verwaltet Geld- und Sachspenden. Jede Spende gehört zu einer
Adresse im Adressbuch (ADR 0045).

- **Geldspende**: Datum, Betrag, Zahlungsweg (Auswahl), Mitgliedsbeitrag, Verzicht auf
  Erstattung von Aufwendungen. **Sachspende**: Bezeichnung, Menge und Einheit (Auswahl), Wert,
  Herkunft (Privat-/Betriebsvermögen), Unterlagen zur Wertermittlung.
- **Übersicht** je Jahr mit Summen, Geldspenden je Monat, Filter und CSV-Export; auf der Seite
  einer Adresse deren Spenden und Summen je Jahr.
- **Import** aus einer CSV-Datei (ADR 0055), z. B. dem Export eines Vereinsportals: Prüfbericht
  vorab, Spender über E-Mail oder Name+PLZ zugeordnet bzw. neu angelegt, eine **Belegnummer**
  verhindert doppelte Spenden bei erneutem Import. Spalten und Beispiel:
  [docs/beispiele/spenden/spenden.csv](docs/beispiele/spenden/spenden.csv).
- **Dankesbriefe** (ADR 0056) aus einer Serienbrief-Vorlage, getrennt für Einfach- und
  Mehrfachspender, mit Zuwendungsbestätigung aus bintafeln (fehlende werden ausgestellt) und/oder
  **hochgeladenen Belegen** aus einem anderen Programm (z. B. Vereinsportal; Zuordnung über die
  Belegnummer im Dateinamen oder von Hand). Ein PDF für den Druck oder E-Mails mit PDF-Anhang an
  Spender mit E-Mail-Einwilligung; danach gelten die Spenden als bedankt.
- **Zuwendungsbestätigungen** als PDF nach den amtlichen Mustern: Einzel-, Sammel- (mit Anlage)
  und Sachbestätigung, Betrag in Ziffern und Worten, fortlaufende Nummer. „Alle ausstellen“
  erstellt am Jahresende für alle Spender auf einmal. Jede Spende wird nur einmal bestätigt;
  Stornieren lässt die Nummer bestehen. Bestätigte Spenden sind nicht mehr änderbar, Adressen
  mit Spenden nicht löschbar.
- **Einrichten** (nur Admin) unter „Einstellungen → Spenden und Zuwendungsbestätigungen“: Name
  und Anschrift der Körperschaft, steuerbegünstigte Zwecke, Art des Bescheids
  (Freistellungsbescheid, Anlage zum KSt-Bescheid, Feststellung nach § 60a AO), Finanzamt,
  Steuernummer, Datum, Veranlagungszeitraum, Unterschrift, Startnummer. Ob die Angaben zur
  Tafel passen, bitte mit der Steuerberatung klären.

## Statistik

„Statistik“ im Menü (Recht „Statistik ansehen“, Vorgabe: Admin und Büro). Oben Zeitraum
(dieses/letztes Jahr, letzte 12 Monate, dieser/letzter Monat, letzte 30 Tage oder eigener
Zeitraum) und Ausgabestelle wählen.

- **Kennzahlen:** Abholungen, verschiedene Haushalte, erreichte Personen (Summe der
  Haushaltsgrößen je Abholung), Bareinnahmen, aktive Haushalte mit Personen, neue Kunden,
  eingegangene Anträge.
- **Diagramme:**
  - Abholungen je Monat (bis gut drei Monate je Woche, bis 31 Tage je Tag)
  - Abholungen je Ausgabestelle im Verlauf und insgesamt
  - Abholungen nach Wochentag und nach Uhrzeit
  - Bareinnahmen je Monat
  - neue Kunden und eingegangene Anträge
  - aktive Haushalte nach Größe, Personen nach Altersgruppe
  - Haushalte nach Status und Einkommensart
  - Auslastung der Kundengruppen
  - Sonderaktionen im Zeitraum
- **Spenden und Mitglieder** (nur ohne Auswahl einer Ausgabestelle, weil sie zum Verein gehören,
  und nur mit dem Recht „Spenden ansehen“ bzw. „Mitglieder ansehen“): Kennzahlen Geldspenden,
  Sachspenden, Mitglieder (und Mitgliedsbeiträge, wenn eingeschaltet); Diagramme Geldspenden im
  Verlauf (Tabelle mit Zahl der Sachspenden), Geldspenden nach Zweck, Eintritte und Austritte,
  Mitglieder nach Art.
- Zu jedem Diagramm gibt es die Zahlen als Tabelle und als **CSV-Datei**. Beim Überfahren mit
  der Maus zeigt jedes Diagramm die genauen Werte.
- Nur Summen, keine Personendaten. Wer einer Ausgabestelle zugeordnet ist, sieht nur deren Zahlen.
- Die Diagramme zeichnet bintafeln selbst (SVG), ohne fremde Dienste (ADR 0036).
- **Jahresbericht (PDF):** Auf der Statistik-Seite Jahr wählen, „Jahresbericht erstellen“. Das
  PDF enthält alle Kennzahlen und jeden Abschnitt als Tabelle, Abschnitte mit einer Zahlenreihe
  zusätzlich als Säulendiagramm; im laufenden Jahr bis heute. Mit gewählter Ausgabestelle nur
  deren Zahlen. Gut als Grundlage für Mitgliederversammlung, Vorstand oder Förderanträge.

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

## Datensicherung in der Oberfläche (Export und Zurücklesen)

„Einstellungen → Export und Zurücklesen“ (Rechte „Alle Daten exportieren“ und „Daten zurücklesen“,
Vorgabe: nur Admin). Ergänzt die tägliche Server-Sicherung (siehe „Betrieb“) um eine Datei, die
man selbst extern aufbewahrt.

- **Exportieren:** Bereiche wählen (Einstellungen und Listen; Kunden und Ausgabe; Anträge;
  Mitarbeitende, Rollen und Personal; Änderungsprotokoll; hochgeladene Dateien), ein Passwort
  festlegen (mindestens 10 Zeichen) und die Datei `bintafeln-export-….bintafeln`
  herunterladen. Sie ist mit dem Passwort verschlüsselt; ohne Passwort lässt sie sich nicht
  öffnen. Alle Bereiche zusammen ergeben eine vollständige Sicherung.
- **Zurücklesen:** Datei und Passwort wählen, „Prüfen“. Die Vorschau zeigt Herkunft (Tafel,
  Datum, Version; Warnung bei einer anderen Installation) und je Tabelle, wie viele Datensätze
  neu sind und wie viele überschrieben würden. Dann:
  - **Aktualisieren** (immer möglich, auch mit einer Teildatei): neue Datensätze hinzufügen,
    gleiche überschreiben, **nichts löschen**.
  - **Vollständig ersetzen** (nur mit einer vollständigen Exportdatei, nur mit einer
    Server-Sicherung von heute und ausdrücklicher Bestätigung): alle Daten dieser Installation
    durch die Datei ersetzen, z. B. beim Umzug auf einen neuen Server.
- Eine Datei aus einer neueren bintafeln-Version wird abgelehnt (erst aktualisieren). Fehlen
  Daten, auf die eine Teildatei verweist, wird nichts verändert und bintafeln sagt, welcher
  Bereich fehlt.
- Nicht enthalten: Zwei-Faktor-Geräte (nach einem Umzug neu einrichten). Das Passwort des
  Mailservers bleibt mit dem Schlüssel des alten Servers verschlüsselt und muss auf einem neuen
  Server neu eingegeben werden (ADR 0037).

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

Der Dienst `backup` sichert die Datenbank und die hochgeladenen Dateien nach den
**Sicherungsaufträgen**, die man in bintafeln unter „Einstellungen → Sicherungen“ einstellt
(siehe [Sicherungsaufträge](#sicherungsaufträge)). Die Sicherungen werden mit
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
`datenbank.dump.age`, `medien.tar.age` und `info.txt`. Ältere Stände löscht der Dienst nach der
Aufbewahrung des Auftrags.

### Sicherungsaufträge

Unter „Einstellungen → Sicherungen“ (Recht „Sicherungen starten, Sicherungsaufträge
einstellen“, Vorgabe nur Admin) gibt es:

- **„Jetzt sichern“** bei jedem Auftrag, immer möglich, auch bei ausgeschaltetem Zeitplan. Der
  Dienst startet die Sicherung innerhalb von etwa 15 Sekunden; die Seite zeigt Fortschritt und
  Ergebnis.
- **Beliebig viele Aufträge**, je Auftrag:
  - **Ziel**: der Sicherungsordner des Servers (`BINTAFELN_SICHERUNG_PFAD`) oder ein Ordner unter
    `/media` oder `/mnt`, also z. B. eine USB-Platte oder ein eingehängtes NAS. Der Dienst
    zeigt diese Ordner mit freiem Platz zur Auswahl; später angesteckte Platten erscheinen
    spätestens nach 30 Minuten (so oft startet sich der Dienst neu, wenn er nichts zu tun hat).
    Gesichert wird in einen Unterordner `bintafeln`.
  - **Wochentage und Uhrzeit**.
  - **Aufbewahrung**: höchstens so viele Stände und/oder so viele Tage. Die neueste Sicherung
    bleibt immer.
- **Übersicht** je Auftrag: letzte Sicherung, Ergebnis, Stände, freier Platz. Fehlgeschlagene
  Aufträge stehen auf der Startseite.

Der Auftrag „Tägliche Sicherung auf dem Server“ ist immer da (ausschaltbar, nicht löschbar):
`./betrieb sichern`, das Update und `./betrieb wiederherstellen` arbeiten mit seinem Ordner.
`BINTAFELN_SICHERUNG_UHRZEIT` und `BINTAFELN_SICHERUNG_ANZAHL` in `.env` gelten nur für seine
erste Einrichtung. Stände von einem externen Ziel zum Wiederherstellen in den Sicherungsordner
kopieren (ADR 0042).

Externe Platte einhängen (Beispiel, als root auf dem Server):

```bash
mkdir -p /mnt/usb-sicherung
mount /dev/sdb1 /mnt/usb-sicherung     # dauerhaft: Eintrag in /etc/fstab
```

Unter Debian mit Desktop hängt sich eine angesteckte Platte oft selbst unter `/media/…` ein.

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

### Musterdaten für eine Test-Installation

Zum Ausprobieren füllt ein Befehl die Installation mit **erfundenen** Daten:

```bash
./betrieb sichern                                   # vorher sichern!
docker compose exec app python manage.py musterdaten --ja --passwort 'Ein-Test-Passwort'
```

Er **ersetzt vollständig** Kundenstamm (150 Haushalte mit Personen, Abholungen, Kontobuchungen,
Notizen, Anmerkungen, Sperren), Anträge, Adressen, Spenden und Mitglieder und legt
Muster-Mitarbeitende `muster-…` in allen Rollen und Kombinationen an (auch einer Ausgabestelle
zugeordnet, auch gesperrt), mit Stammdaten, Verträgen, Arbeitszeiten und Urlaub. Unverändert
bleiben Tafel-Einstellungen (Name, Logo, Anschrift), Ausgabestellen, Kundengruppen, das
Antragsformular mit seinen Texten und alle Konten, die nicht mit `muster-` beginnen. Erneut
ausgeführt, ersetzt er die Musterdaten wieder. Nie auf einer Installation mit echten Daten!

### Aktualisieren

**Am einfachsten in bintafeln selbst:** „Einstellungen → Update“ (Recht „Programm aktualisieren“,
Vorgabe nur Admin). Die Seite zeigt die installierte Version, die verfügbaren Versionen mit ihren
Änderungen und startet das Update auf Knopfdruck, auf Wunsch auch zurück auf eine ältere Version.
Dahinter läuft genau `./betrieb update VERSION` (also mit Sicherung vorher). bintafeln ist dabei
ein bis zwei Minuten nicht erreichbar; danach zeigt die Seite das Ergebnis und das Protokoll.

Das erledigt der Dienst `updater` (ADR 0043). Er ist als einziger Dienst mit Docker verbunden,
von außen nicht erreichbar und nimmt von bintafeln nur den Namen einer vorhandenen Version an.
Er sucht alle 10 Minuten nach neuen Versionen (`git fetch`); solange das Repository privat ist,
braucht der Server dafür Zugangsdaten für GitHub. `git fetch` und das Update laufen dabei als
die Person, der der Projektordner gehört, mit deren Konto und Home-Ordner (nur lesend): Es gelten
also dieselben SSH-Schlüssel, `known_hosts` und git-Einstellungen wie beim `./betrieb update`
auf der Kommandozeile. **Einmalig** kommt der Dienst mit dem ersten
`./betrieb update` auf der Kommandozeile dazu; danach geht jedes Update in der Oberfläche.

Auf der Kommandozeile:

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

Nach dem Neustart räumt das Update die durch den Neubau ersetzten Images auf
(`docker image prune`), damit die Platte nicht nach und nach volläuft. Alte Images braucht man
nicht: Jede ältere Version baut `./betrieb update VERSION` bei Bedarf neu aus dem Repository.

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

Ein Test geht alle Adressen des Programms durch und prüft, dass ohne Anmeldung nur die bewusst
öffentlichen Seiten erreichbar sind und ein Konto ohne Rechte überall gesperrt ist
(`tests/test_zugriffsschutz.py`, ADR 0065). Neue öffentliche Seiten dort eintragen.

GitHub Actions führt bei jedem Pull Request ruff, shellcheck und pytest aus und spielt mit
`tests/sicherung_e2e.sh` eine echte Sicherung und Wiederherstellung im Docker-Aufbau durch.
Dieses Skript überschreibt `.env`, lokal also nur in einer Wegwerf-Kopie starten.

### Verzeichnisstruktur

```
bintafeln/          Django-Projekt (Einstellungen, URLs)
apps/core/          Tafel-Einstellungen, Einrichtung, Startseite, Änderungsprotokoll
apps/konten/        Benutzer, Rollen, Anmeldung, Zwei-Faktor
apps/kunden/        Kundenstamm: Haushalte, Personen, Zusatzfelder, Einstellungen
apps/aufruf/        Modul Aufruf (Monitor, Handy, Kiosk); Module beschreibt apps/core/module.py
apps/warteliste/    Modul Warteliste (Einladungen zu Terminen, Streichungen)
apps/wochenuebersicht/ Modul Wochenübersicht (Soll/Ist der Ausgabestellen je Wochentag)
apps/links/         Modul Links (Kacheln auf der Startseite)
apps/abrechnung/    Modul Abrechnung (Monatsabrechnung je Ausgabestelle mit Quittungen)
apps/listen/        Modul Listen (Katalog fertiger Listen, Spalten, Gliederung, Export)
apps/wetter/        Modul Wetter (Außentemperatur der Ausgabestelle in der Kopfzeile)
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
