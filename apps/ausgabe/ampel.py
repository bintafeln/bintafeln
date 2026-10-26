"""Ampel am Einlass: Darf ein Haushalt heute abholen?

Rot verhindert das Eintragen, gelb ist ein Hinweis, grün heißt alles in Ordnung. Eine Ausnahme
für heute hebt die Terminregeln auf (nicht dran, Höchstzahl, andere Ausgabestelle), nicht aber
Sperre, Status oder einen abgelaufenen Ausweis.
"""

import datetime as dt
import re
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
    # Kunde ist noch nicht an der Reihe (z. B. Aufruf): Ampel blinkt gelb, Abholung bleibt möglich
    blinken: bool = False

    @property
    def farbe(self) -> str:
        farben = {m.farbe for m in self.meldungen}
        if ROT in farben:
            return ROT
        if GELB in farben:
            return GELB
        return GRUEN

    @property
    def lampe(self) -> str:
        """Farbe der Ampel-Grafik: blinkendes Gelb, solange der Kunde noch nicht dran ist."""
        return GELB if self.blinken and self.farbe != ROT else self.farbe

    @property
    def darf_abholen(self) -> bool:
        return self.farbe != ROT

    @property
    def ausnahme_hilft(self) -> bool:
        """Rot nur wegen Regeln, die eine Ausnahme für heute aufhebt."""
        rote = [m for m in self.meldungen if m.farbe == ROT]
        return bool(rote) and all(m.ausnahme_moeglich for m in rote)


def wochentage(text: str) -> list[str]:
    """Wochentage einer Kundengruppe als Kürzel „Mo“ … „So“; nimmt auch „Montag“, „mo“, „Di.“."""
    kuerzel = (t.strip(" .")[:2].capitalize() for t in re.split(r"[,;/\s]+", text or ""))
    return [k for k in kuerzel if k in WOCHENTAGE]


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


# Meldungen, deren Text die Tafel ändern kann: Schlüssel, Bezeichnung, Standardtext, Platzhalter.
# Der Standardtext steht im Code (unten); leer gelassene eigene Texte verwenden ihn.
MELDUNGEN = [
    ("status", "Status gesperrt, beendet oder pausiert", "Status: {status}", ["status"]),
    ("sperre", "Aktive Sperre", "Gesperrt seit {von} bis {bis}: {grund}", ["von", "bis", "grund"]),
    ("ausweis_fehlt", "Kein Ablaufdatum des Ausweises", "Kein Ablaufdatum des Ausweises "
     "hinterlegt", []),
    ("ausweis_abgelaufen", "Ausweis abgelaufen", "Ausweis abgelaufen am {datum}", ["datum"]),
    ("ausweis_bald", "Ausweis läuft bald ab", "Ausweis läuft am {datum} ab", ["datum"]),
    ("heute_abgeholt", "Heute schon so oft abgeholt wie erlaubt", "Heute bereits abgeholt um "
     "{uhrzeit}", ["uhrzeit", "anzahl"]),
    ("heute_mehrfach", "Heute schon abgeholt (mehrfach erlaubt)", "Heute schon {anzahl}-mal "
     "abgeholt (mehrfach erlaubt)", ["anzahl"]),
    ("hoechstzahl", "Höchstzahl im Zeitraum erreicht", "Höchstzahl erreicht: {anzahl} Abholungen "
     "{zeitraum}", ["anzahl", "zeitraum"]),
    ("keine_gruppe", "Keine Kundengruppe", "Keine Kundengruppe zugeordnet", []),
    ("keine_wochentage", "Kundengruppe ohne Wochentage", "Kundengruppe {gruppe} hat keine "
     "Wochentage", ["gruppe"]),
    ("nicht_dran", "Heute nicht dran", "Heute nicht dran (Kundengruppe {gruppe}: {tage})",
     ["gruppe", "tage"]),
    ("andere_stelle", "Andere Ausgabestelle", "Kundengruppe gehört zur Ausgabestelle {stelle}",
     ["stelle"]),
    ("konto_negativ", "Kontostand negativ", "Kontostand negativ: −{betrag} € (angeschrieben)",
     ["betrag"]),
    ("ok", "Alles in Ordnung", "Alles in Ordnung", []),
]  # fmt: skip
MELDUNGS_ARTEN = {art for art, *_ in MELDUNGEN}


def eigener_text(vorlage: str, werte: dict) -> str:
    """Setzt {platzhalter} ein; unbekannte bleiben stehen (kein str.format, keine Attribute)."""
    return re.sub(r"\{(\w+)\}", lambda m: str(werte.get(m[1], m[0])), vorlage).strip()


def bewerten(haushalt, heute: dt.date, ausgabestelle, einstellungen) -> Bewertung:
    """Bewertet einen Haushalt für heute an der gewählten Ausgabestelle (oder None)."""
    b = Bewertung()
    eigene = getattr(einstellungen, "meldungstexte", None) or {}

    def t(art, standard, **werte):
        """Eigener Text der Tafel für diese Meldung, sonst der Standardtext."""
        vorlage = (eigene.get(art) or "").strip()
        return eigener_text(vorlage, werte) if vorlage else standard

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
        status = haushalt.get_status_display()
        melden(ROT, t("status", f"Status: {status}", status=status))
    elif haushalt.status == "pausiert":
        melden(GELB, t("status", "Status: pausiert", status="pausiert"))

    for sperre in haushalt.sperren.all():
        if sperre.ist_aktiv(heute):
            bis = f" bis {sperre.bis:%d.%m.%Y}" if sperre.bis else ""
            zeigen = getattr(einstellungen, "einlass_sperren", True)
            grund = f": {sperre.begruendung}" if sperre.begruendung and zeigen else ""
            melden(ROT, t("sperre", f"Gesperrt seit {sperre.von:%d.%m.%Y}{bis}{grund}",
                          von=f"{sperre.von:%d.%m.%Y}",
                          bis=f"{sperre.bis:%d.%m.%Y}" if sperre.bis else "",
                          grund=sperre.begruendung if zeigen else ""))  # fmt: skip

    ausweis = haushalt.ausweis_gueltig_bis
    if ausweis is None:
        melden(GELB, t("ausweis_fehlt", "Kein Ablaufdatum des Ausweises hinterlegt"))
    elif ausweis < heute:
        datum = f"{ausweis:%d.%m.%Y}"
        melden(ROT, t("ausweis_abgelaufen", f"Ausweis abgelaufen am {datum}", datum=datum))
    elif ausweis <= heute + dt.timedelta(days=einstellungen.vorwarnung_tage):
        datum = f"{ausweis:%d.%m.%Y}"
        melden(GELB, t("ausweis_bald", f"Ausweis läuft am {datum} ab", datum=datum))

    abholungen = [a for a in haushalt.abholungen.all() if a.datum <= heute]
    heute_abgeholt = [a for a in abholungen if a.datum == heute]
    je_tag = einstellungen.max_je_tag  # 0 = beliebig oft am selben Tag
    if heute_abgeholt and je_tag and len(heute_abgeholt) >= je_tag:
        uhrzeiten = [a.uhrzeit for a in heute_abgeholt if a.uhrzeit]
        um = f" um {max(uhrzeiten):%H:%M}" if uhrzeiten else ""
        if je_tag == 1:
            standard = f"Heute bereits abgeholt{um}"
        else:
            standard = (f"Heute bereits {len(heute_abgeholt)}-mal abgeholt, zuletzt"
                        f"{um or ' heute'} (höchstens {je_tag}-mal am Tag)")  # fmt: skip
        uhrzeit = f"{max(uhrzeiten):%H:%M}" if uhrzeiten else ""
        melden(ROT, t("heute_abgeholt", standard, uhrzeit=uhrzeit, anzahl=len(heute_abgeholt)))
    else:
        if heute_abgeholt:
            n = len(heute_abgeholt)
            melden(GELB, t("heute_mehrfach", f"Heute schon {n}-mal abgeholt (mehrfach erlaubt)",
                           anzahl=n))  # fmt: skip
        beginn = zeitraum_beginn(heute, einstellungen.zeitraum)
        anzahl = sum(1 for a in abholungen if a.datum >= beginn)
        if einstellungen.max_abholungen and anzahl >= einstellungen.max_abholungen:
            zeitraum = ZEITRAUM_TEXT[einstellungen.zeitraum]
            terminregel(t("hoechstzahl", f"Höchstzahl erreicht: {anzahl} Abholung"
                          f"{'en' if anzahl != 1 else ''} {zeitraum}", anzahl=anzahl,
                          zeitraum=zeitraum))  # fmt: skip

    gruppe = haushalt.kundengruppe
    if gruppe is None:
        terminregel(t("keine_gruppe", "Keine Kundengruppe zugeordnet"))
    else:
        tage = wochentage(gruppe.wochentage)
        if not tage:
            terminregel(
                t("keine_wochentage", f"Kundengruppe {gruppe.name} hat keine Wochentage – nicht "
                  "prüfbar, ob heute dran (Einstellungen → Kundengruppen)", gruppe=gruppe.name),
                GELB,
            )  # fmt: skip
        elif WOCHENTAGE[heute.weekday()] not in tage:
            terminregel(
                t("nicht_dran", f"Heute nicht dran (Kundengruppe {gruppe.name}: "
                  f"{', '.join(tage)})", gruppe=gruppe.name, tage=", ".join(tage)),
                ROT if einstellungen.nicht_dran_rot else GELB,
            )  # fmt: skip
        if ausgabestelle and gruppe.ausgabestelle and gruppe.ausgabestelle != ausgabestelle:
            stelle = gruppe.ausgabestelle.name
            terminregel(t("andere_stelle", f"Kundengruppe gehört zur Ausgabestelle {stelle}",
                          stelle=stelle), GELB)  # fmt: skip

    if haushalt.kontostand is not None and haushalt.kontostand < 0:
        betrag = f"{-haushalt.kontostand:.2f}".replace(".", ",")
        melden(GELB, t("konto_negativ", f"Kontostand negativ: −{betrag} € (angeschrieben)",
                       betrag=betrag))  # fmt: skip

    if not b.meldungen:
        melden(GRUEN, t("ok", "Alles in Ordnung"))
    return b


def noch_nicht_dran(b: Bewertung, hinweise: list[dict]) -> Bewertung:
    """Meldet ein Modul (z. B. Aufruf), dass der Kunde noch warten muss, blinkt die Ampel gelb.
    Die Bewertung selbst bleibt (Abholung möglich, grün oder gelb); Rot bleibt Rot."""
    if b.farbe == ROT or not any(h.get("warten") for h in hinweise):
        return b
    # „Alles in Ordnung“ passt nicht mehr; Ausnahmen für heute bleiben stehen
    b.meldungen = [m for m in b.meldungen if m.farbe != GRUEN or "Ausnahme" in m.text]
    b.meldungen.insert(0, Meldung(GRUEN, "Kunde ist zu früh (Aufruf)"))
    b.blinken = True
    return b
