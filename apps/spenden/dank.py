"""Dankesbriefe an Spender (ADR 0056).

Je Spender ein Brief aus einer Serienbrief-Vorlage. Beigelegt werden auf Wunsch die
Zuwendungsbestätigungen aus bintafeln (fehlende werden dabei ausgestellt) und hochgeladene Belege
aus anderen Programmen, z. B. dem Vereinsportal (``SpendenBeleg``). Einfach- und Mehrfachspender
lassen sich getrennt auswählen. Nach dem Erstellen trägt jede Spende ``bedankt_am``.
"""

import io
import re
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from apps.core import privatdateien
from apps.serienbriefe import empfaenger as emp
from apps.serienbriefe import gestaltung
from apps.serienbriefe.brief import briefe_pdf
from apps.spenden import bestaetigung as bst
from apps.spenden.models import Spende, SpendenBeleg, Zuwendungsbestaetigung

ARTEN = [("alle", "alle Spender"), ("einfach", "nur Einfachspender (eine Spende im Jahr)"),
         ("mehrfach", "nur Mehrfachspender (mehrere Spenden im Jahr)")]  # fmt: skip


@dataclass
class Dank:
    adresse: object
    spenden: list = field(default_factory=list)
    anzahl_im_jahr: int = 0
    belege: list = field(default_factory=list)
    bestaetigungen: list = field(default_factory=list)

    @property
    def per_mail(self) -> bool:
        a = self.adresse
        return bool(a.email and a.einwilligung_email)


def auswahl(jahr: int, art: str = "alle", nur_offen: bool = True) -> list[Dank]:
    """Spender des Jahres mit ihren (noch nicht bedankten) Spenden."""
    alle = Spende.objects.filter(datum__year=jahr).select_related("adresse", "bestaetigung")
    anzahl: dict[int, int] = {}
    for s in alle:
        anzahl[s.adresse_id] = anzahl.get(s.adresse_id, 0) + 1
    gewaehlt = alle.filter(bedankt_am__isnull=True) if nur_offen else alle
    danke: dict[int, Dank] = {}
    for s in gewaehlt.order_by("adresse__organisation", "adresse__nachname", "datum"):
        n = anzahl[s.adresse_id]
        if (art == "einfach" and n != 1) or (art == "mehrfach" and n < 2):
            continue
        d = danke.setdefault(s.adresse_id, Dank(s.adresse, anzahl_im_jahr=n))
        d.spenden.append(s)
    belege = SpendenBeleg.objects.filter(adresse_id__in=danke, jahr=jahr)
    for b in belege.order_by("hochgeladen_am"):
        danke[b.adresse_id].belege.append(b)
    for d in danke.values():
        d.bestaetigungen = _bestaetigungen(d)
    return list(danke.values())


def _bestaetigungen(d: Dank) -> list[Zuwendungsbestaetigung]:
    gesehen, liste = set(), []
    for s in d.spenden:
        if s.bestaetigt and s.bestaetigung_id not in gesehen:
            gesehen.add(s.bestaetigung_id)
            liste.append(s.bestaetigung)
    return liste


def fehlende_ausstellen(danke: list[Dank], jahr: int, von: str) -> list[str]:
    """Stellt für offene Geldspenden Bestätigungen aus; liefert Fehlermeldungen."""
    fehler = []
    for d in danke:
        if not bst.offene_geldspenden(d.adresse, jahr).exists():
            continue
        try:
            bst.geld_ausstellen(d.adresse, jahr, von)
        except bst.BestaetigungsFehler as grund:
            fehler.append(str(grund))
            if "fehlen noch Angaben" in str(grund):
                break  # gilt für alle gleich
        d.spenden = list(Spende.objects.filter(pk__in=[s.pk for s in d.spenden])
                         .select_related("bestaetigung").order_by("datum"))  # fmt: skip
        d.bestaetigungen = _bestaetigungen(d)
    return fehler


def werte(d: Dank, jahr: int) -> emp.Empfaenger:
    daten = ", ".join(f"{s.datum:%d.%m.%Y}" for s in d.spenden)
    return emp._aus_adresse(d.adresse, jahr, anzahl_spenden=d.anzahl_im_jahr,
                            spendendaten=daten)  # fmt: skip


def anlagen(d: Dank, mit_bestaetigungen: bool, mit_belegen: bool) -> list[tuple[str, bytes]]:
    """PDF-Anlagen eines Spenders als (Dateiname, Inhalt)."""
    liste = []
    if mit_bestaetigungen:
        for b in d.bestaetigungen:
            liste.append((f"Zuwendungsbestaetigung-{b.nummer}.pdf", bst.pdf([b])))
    if mit_belegen:
        for b in d.belege:
            inhalt = privatdateien.lesen(SpendenBeleg.ORDNER, b.datei)
            if inhalt:
                liste.append((_dateiname(b.dateiname), inhalt))
    return liste


def _dateiname(name: str) -> str:
    name = re.sub(r"[^\w.\-]+", "_", name).strip("._") or "Beleg"
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"


def _anhaengen(schreiber: PdfWriter, inhalt: bytes) -> bool:
    try:
        schreiber.append(PdfReader(io.BytesIO(inhalt)))
    except (PdfReadError, ValueError, OSError):
        return False
    return True


def briefe(danke: list[Dank], vorlage, jahr: int, mit_bestaetigungen=True, mit_belegen=True,
           allgemein=None) -> tuple[bytes, list[str]]:  # fmt: skip
    """Ein PDF: je Spender Brief und Anlagen hintereinander. Liefert (PDF, Warnungen)."""
    allgemein = allgemein or {}
    schreiber, warnungen = PdfWriter(), []
    for d in danke:
        e = werte(d, jahr)
        brief = briefe_pdf([(e.anschrift, *gestaltung.brief(vorlage, e, allgemein))], vorlage)
        _anhaengen(schreiber, brief)
        for name, inhalt in anlagen(d, mit_bestaetigungen, mit_belegen):
            if not _anhaengen(schreiber, inhalt):
                warnungen.append(f"{d.adresse.name}: „{name}“ ist kein lesbares PDF.")
    puffer = io.BytesIO()
    schreiber.write(puffer)
    return puffer.getvalue(), warnungen


@transaction.atomic
def vermerken(danke: list[Dank], mit_belegen: bool) -> None:
    heute = timezone.localdate()
    Spende.objects.filter(pk__in=[s.pk for d in danke for s in d.spenden]).update(bedankt_am=heute)
    if mit_belegen:
        SpendenBeleg.objects.filter(pk__in=[b.pk for d in danke for b in d.belege]).update(
            beigelegt_am=heute
        )


# --- Belege hochladen ---------------------------------------------------------------------------


def _ziffern(text: str) -> str:
    """Längste Ziffernfolge ohne führende Nullen, z. B. „Spendenbeleg_000123.pdf“ -> „123“."""
    folgen = re.findall(r"\d+", text or "")
    return max(folgen, key=len).lstrip("0") if folgen else ""


def zuordnen(dateiname: str):
    """Spende mit passender Belegnummer (Ziffern im Dateinamen) oder None."""
    ziffern = _ziffern(dateiname.rsplit(".", 1)[0])
    if not ziffern:
        return None
    treffer = [s for s in Spende.objects.exclude(belegnummer="").select_related("adresse")
               if _ziffern(s.belegnummer) == ziffern]  # fmt: skip
    return treffer[0] if len(treffer) == 1 else None


def hochladen(datei, jahr: int, von: str) -> SpendenBeleg:
    """Speichert ein PDF verschlüsselt und ordnet es über die Belegnummer zu, wenn möglich."""
    name = privatdateien.speichern(SpendenBeleg.ORDNER, datei, typen=("application/pdf",),
                                   max_mb=10)  # fmt: skip
    spende = zuordnen(datei.name)
    return SpendenBeleg.objects.create(
        adresse=spende.adresse if spende else None, spende=spende,
        jahr=spende.datum.year if spende else jahr, dateiname=datei.name[:200], datei=name,
        hochgeladen_von=von,
    )  # fmt: skip
