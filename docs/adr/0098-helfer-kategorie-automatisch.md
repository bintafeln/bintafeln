# 0098: Helfer-Kategorie automatisch, Kategorie „Ehemalige Ehrenamtliche“

- Status: Angenommen
- Datum: 2026-11-01

## Problem

Seit ADR 0097 ergibt sich die Einteilbarkeit aus der **Rolle** des Kontos, und jede Person mit
Konto hat mindestens eine Rolle. Daneben gibt es im Adressbuch die **Kategorien** (Spender, Markt,
Presse … und „Ehrenamtliche Helfer“). Rolle und Kategorie beantworten verschiedene Fragen:

- **Rolle** (am Konto): *Was darf die Person, wo ist sie einteilbar?* – setzt ein Login-Konto voraus.
- **Kategorie** (an der Adresse): *Wie ist der Eintrag einzuordnen?* – braucht kein Konto, auch
  Organisationen (Märkte, Firmen) haben welche. Kategorien dienen zum Filtern und als
  Empfänger-Auswahl, z. B. für Serienbriefe.

Die Kategorie „Ehrenamtliche Helfer“ musste bisher von Hand gesetzt werden. Wer ausscheidet,
verliert zudem keine saubere Spur: man möchte Ehemalige weiterhin anschreiben können (z. B. zum
Helferfest), ohne sie mit den aktiven Helfern zu vermischen.

## Entscheidung

- **Jede Person mit Konto und mindestens einer Rolle wird automatisch der Kategorie „Ehrenamtliche
  Helfer“ zugeordnet** (egal welche Rolle). Das geschieht beim Anlegen, beim Bearbeiten und beim
  Setzen der Rollen in der Adress-Maske.
- Die Kategorie wird **nur ergänzt, nie automatisch entfernt**: Fällt später eine Rolle weg oder
  scheidet die Person aus, bleibt sie als (ehemaliger) Helfer auffindbar.
- Neue Kategorie **„Ehemalige Ehrenamtliche“**. Wird ein Mitarbeiter-Konto **gesperrt**, bekommt die
  verknüpfte Adresse diese Kategorie **zusätzlich** – „Ehrenamtliche Helfer“ bleibt erhalten.
- Konten einer Ausgabestelle (Einlass-Tablet) sind keine Person und bleiben außen vor.

Eine Datenmigration legt die neue Kategorie an und kennzeichnet bestehende Mitarbeiter-Adressen als
„Ehrenamtliche Helfer“.

**Nachtrag:** Die Pflicht „mindestens eine Rolle“ (ADR 0097) gilt nur für **aktive** Konten.
Scheidet jemand aus, wird das Konto gesperrt (direkt über „Konto sperren“ auf der Adressseite); ein
gesperrtes Konto darf rollenlos sein und bleibt so als reine Adresse erhalten. „Verträge & Zeiten“
(früher „Personal“) ist zusätzlich als Reiter unter „Angestellte“ erreichbar; die Adressseite
speichert Änderungen sofort (Autosave, ADR 0076).

## Begründung

Rolle und Kategorie bleiben getrennt (sie lassen sich nicht zusammenlegen: Rollen brauchen ein
Konto, Kategorien gelten auch für Organisationen). Die Automatik verbindet beide nur dort, wo es
der Pflege hilft: Wer mitarbeitet, steht ohne Zusatzaufwand als Helfer im Adressbuch und bleibt es
auch nach dem Ausscheiden – getrennt in aktive und ehemalige, damit Serienbriefe gezielt gehen.
Additiv und nie automatisch löschend, damit keine Spur ungewollt verschwindet.
