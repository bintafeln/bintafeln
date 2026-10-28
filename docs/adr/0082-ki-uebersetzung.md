# 0082: KI-Übersetzung der eigenen Antragstexte

- Status: Angenommen
- Datum: 2026-10-28

## Problem

Das Antragsformular gibt es in 29 Sprachen. Die mitgelieferten Texte sind übersetzt, die eigenen
Texte einer Tafel (Einleitung, Hinweis zu den Nachweisen, Seite nach dem Absenden, Antwortmail)
aber nur auf Deutsch; in allen anderen Sprachen erscheint dann der deutsche Text. Sie von Hand in
28 Sprachen zu übersetzen, schafft keine Tafel.

## Entscheidung

- Auf der Seite „Texte: Deutsch“ übersetzt ein Knopf die gespeicherten deutschen Texte mit Claude
  (Anthropic, Modell `claude-opus-5-5`, geringer Aufwand) in alle anderen Sprachen und speichert sie
  als Texte der jeweiligen Sprache (`apps/antraege/uebersetzen.py`). Überschrieben werden nur die
  übersetzten Felder; danach lässt sich jede Sprache wie gewohnt ansehen und korrigieren.
- Die Seite holt die Sprachen nacheinander per htmx (eine Anfrage je Sprache), damit keine
  einzelne Anfrage zu lange dauert und man den Fortschritt sieht.
- Die Antwort kommt als JSON nach festem Schema; ein Text wird nur übernommen, wenn er dieselben
  Platzhalter (`{nummer}`, `{tafel}` …) enthält wie der deutsche. HTML bleibt erhalten und läuft beim
  Anzeigen wie immer durch `apps.core.html` (nh3).
- Lehnt das Modell eine Anfrage ab, übernimmt serverseitig ein anderes Modell (`fallbacks:
  "default"`).
- Jede Tafel trägt einen eigenen API-Schlüssel ein („Anträge einstellen“); er wird wie das
  Mail-Passwort verschlüsselt gespeichert (ADR 0016), nicht protokolliert und nie wieder angezeigt.
  Ohne Schlüssel gibt es den Knopf nicht.
- Neue Abhängigkeit: das offizielle Python-SDK `anthropic` (mit festen Versionen seiner
  Abhängigkeiten in `requirements.txt`).

## Begründung

- Nur die Texte der Tafel verlassen den Server, nie Angaben aus Anträgen; das bisherige
  Versprechen (ADR 0024) gilt also weiter für alles, was Antragstellende eingeben.
- Claude kann alle 29 Sprachen, auch Tigrinya, Paschtu, Dari, Sorani und Kurmandschi, die gerade
  bei Tafeln gebraucht werden und die andere Dienste (z. B. DeepL) nicht anbieten.
- Kosten entstehen nur bei Klick; eine vollständige Übersetzung kostet wenige Cent.
