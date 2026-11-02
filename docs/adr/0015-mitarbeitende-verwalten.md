# 0015: Mitarbeitende in bintafeln verwalten

- Status: Angenommen
- Datum: 2026-10-24
- Ergänzt: ADR 0004, ADR 0009

## Problem

Konten wurden bisher über die technische Django-Verwaltung angelegt. Das ist für Tafeln zu
umständlich und zeigt mehr, als nötig ist. Außerdem muss auch nach Jahren nachvollziehbar
bleiben, wer wann dabei war und was eingetragen hat.

## Entscheidung

- Eigene Seite „Mitarbeitende“ für **Admin**. Ein Admin kann sie in den Tafel-Einstellungen für
  das **Büro** freischalten. Das Büro bearbeitet dann keine Admin-Konten und vergibt keine
  Admin-Rolle.
- **Startpasswort:** bintafeln erzeugt es zufällig (ohne verwechselbare Zeichen) und zeigt es
  einmal an. Bei der ersten Anmeldung muss ein eigenes Passwort gewählt werden, danach
  gegebenenfalls die Zwei-Faktor-Anmeldung. Eine Einladung per Mail folgt, sobald bintafeln
  Mails versenden kann.
- **Sperren statt löschen:** Gesperrte Konten können sich nicht anmelden, eine laufende
  Sitzung endet sofort. Sie stehen in einer **Archivliste** mit „dabei seit“, „gesperrt am“
  und „gesperrt von“. Sie lassen sich wieder freischalten.
- **Ausnahme – endgültig löschen:** Ein **gesperrtes** (archiviertes) Konto kann mit dem Recht
  „Gesperrte Mitarbeitende endgültig löschen“ (Vorgabe: nur Admin) ganz entfernt werden – samt
  Stammdaten, verknüpfter Adresse und allem, was am Konto hängt (Verträge, Stunden, Urlaub,
  Abwesenheiten, Zeitbuchungen, PIN, Import-Vorlagen). Es geht in den **Papierkorb** (ADR 0073)
  und lässt sich dort eine Weile wiederherstellen. Wo die Person nur als „eingetragen/gesehen
  von“ an fremden Vorgängen (Abholungen, Notizen, Tickets, Warteliste) steht, wird sie dort auf
  leer gesetzt, die Vorgänge bleiben. Hat die Person **Spenden oder eine Mitgliedschaft**, wird
  das Löschen abgelehnt – das ist zuerst zu klären. Aktive Konten müssen erst gesperrt werden;
  niemand löscht sich selbst, Admin-Konten nur ein Admin.
- **Schutzregeln:** Niemand sperrt sich selbst oder nimmt sich selbst die Admin-Rolle. Da
  Admin-Konten nur Admins ändern, bleibt so immer mindestens ein aktiver Admin.
- Neue Rollen **Fahrer** und **Beifahrer**, mit eigener Zwei-Faktor-Einstellung. Sie haben noch
  keine eigenen Ansichten.
- **Beschäftigung:** ehrenamtlich oder fest angestellt. Das ist die Grundlage für ein späteres
  Arbeitsstundenkonto.

## Begründung

Ohne Mailserver ist das einmal angezeigte Startpasswort mit Änderungspflicht der sicherste
einfache Weg. Gesperrte statt gelöschter Konten halten Änderungsprotokoll, Abholungen und
Buchungen dauerhaft zuordenbar. Die Archivliste enthält nur Name, Benutzername, Rollen und
Zeiträume. Wie lange sie aufbewahrt wird, legt die Tafel in ihrem Löschkonzept fest.

Das endgültige Löschen ist die Umsetzung desselben Löschkonzepts und der Datensparsamkeit: Wer
nach Ablauf der eigenen Aufbewahrungsfrist nicht mehr gebraucht wird, lässt sich bewusst und nur
vom Admin entfernen. Der Papierkorb schützt vor Versehen; die Sperre vorab verhindert, dass im
laufenden Betrieb aus Versehen gelöscht wird; die Schutzregel bei Spenden und Mitgliedschaft hält
Daten, die aus steuer- oder vereinsrechtlichen Gründen bleiben müssen.
