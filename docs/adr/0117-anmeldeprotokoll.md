# 0117: Anmeldeprotokoll (IP-Adresse und Browser bei der Anmeldung)

- Status: Angenommen
- Datum: 2026-11-08

## Problem

Bisher hielt bintafeln bei der Anmeldung nur den Zeitpunkt der letzten erfolgreichen Anmeldung
(`last_login`) fest. Für die IT-Sicherheit ist aber interessant, **wer sich wann von wo** angemeldet
hat und ob es **Fehlversuche** gab (falsches Passwort, falscher Zwei-Faktor-Code) – etwa um zu
erkennen, dass sich jemand von einem ungewohnten Ort aus anzumelden versucht. Eine IP-Adresse ist
jedoch ein personenbezogenes Datum und darf nicht unbegrenzt gespeichert werden; der Rechnername des
Geräts ist einem Webserver grundsätzlich nicht zugänglich.

## Entscheidung

- Ein **Anmeldeprotokoll** (`konten.AnmeldeProtokoll`) hält erfolgreiche Anmeldungen **und**
  Fehlversuche fest – jeweils mit Zeitpunkt, Benutzername (und, falls bekannt, dem Konto),
  **IP-Adresse** und **Browser/System** (User-Agent). Den tatsächlichen Rechnernamen kann ein Server
  nicht sehen; deshalb wird statt eines „Rechnernamens“ die vom Browser gemeldete Kennung gespeichert.
- Die **echte Besucher-IP** steht hinter dem Caddy-Proxy im ersten Eintrag von `X-Forwarded-For`
  (wie bereits beim Antragsformular und der Wartezeit-Seite).
- **Woher die Einträge kommen:** Erfolg und ein falscher Zwei-Faktor-Code tragen die Anmelde-Ansichten
  selbst ein (`apps/konten/anmeldeprotokoll.eintragen`); ein falsches Passwort fängt das Signal
  `user_login_failed` ab. So wird ein `force_login` in Tests oder im Code nicht mitprotokolliert.
- **Datenschutz:** Das Protokoll ist nur mit dem Recht `protokoll.sehen` einsehbar (wie das
  Änderungsprotokoll), steht in der Auskunft (Art. 15) der betroffenen Person und wird nach einer je
  Tafel einstellbaren Frist (`AnmeldeEinstellungen.protokoll_tage`, Vorgabe 90 Tage) über
  `anmeldeprotokoll.fristen_anwenden()` automatisch gelöscht. „Aus“ protokolliert nichts und löscht
  die vorhandenen Einträge.
- Das Anmeldeprotokoll wird selbst **nicht** bei django-auditlog registriert (es ist kein
  Stammdatensatz, sondern das Protokoll).

## Begründung

Die Sicherheit profitiert davon, Anmeldungen und Angriffsversuche nachvollziehen zu können, ohne
dauerhaft personenbezogene Daten zu horten: einstellbare Frist, Auskunft und Abschaltbarkeit halten
die Datensparsamkeit ein. Signale plus gezielte Einträge in den Ansichten erfassen alle Fälle der
zweistufigen Anmeldung, ohne programmatische Logins (Tests, Automatik) zu verfälschen.
