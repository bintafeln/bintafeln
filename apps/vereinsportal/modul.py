"""Beschreibung des Moduls für den Modulrahmen (ADR 0049, ADR 0126). Ohne Datenbankzugriff."""

from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Verein/Spenden", [
            ("vereinsportal.nutzen", eintrag("Aus dem Vereinsportal einlesen",
                                             "vereinsportal:start", genau=True)),
            ("vereinsportal.abruf", eintrag("Abruf aus dem Vereinsportal",
                                             "vereinsportal:abruf")),
        ]),
        ("Einstellungen/Verein", [
            ("vereinsportal.nutzen", eintrag("Vereinsportal", "vereinsportal:einstellungen")),
        ]),
    ]  # fmt: skip


def auskunft_mitarbeiter(benutzer, pdf):
    from apps.vereinsportal.models import Abruf, Zugang

    zugang = Zugang.objects.filter(benutzer=benutzer).first()
    abrufe = Abruf.objects.filter(benutzer=benutzer)
    if not zugang and not abrufe.exists():
        return
    pdf.ueberschrift("Vereinsportal")
    if zugang:
        pdf.absatz(f"Gespeicherte Zugangsdaten: E-Mail {zugang.email}, Passwort verschlüsselt "
                   f"gespeichert (geändert am {zugang.geaendert_am:%d.%m.%Y}).")  # fmt: skip
    if abrufe.exists():
        pdf.tabelle(["Gestartet am", "Zeitraum", "Ergebnis"],
                    [[f"{a.gestartet_am:%d.%m.%Y %H:%M}", f"{a.von:%d.%m.%Y} – {a.bis:%d.%m.%Y}",
                      a.get_stand_display()] for a in abrufe],
                    breiten=[0.3, 0.4, 0.3])  # fmt: skip


MODUL = Modul(
    kennung="vereinsportal",
    titel="Spendenbelege aus dem Vereinsportal",
    beschreibung="Für Tafeln, die ihre Spendenbescheinigungen im Vereinsportal ausstellen: "
    "Finanzexport und die Liste der Spender mit E-Mail einlesen (von Hand oder automatisch). Die "
    "Spenden kommen in die Spendenliste, die Spender ins Adressbuch; bintafeln stellt für sie "
    "keine zweite Bestätigung aus, erstellt aber Sammelbestätigungen für Mehrfachspender.",
    app_label="vereinsportal",
    pfade=("/vereinsportal/",),
    rechte=(
        ("vereinsportal.nutzen", "Spenden aus dem Vereinsportal einlesen",
         "Finanzexport und Spenderliste von Hand einlesen und die Einstellungen dazu ändern. "
         "Dabei entstehen Spenden und Adressen."),
        ("vereinsportal.abruf", "Automatischer Abruf mit eigenen Zugangsdaten",
         "Finanzexport und Spenderliste automatisch aus dem Vereinsportal holen. Jedes Konto "
         "trägt dafür seine eigenen Zugangsdaten ein; andere sehen und nutzen sie nicht. "
         "Gedacht für Vorstand und Admin."),
    ),
    vorgaben={"Büro": ("vereinsportal.nutzen",)},
    kapitel=(("vereinsportal", "Spendenbelege aus dem Vereinsportal",
              ("vereinsportal.nutzen",)),),
    menue=menue,
    auskunft_mitarbeiter=auskunft_mitarbeiter,
    sicherung_bereich="adressen",
)  # fmt: skip
