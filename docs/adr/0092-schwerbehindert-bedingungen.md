# 0092 – Wann eine Person als schwerbehindert gilt

## Problem

Bisher galt jede Person ab GdB 50 als „schwerbehindert“ (Merkmal am Einlass, Rollstuhl-Symbol auf
dem Ausweis, Vorrang beim Aufruf). Tafeln erkennen das aber nach eigenen Regeln an, z. B. erst ab
einem höheren Grad, nur mit bestimmten Merkzeichen oder nur, wenn der Ausweis gezeigt wurde.

## Entscheidung

- Drei Bedingungen in `KundenEinstellungen`, alle müssen erfüllt sein: `sb_ab_gdb` (Vorgabe 50,
  also wie bisher), `sb_merkzeichen` (leer = egal, sonst mindestens eines davon) und
  `sb_ausweis_vorgelegt` (Haken „Schwerbehindertenausweis vorgelegt“ an der Person, Zusatzfeld
  `sb_ausweis`, Art. 9).
- Die Regel steht nur in `merkmale.gilt_schwerbehindert()`; `gdb_setzen()` (Antrag, Bearbeiten)
  nutzt sie. Ändern sich die Bedingungen, setzt `merkmale.neu_bewerten()` das Merkmal bei allen
  Personen mit GdB neu. Personen ohne GdB (von Hand oder aus dem Import) behalten ihren Wert.
- Schwerbehinderung wird nicht weiter unterteilt. Blind, Taub und Stumm bleiben eigene Merkmale
  (z. B. als Kürzel auf dem Ausweis); GdB und Merkzeichen stehen nur in den Daten der Person.

## Begründung

Die Vorgabe ändert nichts für Tafeln, die nichts einstellen. Eine Stelle für die Regel verhindert,
dass Antrag, Bearbeiten und Ausweis verschieden entscheiden.
