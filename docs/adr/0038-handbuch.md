# 0038: Handbuch im Programm, nach Rechten gefiltert

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Mitarbeitende brauchen eine ausführliche Anleitung direkt im Programm. Wer am Einlass mit wenigen
Rechten arbeitet, soll nicht durch Kapitel über Mitarbeitende, Personal oder Einstellungen
blättern müssen.

## Entscheidung

- Seite „Hilfe“ für alle angemeldeten Konten. Kapitel sind Templates (`templates/hilfe/`), ihr
  Verzeichnis mit Teil und Rechten steht in `apps/core/hilfe.py`.
- Ein Kapitel erscheint, wenn das Konto mindestens eines seiner Rechte hat; Absätze innerhalb
  eines Kapitels richten sich mit `{% if "recht" in rechte %}` ebenfalls nach den Rechten.
- Alle sichtbaren Kapitel stehen auf einer Seite mit Inhaltsverzeichnis, damit die Suche des
  Browsers alles findet und man sie drucken kann.
- Neue oder geänderte Funktionen aktualisieren das Handbuch im selben PR; ein Test prüft, dass
  jedes Kapitel eine Vorlage hat und nur bekannte Rechte nennt.

## Begründung

Templates statt einer Markdown-Bibliothek: keine neue Abhängigkeit, Links und Bedingungen direkt
nutzbar. Die Bindung an Rechte nutzt dieselbe Grundlage wie Menü und Seiten (ADR 0033).
