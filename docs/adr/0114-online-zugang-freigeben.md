# ADR 0114: Online-Zugang mit Geburtsdatum als Startpasswort freigeben

## Problem

Importierte Mitarbeitende haben ein Konto, aber (aus dem Import mit Einladung, ADR 0016) **kein
nutzbares Passwort** – sie können sich nicht anmelden. Bei vielen Ehrenamtlichen ist der bestehende
Weg (jede Person bekommt einen Einladungs-Link und setzt ihr Passwort selbst) umständlich: Viele
klicken den Link nicht, brauchen Hilfe, haben keine Mail gelesen. Gewünscht ist eine einfache,
händische Freigabe je Person – mit einem Passwort, das die Person ohnehin kennt.

## Entscheidung

Neue Aktion **„Online-Zugang freigeben"** (einzeln auf der Kontoseite, gesammelt über die Seite
„Online-Zugänge freigeben"):

- Startpasswort = **Geburtsdatum mit Punkten** (`TT.MM.JJJJ`, z. B. `15.03.1980`); fehlt es,
  **Straße und Hausnummer** (wie hinterlegt). Beides kennt die Person selbst. Fehlt beides, wird die
  Freigabe mit Hinweis abgelehnt (dann Daten nachtragen oder den Link-Weg nutzen).
- Das Konto wird aktiv und muss das Passwort **bei der ersten Anmeldung ändern**
  (`passwort_aendern` + `PasswortAendernMiddleware`, vor der Zwei-Faktor-Einrichtung).
- Ist eine **E-Mail-Adresse** hinterlegt, geht eine Einladung an diese Adresse mit Anmeldelink und
  dem **Format** des vorläufigen Passworts (nicht dem konkreten Wert – die Person kennt ihn).
  Fehlt die Adresse, wird trotzdem freigegeben; die Oberfläche weist darauf hin, die Zugangsdaten
  persönlich weiterzugeben.

Logik in `apps/konten/verwaltung.py` (`freigeben`, `startpasswort_basis`), Mail in
`apps/konten/einladung.py` (`freigabe_senden`, Vorlage `mail/freigabe.txt`), Ansichten in
`views_mitarbeitende.py` (`freigeben`, `zugaenge_freigeben`). „Noch nicht freigeschaltet" erkennt
bintafeln an `has_usable_password() == False`.

## Begründung

Das Geburtstags-Passwort ist bewusst einfach und für die Person leicht zu merken; es gilt **nur bis
zur ersten Anmeldung**. Danach fangen der erzwungene Passwortwechsel und – bei sensiblen Rollen –
die Zwei-Faktor-Pflicht das schwache Startpasswort ab, die Anmelde-Sperre (5 Fehlversuche/15 min)
bleibt. Deshalb darf das Format auch in der Mail stehen. Der bestehende **Einladungs-Link** (Person
setzt selbst ein Passwort) bleibt als Alternative erhalten; die neue Freigabe ist der einfache Weg,
um viele vorhandene Konten nach dem Import zügig nutzbar zu machen.
