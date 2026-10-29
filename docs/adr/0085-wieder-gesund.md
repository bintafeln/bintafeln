# 0085: Wieder gesund heißt nicht wieder eingetragen

- Status: Angenommen
- Datum: 2026-10-29

## Problem

Am Aushang-Monitor ließ sich ein Ausfall nur für den angetippten Tag eintragen. Wer länger krank
ist, musste jeden Tag einzeln austragen.

Kam jemand früher zurück, blieb nur „zurücknehmen“: Das löscht den Ausfall, und die Person steht
sofort wieder auf ihren festen Plätzen. Dort ist aber oft schon ein Ersatz geplant oder
abgesprochen, und das ginge dabei unter.

## Entscheidung

- Beim Austragen am Monitor wählt man neben dem Grund die Dauer: nur dieser Tag, 1 bis 8 Wochen
  oder bis zu einem Datum (höchstens ein Jahr). Die Regeln stehen in `apps/core/ausfall.py`.
- „Wieder gesund“ (am Monitor, unter „Meine Dienste/Einsätze“ und in der Platzansicht) setzt
  `Ausfall.gesund_ab` auf heute.
  - Ab dann ist die Person verfügbar und kann einspringen, auch auf ihrem alten Platz.
  - Ihre festen Plätze bleiben bis zum Ende des Ausfalls frei bzw. beim Ersatz.
  - Die Planenden werden benachrichtigt (Mail, Telegram).
- „Zurücknehmen“ bleibt für versehentlich gemeldete Ausfälle und löscht ganz.

## Begründung

Niemand soll durch eine Gesundmeldung aus Versehen doppelt eingeteilt werden oder einen
abgesprochenen Ersatz verdrängen. Die Person trägt sich bewusst dort ein, wo noch jemand fehlt.
