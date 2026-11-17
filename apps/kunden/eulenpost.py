"""Post der Verwaltung an die Ausgabestellen (ADR 0142).

Die Verwaltung schreibt an eine, mehrere oder alle Ausgabestellen. Bei der Ausgabestelle fliegt
eine Eule mit einem Brief in die Kopfzeile und bleibt dort sitzen, bis die Post gelesen ist
(``static/js/eulenpost.js``); die Kopfzeile fragt jede Minute nach. „Wichtige“ Post legt
zusätzlich einen Hinweis über die Seite. Gelesen ist Post je Ausgabestelle, sobald dort jemand
„Gelesen“ bestätigt; die Verwaltung sieht, wer wann gelesen hat.
"""

from django.db import transaction
from django.utils import timezone

from apps.kunden.models import Ausgabestelle, PostEmpfang, Rundschreiben


def _name(benutzer) -> str:
    return (benutzer.get_full_name() or benutzer.get_username())[:150]


@transaction.atomic
def schreiben(stellen, benutzer, betreff: str, text: str, wichtig: bool = False) -> Rundschreiben:
    r = Rundschreiben.objects.create(betreff=betreff.strip()[:200], text=text.strip()[:4000],
                                     wichtig=wichtig, von=_name(benutzer),
                                     benutzer=benutzer)  # fmt: skip
    PostEmpfang.objects.bulk_create([PostEmpfang(rundschreiben=r, stelle=s) for s in stellen])
    return r


def ungelesen(stelle):
    """Ungelesene Post an diese Ausgabestelle, älteste zuerst."""
    if stelle is None:
        return PostEmpfang.objects.none()
    return (PostEmpfang.objects.filter(stelle=stelle, gelesen_am__isnull=True)
            .select_related("rundschreiben").order_by("rundschreiben__erstellt_am"))  # fmt: skip


def stand(stelle) -> dict:
    """Was die Kopfzeile braucht: Zahl der ungelesenen und die älteste wichtige (für den
    Hinweis über der Seite)."""
    offen = list(ungelesen(stelle))
    wichtig = next((e for e in offen if e.rundschreiben.wichtig), None)
    return {"zahl": len(offen), "wichtig": wichtig,
            "schluessel": ",".join(str(e.pk) for e in offen)}  # fmt: skip


def postfach(stelle, anzahl: int = 30):
    if stelle is None:
        return PostEmpfang.objects.none()
    return (PostEmpfang.objects.filter(stelle=stelle).select_related("rundschreiben")
            .order_by("-rundschreiben__erstellt_am")[:anzahl])  # fmt: skip


def gelesen(empfang: PostEmpfang, benutzer) -> None:
    if empfang.gelesen_am is None:
        empfang.gelesen_am, empfang.gelesen_von = timezone.now(), _name(benutzer)
        empfang.save(update_fields=["gelesen_am", "gelesen_von"])


def gesendet(anzahl: int = 30):
    """Die zuletzt geschriebene Post mit Lesestand je Ausgabestelle (für die Verwaltung)."""
    return Rundschreiben.objects.prefetch_related("empfaenge__stelle")[:anzahl]


def waehlbare_stellen():
    return Ausgabestelle.objects.filter(aktiv=True).order_by("name")
