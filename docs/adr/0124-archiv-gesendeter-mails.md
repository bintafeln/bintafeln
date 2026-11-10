# ADR 0124: Archiv der gesendeten Mails

## Problem

bintafeln verschickt Einladungen, Bestätigungen, Dankesbriefe, Serienbriefe und
Benachrichtigungen, hielt aber nirgends fest, was wann an wen ging. Bei Rückfragen („Ich habe
keine Einladung bekommen“) ließ sich nichts nachsehen, und fehlgeschlagene Mails fielen nur im
Augenblick des Sendens auf.

## Entscheidung

- **Eine Stelle hält fest:** `apps.core.mail.senden()` legt nach jedem Versuch einen
  `GesendeteMail`-Eintrag an – auch bei einem Fehlschlag, dann mit dem verständlichen Grund. Die
  Aufrufer nennen mit `art=` (Schlüssel aus `mail.ARTEN`), wofür die Mail ist.
- **Sparsam gespeichert:** Empfänger, Betreff, Text; Anhänge nur mit Name, Größe und Typ. Mails
  mit Zugangsdaten (`vertraulich=True`: Link zum neuen Passwort, Freigabe des Zugangs) ohne
  Inhalt.
- **Frist:** `MailEinstellungen.archiv_tage` (Vorgabe 90, 0 = kein Archiv);
  `mail.fristen_anwenden()` löscht täglich mit den übrigen Fristen, direkt und ohne Papierkorb.
- **Zugriff:** eigenes Recht `system.mails`, in der Vorgabe nur Admin. Jeder Abruf einer Mail
  steht als Zugriff im Änderungsprotokoll. Das Modell selbst ist bewusst **nicht** bei
  django-auditlog registriert: Sonst läge der Inhalt ein zweites Mal im Protokoll und überlebte
  die Frist.
- **Nicht in der Datensicherung zum Herunterladen** (`AUSGENOMMEN`): vorübergehende Daten.
- In der Auskunft nach Art. 15 erscheinen die archivierten Mails an die Adresse der Person
  (Datum und Betreff).

## Begründung

Alle Mails laufen schon über eine Funktion; dort festzuhalten kostet die Aufrufer nur ein Wort
und kann nicht vergessen werden. Anhänge (Zuwendungsbestätigungen, Listen mit Kundendaten) würden
das Archiv groß und heikel machen und lassen sich neu erzeugen. Ein Link zum Setzen des Passworts
wäre im Archiv ein Schlüssel zu fremden Konten.
