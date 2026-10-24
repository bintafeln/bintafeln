# 0016: Mailserver in der Oberfläche, Einladungen per Link

- Status: Angenommen
- Datum: 2026-10-24
- Ergänzt: ADR 0003, ADR 0015

## Problem

bintafeln soll Mails versenden, zunächst Einladungen und Links zum Zurücksetzen von Passwörtern,
später weitere. Jede Tafel hat einen anderen Mail-Anbieter. Das Passwort des Mailservers ist ein
Geheimnis und gehört nicht im Klartext in die Datenbank oder in Sicherungen.

## Entscheidung

- Der Admin richtet den Mailserver unter „Einstellungen → E-Mail“ ein: Server, Port,
  Verschlüsselung, Benutzer, Passwort und Absender. Eine Testmail prüft die Angaben.
- Das Passwort wird mit **Fernet** (Bibliothek `cryptography`) **verschlüsselt** gespeichert.
  Der Schlüssel wird per HKDF aus `DJANGO_SECRET_KEY` abgeleitet, also aus `.env`; es gibt keine
  weitere Einstellung. Nach einer Änderung des geheimen Schlüssels muss das Passwort neu
  eingegeben werden; die Seite weist darauf hin.
- Einladungen und „Passwort vergessen“ schicken **nie ein Passwort**, sondern einen
  **einmaligen Link**: Djangos Token zum Zurücksetzen, gültig 3 Tage
  (`PASSWORD_RESET_TIMEOUT`). Er wird ungültig, sobald das Passwort gesetzt wurde.
- „Passwort vergessen?“ erscheint nur, wenn ein Mailserver eingerichtet ist. Die Antwort verrät
  nie, ob es ein Konto gibt. Je Konto geht höchstens eine Mail in fünf Minuten raus. Die
  Zwei-Faktor-Anmeldung bleibt davon unberührt.
- Scheitert eine Einladung, zeigt bintafeln stattdessen ein Startpasswort an.

## Begründung

Die Eingabe in der Oberfläche passt zum Wunsch, dass jede Tafel ihren Mailserver selbst
einträgt. Durch die Verschlüsselung mit einem Schlüssel außerhalb der Datenbank bleibt das
Passwort auch in Sicherungen geschützt. Links statt Passwörter verhindern, dass ein
mitgelesenes Postfach dauerhaft Zugang verschafft.
