"""Arbeitszeit am Aushang-Monitor stempeln (ADR 0123): mit Name und persönlicher PIN direkt am
Monitor oder über einen QR-Code, der sich laufend ändert und nur kurz gilt. So lässt sich nur
vor Ort stempeln, ohne ein eigenes Stempel-Gerät."""

from django.core import signing

from apps.aushang import pin
from apps.aushang.models import Aushang
from apps.core import module

SALZ = "aushang.stempeln"
GILT_SEKUNDEN = 90  # so lange lässt sich ein gezeigter QR-Code einlösen
WECHSEL_SEKUNDEN = 30  # so oft holt der Monitor einen neuen Code


def an(aushang: Aushang) -> bool:
    """Ob an diesem Monitor gestempelt wird: wie eingestellt; in der Vorgabe nur an Monitoren
    mit einer Seite, die das vorsieht (Dienstplan). Nie, wenn die Tafel keine Arbeitszeit
    erfasst oder kein Weg (PIN, QR-Code) eingeschaltet ist."""
    from apps.personal.models import ArbeitszeitEinstellungen

    if not (aushang.stempeln_pin or aushang.stempeln_qr):
        return False
    if aushang.stempeln == Aushang.Stempeln.AUS:
        return False
    if aushang.stempeln == Aushang.Stempeln.STANDARD:
        arten = module.aushangseiten()
        if not any(getattr(arten.get(s.art), "stempeln_standard", False)
                   for s in aushang.seiten.all()):  # fmt: skip
            return False
    return ArbeitszeitEinstellungen.laden().aktiv or bool(personen())


def personen() -> list:
    """Alle, für die Arbeitszeit erfasst wird (aktive Konten von Personen), nach Name."""
    from django.contrib.auth import get_user_model

    from apps.personal import arbeitszeit

    konten = (get_user_model().objects.filter(is_active=True, stelle__isnull=True)
              .order_by("last_name", "first_name", "username"))  # fmt: skip
    return [k for k in konten if arbeitszeit.erfasst(k)]


def mit_pin() -> list[tuple[int, str]]:
    """[(pk, Name)] derer, die am Monitor mit PIN stempeln können."""
    haben = pin.mit_pin()
    return [(k.pk, str(k)) for k in personen() if k.pk in haben]


def marke(aushang: Aushang) -> str:
    """Kurzlebige, unterschriebene Marke für den QR-Code dieses Monitors."""
    return signing.dumps({"a": aushang.pk}, salt=SALZ)


def einloesen(marke_text: str) -> Aushang | None:
    """Der Monitor zu einer noch gültigen Marke – nur wenn dort (weiter) per QR-Code gestempelt
    wird; sonst None."""
    try:
        daten = signing.loads(marke_text, salt=SALZ, max_age=GILT_SEKUNDEN)
    except signing.BadSignature:
        return None
    aushang = Aushang.objects.filter(pk=daten.get("a"), aktiv=True).first()
    if aushang is None or not aushang.stempeln_qr or not an(aushang):
        return None
    return aushang
