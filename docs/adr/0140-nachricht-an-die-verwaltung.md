# 0140 – Nachricht einer Ausgabestelle an die Verwaltung ohne Kunden

## Problem

Ausgabestellen konnten der Verwaltung bisher nur zu einem Kunden schreiben (ADR 0062). Für alles
andere – Kühlschrank defekt, Schlüssel fehlt, Frage zum Ablauf – blieb nur eine Mail aus dem
eigenen Postfach. Viele Ausgabestellen arbeiten aber mit einem gemeinsamen Stellenkonto ohne
eigene E-Mail, und die Antwort landete irgendwo, nur nicht an der Ausgabestelle.

## Entscheidung

- Auf der Startseite steht für alle mit dem Recht `einlass.nutzen` der Knopf „✉ Nachricht an die
  Verwaltung“. Die Seite nimmt Betreff und Text auf; Absender ist die gewählte Ausgabestelle
  (ADR 0067) und das Konto. Ohne gewählte Ausgabestelle kann man nicht schreiben.
- Gespeichert wird `StellenNachricht` (App `kunden`, neben `Nachricht`), Logik in
  `apps/kunden/an_verwaltung.py`.
- Benachrichtigt wird über die Art `nachricht_verwaltung` (ADR 0086, 0125). Vorgabe ist die
  E-Mail der Tafel aus den Tafel-Einstellungen (keine festen Adressen im Code). Unter
  „Mail-Empfänger“ lassen sich stattdessen oder zusätzlich Personen mit dem Recht
  `kunden.nachrichten` wählen. Die Mail enthält einen Link zum Antworten.
- Die Verwaltung (Recht `kunden.nachrichten`) liest und beantwortet die Nachrichten auf der
  bekannten Seite „Nachrichten der Ausgabestellen“ unter dem Reiter „ohne Kunde“, oder hakt sie
  ohne Antwort ab.
- Die Antwort steht auf der Startseite der Ausgabestelle, bis dort jemand „gelesen“ klickt; auf
  der Schreibseite stehen die letzten Nachrichten der Ausgabestelle mit Antwort.
- Erledigte werden nach 90 Tagen gelöscht (wie ADR 0062). Eigene Nachrichten stehen in der
  Auskunft nach Art. 15 für Mitarbeitende.

## Begründung

Die Antwort im Programm erreicht auch Stellenkonten ohne E-Mail und alle, die an der
Ausgabestelle arbeiten, nicht nur die Person, die geschrieben hat. Die Mail an die Tafel sorgt
dafür, dass die Nachricht in der Verwaltung nicht übersehen wird; jede Tafel stellt selbst ein,
wer sie bekommt. Eine eigene Seite mit Reiter statt einer zweiten Postliste hält alles, was die
Ausgabestellen der Verwaltung schreiben, an einem Ort.
