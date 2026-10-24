"""Ampel am Einlass: Darf ein Haushalt heute abholen?

Rot verhindert das Eintragen, gelb ist ein Hinweis, grün heißt alles in Ordnung. Eine Ausnahme
für heute hebt die Terminregeln auf (nicht dran, Höchstzahl, andere Ausgabestelle), nicht aber
Sperre, Status oder einen abgelaufenen Ausweis.
"""

import datetime as dt
from dataclasses import dataclass, field

from apps.ausgabe.models import AusgabeEinstellungen

ROT, GELB, GRUEN = "rot", "gelb", "gruen"
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


@dataclass
class Meldung:
    farbe: str
    text: str
    ausnahme_moeglich: bool = False  # eine Ausnahme für heute würde die Regel aufheben


@dataclass
class Bewertung:
    meldungen: list[Meldung] = field(default_factory=list)

    @property
    def farbe(self) -> str:
        farben = {m.farbe for m in self.meldungen}
        if ROT in farben:
            return ROT
        if GELB in farben:
            return GELB
        return GRUEN

    @property
    def darf_abholen(self) -> bool:
        return self.farbe != ROT

    @property
    def ausnahme_hilft(self) -> bool:
        """Rot nur wegen Regeln, die eine Ausnahme für heute aufhebt."""
        rote = [m for m in self.meldungen if m.farbe == ROT]
        return bool(rote) and all(m.ausnahme_moeglich for m in rote)


def zeitraum_beginn(heute: dt.date, zeitraum: str) -> dt.date:
    if zeitraum == AusgabeEinstellungen.Zeitraum.MONAT:
        return heute.replace(day=1)
    if zeitraum == AusgabeEinstellungen.Zeitraum.VIERZEHN_TAGE:
        return heute - dt.timedelta(days=13)
    return heute - dt.timedelta(days=heute.weekday())


ZEITRAUM_TEXT = {
    AusgabeEinstellungen.Zeitraum.WOCHE: "in dieser Kalenderwoche",
    AusgabeEinstellungen.Zeitraum.VIERZEHN_TAGE: "in den letzten 14 Tagen",
    AusgabeEinstellungen.Zeitraum.MONAT: "in diesem Monat",
}


def bewerten(haushalt, heute: dt.date, ausgabestelle, einstellungen) -> Bewertung:
    """Bewertet einen Haushalt für heute an der gewählten Ausgabestelle (oder None)."""
    b = Bewertung()

    def melden(farbe, text, ausnahme_moeglich=False):
        b.meldungen.append(Meldung(farbe, text, ausnahme_moeglich))

    ausnahme = next((a for a in haushalt.ausnahmen.all() if a.datum == heute), None)

    def terminregel(text, farbe=ROT):
        """Regel, die eine Ausnahme für heute aufheben kann."""
        if ausnahme:
            grund = f": {ausnahme.begruendung}" if ausnahme.begruendung else ""
            melden(GRUEN, f"{text} – Ausnahme für heute erteilt{grund}")
        else:
            melden(farbe, text, ausnahme_moeglich=True)

    if haushalt.status in ("gesperrt", "beendet"):
        melden(ROT, f"Status: {haushalt.get_status_display()}")
    elif haushalt.status == "pausiert":
        melden(GELB, "Status: pausiert")

    for sperre in haushalt.sperren.all():
        if sperre.ist_aktiv(heute):
            bis = f" bis {sperre.bis:%d.%m.%Y}" if sperre.bis else ""
            grund = f": {sperre.begruendung}" if sperre.begruendung else ""
            melden(ROT, f"Gesperrt seit {sperre.von:%d.%m.%Y}{bis}{grund}")

    ausweis = haushalt.ausweis_gueltig_bis
    if ausweis is None:
        melden(GELB, "Kein Ablaufdatum des Ausweises hinterlegt")
    elif ausweis < heute:
        melden(ROT, f"Ausweis abgelaufen am {ausweis:%d.%m.%Y}")
    elif ausweis <= heute + dt.timedelta(days=einstellungen.vorwarnung_tage):
        melden(GELB, f"Ausweis läuft am {ausweis:%d.%m.%Y} ab")

    abholungen = [a for a in haushalt.abholungen.all() if a.datum <= heute]
    heute_abgeholt = [a for a in abholungen if a.datum == heute]
    if heute_abgeholt:
        uhrzeit = heute_abgeholt[0].uhrzeit
        um = f" um {uhrzeit:%H:%M}" if uhrzeit else ""
        melden(ROT, f"Heute bereits abgeholt{um}")
    else:
        beginn = zeitraum_beginn(heute, einstellungen.zeitraum)
        anzahl = sum(1 for a in abholungen if a.datum >= beginn)
        if anzahl >= einstellungen.max_abholungen:
            terminregel(
                f"Höchstzahl erreicht: {anzahl} Abholung{'en' if anzahl != 1 else ''} "
                f"{ZEITRAUM_TEXT[einstellungen.zeitraum]}"
            )

    gruppe = haushalt.kundengruppe
    if gruppe is None:
        terminregel("Keine Kundengruppe zugeordnet")
    else:
        tage = [t.strip() for t in gruppe.wochentage.split(",") if t.strip()]
        if tage and WOCHENTAGE[heute.weekday()] not in tage:
            terminregel(
                f"Heute nicht dran (Kundengruppe {gruppe.name}: {', '.join(tage)})",
                ROT if einstellungen.nicht_dran_rot else GELB,
            )
        if ausgabestelle and gruppe.ausgabestelle and gruppe.ausgabestelle != ausgabestelle:
            terminregel(f"Kundengruppe gehört zur Ausgabestelle {gruppe.ausgabestelle.name}", GELB)

    if haushalt.kontostand is not None and haushalt.kontostand < 0:
        betrag = f"{-haushalt.kontostand:.2f}".replace(".", ",")
        melden(GELB, f"Kontostand negativ: −{betrag} € (angeschrieben)")

    if not b.meldungen:
        melden(GRUEN, "Alles in Ordnung")
    return b
