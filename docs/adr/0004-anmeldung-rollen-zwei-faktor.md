# 0004: Anmeldung, Rollen und Zwei-Faktor

- Status: Angenommen
- Datum: 2026-10-23

## Problem

Verschiedene Personen einer Tafel brauchen unterschiedliche Rechte. Kundendaten sind besonders
schützenswert, ein gestohlenes Passwort allein darf nicht reichen.

## Entscheidung

- **Eigenes Benutzermodell** `konten.Benutzer` von Anfang an.
- **Vier Rollen als Django-Gruppen:** Admin, Büro, Ausgabe, Kiosk. Eine Datenmigration legt sie
  an. Ansichten werden mit `@rolle_erforderlich(...)` geschützt.
- **Zwei-Faktor mit django-otp (TOTP, Authenticator-App).** Hat ein Konto ein bestätigtes Gerät,
  ist der Code bei der Anmeldung Pflicht. Auch die Django-Verwaltung (`/admin/`) nutzt diese
  Anmeldung.
- **Den ersten Admin legt die Einrichtungsseite im Browser an**, solange es keinen gibt. Danach
  ist sie gesperrt.

## Begründung

- Ein eigenes Benutzermodell lässt sich später nur mit großem Aufwand einführen. Django empfiehlt
  es deshalb für neue Projekte.
- Gruppen sind Django-Standard, in der Verwaltung pflegbar und reichen für rollenbasierte
  Rechte je Modul.
- TOTP funktioniert mit jeder gängigen Authenticator-App, ohne SMS und ohne externen Dienst.
- Die Einrichtungsseite vermeidet Standardpasswörter und Kommandozeilenbefehle bei der
  Installation.

## Folgen

- Noch offen: Einrichtung des Zwei-Faktor-Geräts durch die Person selbst (QR-Code) und
  Zwei-Faktor-Pflicht für ausgewählte Rollen.
