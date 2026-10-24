"""Rollen und Rechte von bintafeln (ADR 0033).

Jede Rolle ist eine Django-Gruppe mit einer ``konten.Rolle``, die ihre Rechte festlegt
(Katalog in ``apps.konten.rechte``). Ansichten prüfen Rechte mit ``recht_erforderlich`` bzw.
``hat_recht``, nie Rollennamen. Die Rolle Admin hat immer alle Rechte; ebenso Superuser.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from apps.konten import rechte as katalog

ADMIN = "Admin"
# Mitgelieferte Rollen; Namen nur noch für Vorgaben, Demo und Tests.
BUERO = "Büro"
AUSGABE = "Ausgabe"
KIOSK = "Kiosk"
FAHRER = "Fahrer"
BEIFAHRER = "Beifahrer"
PERSONAL = "Personal"

# Mitgelieferte Rollen: Reihenfolge, Zwei-Faktor Pflicht, Belehrung (IfSG), Führerschein
MITGELIEFERT = {
    ADMIN: (0, True, False, False),
    BUERO: (10, True, False, False),
    AUSGABE: (20, False, True, False),
    KIOSK: (30, False, False, False),
    FAHRER: (40, False, True, True),
    BEIFAHRER: (50, False, True, False),
    PERSONAL: (60, True, False, False),
}


def vorgaben_wiederherstellen() -> None:
    """Legt die mitgelieferten Rollen mit ihren Vorgaben an bzw. setzt sie zurück (Demo)."""
    from django.contrib.auth.models import Group

    from apps.konten.models import Rolle

    for name, (reihenfolge, zwei_faktor, belehrung, fuehrerschein) in MITGELIEFERT.items():
        gruppe, _ = Group.objects.get_or_create(name=name)
        Rolle.objects.update_or_create(gruppe=gruppe, defaults={
            "rechte": list(katalog.VORGABEN.get(name, [])), "reihenfolge": reihenfolge,
            "zwei_faktor_pflicht": zwei_faktor, "braucht_belehrung": belehrung,
            "braucht_fuehrerschein": fuehrerschein,
        })  # fmt: skip


def alle_rollen():
    """Alle Rollen in Anzeigereihenfolge."""
    from apps.konten.models import Rolle

    return list(Rolle.objects.select_related("gruppe"))


def rollen_von(benutzer) -> set[str]:
    """Namen der Rollen eines Kontos (Superuser zählen als Admin)."""
    if not benutzer.is_authenticated:
        return set()
    namen = set(benutzer.groups.values_list("name", flat=True))
    if benutzer.is_superuser:
        namen.add(ADMIN)
    return namen


def ist_admin(benutzer) -> bool:
    return ADMIN in rollen_von(benutzer)


def rechte_von(benutzer) -> frozenset[str]:
    """Rechte eines Kontos, einmal je Anfrage berechnet (am Benutzerobjekt zwischengespeichert)."""
    if not getattr(benutzer, "is_authenticated", False):
        return frozenset()
    gemerkt = getattr(benutzer, "_bintafeln_rechte", None)
    if gemerkt is not None:
        return gemerkt
    from apps.konten.models import Rolle

    if benutzer.is_superuser:
        ergebnis = katalog.ALLE
    else:
        rollen = Rolle.objects.filter(gruppe__user=benutzer).select_related("gruppe")
        if any(r.ist_admin for r in rollen):
            ergebnis = katalog.ALLE
        else:
            ergebnis = frozenset(c for r in rollen for c in r.rechte if c in katalog.ALLE)
    benutzer._bintafeln_rechte = ergebnis
    return ergebnis


def rechte_vergessen(benutzer) -> None:
    """Nach dem Ändern von Rollen im selben Ablauf."""
    if hasattr(benutzer, "_bintafeln_rechte"):
        del benutzer._bintafeln_rechte


def hat_recht(benutzer, *codes: str) -> bool:
    """Wahr, wenn das Konto mindestens eines der Rechte hat."""
    unbekannt = set(codes) - katalog.ALLE
    if unbekannt:
        raise ValueError(f"Unbekannte Rechte: {', '.join(sorted(unbekannt))}")
    return bool(rechte_von(benutzer) & set(codes))


def recht_erforderlich(*codes: str):
    """Decorator: Ansicht nur für angemeldete Konten mit mindestens einem der Rechte."""
    unbekannt = set(codes) - katalog.ALLE
    if unbekannt:
        raise ValueError(f"Unbekannte Rechte: {', '.join(sorted(unbekannt))}")

    def dekorator(ansicht):
        @wraps(ansicht)
        @login_required
        def pruefen(request, *args, **kwargs):
            if not hat_recht(request.user, *codes):
                raise PermissionDenied
            return ansicht(request, *args, **kwargs)

        return pruefen

    return dekorator


def darf_mitarbeitende_verwalten(benutzer) -> bool:
    return hat_recht(benutzer, "mitarbeitende.verwalten")
