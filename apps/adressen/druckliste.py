"""Druckliste für Mitarbeitende und Adressbuch-Personen (ADR 0044/0097).

Eine Seite, auf der man sich aus dem Adressbuch (Personen) eine Liste zusammenstellt – nach
Beschäftigung/Rolle/Ausgabestelle/Status gefiltert, einzelne Personen an- oder abgewählt, Spalten
nach Wunsch – und als PDF in A4 oder A3, hoch oder quer druckt. Mitarbeitende sind zugleich
Adressbuch-Personen (ADR 0097); die Zusatzangaben (Rollen, Ausgabestellen, Beschäftigung, „Dabei
seit“, Personalnummer, Notfallkontakt) stehen am verknüpften Konto und nur Berechtigten offen.
"""

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from reportlab.lib.pagesizes import A3, A4, landscape

from apps.adressen.models import Adresse
from apps.core.pdf import Pdf

# (Schlüssel, Überschrift, nur_mitarbeitende): Spalten nur mit Mitarbeiter-Bezug stehen erst mit
# dem Recht „mitarbeitende.verwalten“ zur Wahl, weil sie Angaben vom Konto zeigen.
SPALTEN = [
    ("nachname", "Nachname", False),
    ("vorname", "Vorname", False),
    ("anrede", "Anrede", False),
    ("strasse", "Straße", False),
    ("plz", "PLZ", False),
    ("ort", "Ort", False),
    ("telefon", "Telefon", False),
    ("mobil", "Handy", False),
    ("email", "E-Mail", False),
    ("geburtsdatum", "Geburtsdatum", False),
    ("rollen", "Rollen", True),
    ("ausgabestellen", "Ausgabestellen", True),
    ("beschaeftigung", "Beschäftigung", True),
    ("eintritt", "Dabei seit", True),
    ("personalnummer", "Personalnummer", True),
    ("notfall", "Notfallkontakt", True),
]
SPALTEN_FEST: set[str] = {"nachname"}  # der Nachname ist immer dabei

BESCHAEFTIGUNG = {"ehrenamtlich": "ehrenamtlich", "angestellt": "fest"}


def spalten_katalog(darf_mitarbeit: bool) -> list[tuple[str, str]]:
    """(Schlüssel, Überschrift) der wählbaren Spalten; Mitarbeiter-Spalten nur mit Recht."""
    return [(k, t) for k, t, nur in SPALTEN if darf_mitarbeit or not nur]


def filtern(request, darf_mitarbeit: bool):
    """Adressbuch-Personen nach den Filtern der Seite. Ohne das Mitarbeiter-Recht nur die reinen
    Personen-Angaben; die konto-bezogenen Filter werden dann nicht angewandt."""
    f = {
        "mitarbeit": request.GET.get("mitarbeit", "alle"),
        "status": request.GET.get("status", "alle"),
        # Leere Werte verwerfen: die „alle“-Option sendet rolle=/stelle= mit, getlist liefert dann
        # [""] – das wäre „wahr“ und würde auf eine leere Rolle/Stelle filtern (→ nichts).
        "rollen": [r for r in request.GET.getlist("rolle") if r],
        "stellen": [s for s in request.GET.getlist("stelle") if s],
        "suche": (request.GET.get("suche") or "").strip(),
    }
    qs = Adresse.objects.filter(art=Adresse.Art.PERSON)
    if darf_mitarbeit:
        if f["mitarbeit"] == "mitarbeitende":
            qs = qs.filter(konto__isnull=False)
        elif f["mitarbeit"] == "ohne_konto":
            qs = qs.filter(konto__isnull=True)
        elif f["mitarbeit"] in BESCHAEFTIGUNG:
            qs = qs.filter(konto__beschaeftigung=BESCHAEFTIGUNG[f["mitarbeit"]])
        if f["status"] == "aktiv":
            qs = qs.filter(konto__is_active=True)
        elif f["status"] == "archiv":
            qs = qs.filter(konto__is_active=False)
        if f["rollen"]:
            qs = qs.filter(konto__groups__name__in=f["rollen"])
        if f["stellen"]:
            qs = qs.filter(konto__ausgabestellen__pk__in=[s for s in f["stellen"] if s.isdigit()])
    else:
        f["mitarbeit"], f["status"], f["rollen"], f["stellen"] = "alle", "alle", [], []
    for wort in f["suche"].split():
        qs = qs.filter(Q(nachname__icontains=wort) | Q(vorname__icontains=wort))
    qs = (
        qs.distinct()
        .select_related("konto__stammdaten")
        .prefetch_related("konto__groups", "konto__ausgabestellen")
    )
    return f, qs.order_by("nachname", "vorname", "pk")


def _wert(a: Adresse, schluessel: str) -> str:
    konto = a.konto if a.konto_id else None
    try:
        stamm = konto.stammdaten if konto else None
    except ObjectDoesNotExist:
        stamm = None
    if schluessel == "nachname":
        return a.nachname
    if schluessel == "vorname":
        return a.vorname
    if schluessel == "anrede":
        return a.anrede
    if schluessel == "strasse":
        return a.strasse
    if schluessel == "plz":
        return a.plz
    if schluessel == "ort":
        return a.ort
    if schluessel == "telefon":
        return a.telefon
    if schluessel == "mobil":
        return a.mobil
    if schluessel == "email":
        return a.email
    if schluessel == "geburtsdatum":
        return f"{a.geburtsdatum:%d.%m.%Y}" if a.geburtsdatum else ""
    if not konto:
        return ""
    if schluessel == "rollen":
        return ", ".join(g.name for g in konto.groups.all())
    if schluessel == "ausgabestellen":
        return ", ".join(s.name for s in konto.ausgabestellen.all())
    if schluessel == "beschaeftigung":
        return konto.get_beschaeftigung_display() if konto.beschaeftigung else ""
    if not stamm:
        return ""
    if schluessel == "eintritt":
        return f"{stamm.eintritt:%d.%m.%Y}" if stamm.eintritt else ""
    if schluessel == "personalnummer":
        return str(stamm.personalnummer) if stamm.personalnummer else ""
    if schluessel == "notfall":
        return " ".join(t for t in (stamm.notfall_name, stamm.notfall_telefon) if t)
    return ""


def _seitengroesse(format_: str, quer: bool):
    groesse = A3 if format_ == "a3" else A4
    return landscape(groesse) if quer else groesse


def zeilen(adressen, spalten: list[str]) -> list[list[str]]:
    return [[_wert(a, k) for k in spalten] for a in adressen]


def pdf(titel: str, spalten: list[tuple[str, str]], adressen, format_: str, quer: bool) -> bytes:
    """Die zusammengestellte Liste als PDF in der gewählten Größe/Ausrichtung."""
    from django.utils import timezone

    doc = Pdf(titel, f"Stand {timezone.localdate():%d.%m.%Y} · {len(adressen)} "
              f"Person{'en' if len(adressen) != 1 else ''}",
              seitengroesse=_seitengroesse(format_, quer))  # fmt: skip
    kopf = [t for _, t in spalten]
    doc.tabelle(kopf, zeilen(adressen, [k for k, _ in spalten]))
    return doc.erzeugen()
