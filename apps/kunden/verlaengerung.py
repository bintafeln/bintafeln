"""Sammel-Verlängerung der Ausweise (ADR 0068).

Die Ausgabestellen melden mit einer Nachricht (Anliegen „verlaengern“), dass sie die Bescheide
geprüft haben. Die Verwaltung bekommt alle gemeldeten Haushalte auf einer Seite, jeder geprüft
nach den Bedingungen aus den Einstellungen des Kundenstamms, und verlängert sie zusammen. Wer die
Bedingungen nicht erfüllt, bekommt je nach Einstellung eine Notiz an die Ausgabestelle (Pause
einlegen, Status bleibt) oder wird pausiert; die gemeldete Notiz wird dabei gestrichen.
"""

import datetime as dt
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from apps.antraege.aufnahme import monat_plus
from apps.kunden import gruppen, historie
from apps.kunden.models import (
    Haushalt,
    HaushaltEreignis,
    KundenEinstellungen,
    Nachricht,
    Notiz,
    NotizVorlage,
    Zusatzfeld,
)

ANLIEGEN = "verlaengern"
# Steht der Ausweis noch so lange, ist die Meldung vermutlich zu früh
NOCH_LANGE_TAGE = 60

OK, NEIN, UNKLAR = "ok", "nein", "unklar"


@dataclass
class Pruefung:
    haushalt: Haushalt
    ergebnis: str  # OK, NEIN oder UNKLAR
    neu_bis: dt.date
    personen: list[tuple[str, str]] = field(default_factory=list)  # (Name, erfüllt durch / fehlt)
    gruende: list[str] = field(default_factory=list)
    fehlt: list[str] = field(
        default_factory=list
    )  # Personen ohne Bedingung, z. B. „Peter Muster: 33 Jahre, nicht schwerbehindert“
    hinweise: list[str] = field(default_factory=list)
    nachrichten: list[Nachricht] = field(default_factory=list)

    @property
    def nummer(self) -> str:
        return self.haushalt.kundennummer


def neues_datum(h: Haushalt, heute: dt.date, monate: int, e: KundenEinstellungen) -> dt.date:
    """Ab dem bisherigen Ablauf weiter; ist der Ausweis schon abgelaufen, ab heute."""
    basis = max(h.ausweis_gueltig_bis or heute, heute)
    return monat_plus(basis, monate, e.ausweis_bis_monatsende)


def _bedingung(person, h: Haushalt, heute: dt.date, e: KundenEinstellungen, felder) -> str:
    """Womit die Person die Bedingung erfüllt; leer, wenn nicht; None, wenn es unklar ist."""
    for f in felder:
        quelle = h.zusatz if f.gilt_fuer == Zusatzfeld.GiltFuer.HAUSHALT else person.zusatz
        if quelle.get(f.schluessel) is True:
            return f.bezeichnung
    if e.verlaengern_ab_alter is not None:
        alter = person.alter(heute)
        if alter is None:
            return None
        if alter >= e.verlaengern_ab_alter:
            return f"{alter} Jahre"
    return ""


def _nicht_erfuellt(person, heute: dt.date, e: KundenEinstellungen, felder) -> str:
    """Was der Person fehlt, z. B. „33 Jahre, nicht schwerbehindert“."""
    teile = []
    if e.verlaengern_ab_alter is not None and (alter := person.alter(heute)) is not None:
        teile.append(f"{alter} {'Jahr' if alter == 1 else 'Jahre'}")
    for f in felder:
        b = f.bezeichnung
        teile.append(f"nicht {b.lower()}" if " " not in b.strip() else f"nicht „{b}“")
    return ", ".join(teile)


def personen_text(e: KundenEinstellungen) -> str:
    """Bedingung je Person, z. B. „ab 60 Jahren oder Schwerbehindert“; leer ohne."""
    teile = []
    if e.verlaengern_ab_alter is not None:
        teile.append(f"ab {e.verlaengern_ab_alter} Jahren")
    teile += [f.bezeichnung for f in e.verlaengern_felder.all()]
    return " oder ".join(teile)


def einkommen_text(e: KundenEinstellungen) -> str:
    """Einkommensarten, von denen der Haushalt zusätzlich eine haben muss; leer ohne."""
    arten = [a.bezeichnung for a in e.verlaengern_einkommensarten.all()]
    return ", ".join(arten[:-1]) + f" oder {arten[-1]}" if len(arten) > 1 else "".join(arten)


def bedingungen_text(e: KundenEinstellungen) -> str:
    """z. B. „ab 60 Jahren oder Schwerbehindert; zusätzlich Einkommensart Bürgergeld oder
    Wohngeld“; leer ohne Bedingung."""
    if e.verlaengern_regel == KundenEinstellungen.Verlaengern.OHNE:
        return ""
    personen, einkommen = personen_text(e), einkommen_text(e)
    if einkommen:
        zusatz = f"Einkommensart {einkommen}"
        return f"{personen}; zusätzlich {zusatz}" if personen else zusatz
    return personen or "keine Bedingung eingestellt"


def pause_text(monate: int) -> str:
    return "ein Pausenjahr" if monate == 12 else f"eine Pause von {monate} Monaten"


def ablehnung_notiz(p: Pruefung, e: KundenEinstellungen, bis: dt.date | None = None) -> str:
    """Notiz für die Ausgabestelle: was nicht erfüllt ist und was jetzt gilt."""
    # **…** zeigt die Notiz fett (apps/core/templatetags/notiz.py)
    zeilen = ["Ausweis kann **NICHT!** verlängert werden."]
    gruende = [g for g in p.gruende if not g.endswith("erfüllen eine Bedingung")
               and not g.endswith("erfüllt eine Bedingung")
               and not g.startswith(EINKOMMEN_NEIN)]  # fmt: skip
    if p.fehlt:
        wer = ("Mindestens eine Person" if e.verlaengern_regel == e.Verlaengern.EINE
               else "Jede Person")  # fmt: skip
        regel = []
        if personen := personen_text(e):
            regel.append(f"{wer} im Haushalt muss eine der Bedingungen erfüllen ({personen})")
        if einkommen := einkommen_text(e):
            regel.append(("und zusätzlich muss der Haushalt" if personen else "Der Haushalt muss")
                         + f" eine dieser Einkommensarten haben: {einkommen}")  # fmt: skip
        zeilen.append(f"Die Regel besagt: {', '.join(regel)}.")
        zeilen.append("In diesem Haushalt sind folgende Kriterien nicht erfüllt:")
        zeilen += [f"– {f}" for f in p.fehlt]
    zeilen += [f"{g}." for g in gruende]
    text = "\n".join(zeilen)
    if bis:
        return text + f"\nPausiert bis {bis:%d.%m.%Y}."
    if not p.fehlt:  # z. B. gesperrt oder beendet: keine Pause, nur der Grund
        return text
    ablauf = p.haushalt.ausweis_gueltig_bis
    text += f"\nDer Kunde muss {pause_text(e.verlaengern_sonst_pausieren_monate)} einlegen"
    if ablauf:
        text += f"; der Ausweis gilt noch bis {ablauf:%d.%m.%Y}"
    return text + ". Danach ist eine Neuanmeldung über unsere Homepage möglich."


def gemeldete_notizen_streichen(p: Pruefung) -> int:
    """Löscht die Notizen, mit denen gemeldet wurde (Notiz-Knopf mit „Meldet der Verwaltung“)."""
    texte = list(NotizVorlage.objects.filter(melden=ANLIEGEN).values_list("text", flat=True))
    if not texte or not p.nachrichten:
        return 0
    seit = min(n.erstellt_am for n in p.nachrichten) - dt.timedelta(minutes=5)
    return Notiz.objects.filter(kundennummer=p.nummer, text__in=texte,
                                erstellt_am__gte=seit).delete()[0]  # fmt: skip


def pruefen(h: Haushalt, heute: dt.date, monate: int, e: KundenEinstellungen) -> Pruefung:
    p = Pruefung(haushalt=h, ergebnis=OK, neu_bis=neues_datum(h, heute, monate, e))
    if h.status in (Haushalt.Status.GESPERRT, Haushalt.Status.BEENDET):
        p.ergebnis = NEIN
        p.gruende.append(f"Status „{h.get_status_display()}“")
    if any(s.ist_aktiv(heute) for s in h.sperren.all()):
        p.ergebnis = NEIN
        p.gruende.append("Aktive Sperre")
    if h.ausweis_gueltig_bis and (h.ausweis_gueltig_bis - heute).days > NOCH_LANGE_TAGE:
        p.hinweise.append(f"Ausweis noch gültig bis {h.ausweis_gueltig_bis:%d.%m.%Y}")
    if h.status == Haushalt.Status.PAUSIERT:
        p.hinweise.append("Status „pausiert“ bleibt – bei Bedarf im Haushalt ändern")
    if e.verlaengern_regel == KundenEinstellungen.Verlaengern.OHNE:
        return p
    personen = list(h.personen.all())
    if not personen:
        p.ergebnis = UNKLAR if p.ergebnis == OK else p.ergebnis
        p.gruende.append("Keine Personen erfasst")
        return p
    felder = list(e.verlaengern_felder.all())
    # Ohne Alter und Ja/Nein-Feld zählt nur die Einkommensart (unten)
    if e.verlaengern_ab_alter is None and not felder:
        personen = []
    erfuellt = []
    for person in personen:
        womit = _bedingung(person, h, heute, e, felder)
        name = f"{person.vorname} {person.nachname}".strip()
        if womit is None:
            p.personen.append((name, "Geburtsdatum fehlt"))
        elif womit:
            p.personen.append((name, f"✓ {womit}"))
        else:
            # Alle nicht erfüllten Bedingungen, z. B. „✗ 40 Jahre, nicht schwerbehindert“
            was = _nicht_erfuellt(person, heute, e, felder)
            p.personen.append((name, f"✗ {was}" if was else "✗"))
            p.fehlt.append(f"{name}: {was}" if was else name)
        erfuellt.append(womit)
    if not erfuellt:
        nein = unklar = False
    elif e.verlaengern_regel == KundenEinstellungen.Verlaengern.ALLE:
        nein, unklar = "" in erfuellt, None in erfuellt
        text = "nicht alle Personen erfüllen eine Bedingung"
    else:
        erfuellt_eine = any(erfuellt)
        nein, unklar = not erfuellt_eine and None not in erfuellt, not erfuellt_eine
        text = "keine Person erfüllt eine Bedingung"
    if nein:
        p.ergebnis = NEIN
        p.gruende.append(text[0].upper() + text[1:])
    elif unklar and p.ergebnis == OK:
        p.ergebnis = UNKLAR
        p.gruende.append("Geburtsdatum fehlt – bitte selbst prüfen")
    _einkommen_pruefen(p, h, e)
    return p


EINKOMMEN_NEIN = "Einkommensart"


def _einkommen_pruefen(p: Pruefung, h: Haushalt, e: KundenEinstellungen) -> None:
    """Zusätzlich zur Bedingung je Person (und nicht statt ihrer): Sind Einkommensarten gewählt,
    muss der Haushalt eine davon haben (z. B. Bürgergeld, Wohngeld)."""
    arten = {a.pk for a in e.verlaengern_einkommensarten.all()}
    if not arten or h.einkommensart_id in arten:
        return
    if h.einkommensart_id is None:
        if p.ergebnis == OK:
            p.ergebnis = UNKLAR
        p.gruende.append("Einkommensart fehlt – bitte selbst prüfen")
        return
    p.ergebnis = NEIN
    p.gruende.append(f"{EINKOMMEN_NEIN} „{h.einkommensart.bezeichnung}“ zählt nicht")
    p.fehlt.append(f"Einkommensart des Haushalts: {h.einkommensart.bezeichnung} "
                   f"(nötig: {einkommen_text(e)})")  # fmt: skip


def gemeldete(benutzer, heute: dt.date, monate: int) -> list[Pruefung]:
    """Alle Haushalte mit offener Nachricht „Ausweis verlängern“, je Haushalt einmal."""
    from apps.kunden import zugang

    e = KundenEinstellungen.laden()
    offen = list(Nachricht.objects.filter(anliegen=ANLIEGEN, erledigt_am__isnull=True)
                 .select_related("stelle").order_by("erstellt_am"))  # fmt: skip
    nummern = {n.kundennummer for n in offen}
    haushalte = (
        zugang.filtern(Haushalt.objects.all(), benutzer)
        .filter(kundennummer__in=nummern)
        .select_related("einkommensart", "kundengruppe")
        .prefetch_related("personen", "sperren")
        .order_by("kundennummer")
    )
    ergebnis = []
    for h in haushalte:
        p = pruefen(h, heute, monate, e)
        p.nachrichten = [n for n in offen if n.kundennummer == h.kundennummer]
        ergebnis.append(p)
    return ergebnis


def ausfuehren(benutzer, heute: dt.date, monate: int, verlaengern: set[str],
               ablehnen: set[str], an_stelle: bool = False) -> tuple[int, int]:  # fmt: skip
    """Verlängert die gewählten gemeldeten Haushalte; bei nicht verlängerbaren je nach Einstellung
    Notiz an die Ausgabestelle oder Pause. In beiden Fällen ist die Meldung danach erledigt und
    die gemeldete Notiz gestrichen. ``an_stelle``: die Notiz zur Ablehnung auch auf die Startseite
    der Ausgabestelle (nur auf ausdrücklichen Wunsch). Ergebnis: (verlängert, abgelehnt)."""
    e = KundenEinstellungen.laden()
    A = KundenEinstellungen.Ablehnung
    von = benutzer.get_username()
    jetzt = timezone.now()
    v = ab = 0
    with transaction.atomic():
        for p in gemeldete(benutzer, heute, monate):
            h = p.haushalt
            vorher = historie.schnappschuss(h)
            if p.nummer in verlaengern and p.ergebnis != NEIN:
                h.ausweis_gueltig_bis = p.neu_bis
                zusatz = "Ausweis verlängert (Sammel-Verlängerung)"
                v += 1
            elif (p.nummer in ablehnen and p.ergebnis == NEIN
                  and e.verlaengern_ablehnung != A.ANZEIGEN):  # fmt: skip
                bis = None
                if e.verlaengern_ablehnung == A.PAUSIEREN:
                    h.status = Haushalt.Status.PAUSIERT
                    bis = monat_plus(heute, e.verlaengern_sonst_pausieren_monate, False)
                Notiz.objects.create(kundennummer=h.kundennummer, benutzer=benutzer,
                                     verfasst_von=von[:100], an_stelle=an_stelle,
                                     text=ablehnung_notiz(p, e, bis)[:1000])  # fmt: skip
                zusatz = ("Nicht verlängert (Sammel-Verlängerung)" if bis is None
                          else f"Nicht verlängert, pausiert bis {bis:%d.%m.%Y}")  # fmt: skip
                ab += 1
            else:
                continue
            gemeldete_notizen_streichen(p)
            h.geaendert_am, h.geaendert_von = jetzt, von
            h.save()
            gruppen.pruefen(h, heute)  # ohne gültigen Ausweis keine Kundengruppe (ADR 0061)
            historie.festhalten(h.kundennummer, vorher, historie.schnappschuss(h),
                                quelle=HaushaltEreignis.Quelle.BEARBEITUNG, von=von,
                                zusatz=zusatz)  # fmt: skip
            Nachricht.objects.filter(pk__in=[n.pk for n in p.nachrichten]).update(
                erledigt_am=jetzt, erledigt_von=von)  # fmt: skip
    return v, ab
