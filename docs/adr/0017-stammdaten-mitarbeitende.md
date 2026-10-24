# 0017: Stammdaten der Mitarbeitenden, Wiedervorlagen und Löschfrist

- Status: Angenommen
- Datum: 2026-10-24
- Ergänzt: ADR 0015

## Problem

Für Mitarbeitende braucht die Tafel mehr als ein Konto: Anschrift und Telefon, Notfallkontakt,
Eintritt und Austritt. Für Fahrer muss sie den Führerschein regelmäßig prüfen. Wer mit
Lebensmitteln umgeht, braucht die Belehrung nach § 43 Infektionsschutzgesetz (IfSG). Diese
Angaben sind Personaldaten und dürfen nicht unbegrenzt gespeichert werden.

## Entscheidung

- **Stammdaten** liegen in einem eigenen Datensatz neben dem Konto: Anrede, Geburtsdatum,
  Anschrift, Telefon, Handy, Notfallkontakt, Eintritt, Austritt, Anmerkung. Dazu kommen der
  **Führerschein-Vermerk** (Klassen, gültig bis, gesehen am / von) und die **IfSG-Belehrung**
  (Erstbelehrung, letzte Folgebelehrung) sowie **Schulungen** (Thema, Datum, gültig bis).
- Sehen und bearbeiten dürfen dieselben Personen, die Mitarbeitende verwalten (Admin; das Büro
  mit Freigabe, aber nicht bei Admin-Konten).
- **Wiedervorlagen:**
  - Führerschein ansehen nach N Monaten (Vorgabe 6, nur Rolle Fahrer); Ablauf des Führerscheins
  - IfSG-Folgebelehrung nach N Monaten (Vorgabe 24, Rollen Ausgabe, Fahrer, Beifahrer)
  - Ablauf von Schulungen (je Thema die jüngste)
  - Erscheinen mit Vorlauf (Vorgabe 14 Tage) unter „Mitarbeitende → Fällig“ und als Hinweis auf
    der Startseite
- **Führerschein-Kopie** nur, wenn die Tafel sie in den Einstellungen erlaubt (Vorgabe: aus; der
  Vermerk genügt in der Regel). Kopien werden mit dem Schlüssel aus ADR 0016 verschlüsselt
  unter `MEDIA_ROOT/privat/` gespeichert und nie öffentlich ausgeliefert. Jeder Abruf steht im
  Änderungsprotokoll.
- **Löschfrist:** N Jahre (Vorgabe 3) nach Austritt bzw. Sperre werden Anschrift, Kontakte,
  Notfallkontakt, Führerschein, Belehrungen, Kopie und Schulungen geleert. Die Einträge dazu im
  Änderungsprotokoll werden ebenfalls gelöscht. Name, Rollen, Eintritt und Austritt bleiben im
  Archiv (ADR 0015).

## Begründung

Der getrennte Datensatz erlaubt es, persönliche Angaben fristgerecht zu leeren, ohne die
Nachvollziehbarkeit (wer war wann dabei) zu verlieren. Wiedervorlagen ersetzen Listen auf Papier.
Die Kopie ist optional und verschlüsselt, weil sie meist nicht erforderlich ist
(Datensparsamkeit).
