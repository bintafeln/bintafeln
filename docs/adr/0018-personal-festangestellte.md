# 0018: Personal für Festangestellte

- Status: Angenommen
- Datum: 2026-10-24
- Ergänzt: ADR 0015, ADR 0017

## Problem

Für Festangestellte braucht die Tafel Angaben, die ein Arbeitgeber führen muss:
Arbeitsvertrag mit Stundenlohn, Urlaub mit Übertrag und Verfall, Krankheitszeiten und ein
Stundenkonto. Diese Daten sind besonders vertraulich. Krankheit ist eine Gesundheitsangabe im
Sinne von Art. 9 DSGVO.

## Entscheidung

- Neue App `personal`, sichtbar nur für **Admin** und die neue Rolle **Personal**. Diese Rolle
  vergibt nur ein Admin, und für sie ist die Zwei-Faktor-Anmeldung standardmäßig Pflicht.
- **Arbeitsverträge** mit Beginn, Ende, Tätigkeit, Wochenstunden, Urlaubstagen pro Jahr und
  Stundenlohn. Das Vertragsdokument wird verschlüsselt gespeichert, jeder Abruf protokolliert.
  Eine Vertragsänderung ist ein neuer Vertrag ab einem Datum.
- **Abwesenheiten** sind „Urlaub“ oder „krank“ mit Zeitraum und Arbeitstagen. Ohne Angabe gelten
  Montag bis Freitag; Feiertage und halbe Tage trägt man selbst ein. Bei Krankheit wird nur
  festgehalten, ob eine Arbeitsunfähigkeitsbescheinigung vorliegt, **nie eine Diagnose**.
- **Urlaub:**
  - Anspruch anteilig je vollem Vertragsmonat; ab einem halben Tag wird aufgerundet
    (§ 5 BUrlG).
  - Der Resturlaub wird **automatisch übertragen** und verfällt zum einstellbaren Datum
    (Vorgabe 31.03.). Das Datum ist je Person und Jahr änderbar, ebenso der Anspruch.
  - Genommener Urlaub verbraucht zuerst den Übertrag, soweit er bis zum Verfallsdatum beginnt.
- **Stundenkonto:**
  - Soll = Wochenstunden ÷ 5 je Werktag.
  - Ist-Stunden werden von Hand eingetragen, bis die geplante Arbeitszeiterfassung sie liefert.
  - Urlaub und Krankheit werden mit dem Tagessoll gutgeschrieben.
  - Der Saldo läuft über die Jahre weiter.
- **Löschfrist:** Mit den Stammdaten (ADR 0017) werden Verträge, Dokumente, Abwesenheiten,
  Urlaubsjahre und Stunden gelöscht, auch ihre Einträge im Änderungsprotokoll.

## Begründung

Die Berechnungen folgen dem Bundesurlaubsgesetz, bleiben aber einfach und nachvollziehbar.
Abweichungen (Feiertage, Teilzeit an bestimmten Tagen, Sonderregeln im Vertrag) lassen sich
von Hand eintragen. Lohnabrechnung gehört nicht zu bintafeln; der Stundenlohn dient nur der
Übersicht. Wie lange Personalunterlagen aufbewahrt werden müssen, kann von der Löschfrist
abweichen. Die Tafel stellt sie unter „Fristen einstellen“ passend ein.
