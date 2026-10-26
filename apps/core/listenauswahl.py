"""Auswahlkästchen in Listen: Export und Druck nehmen nur die angehakten Zeilen (GET „id“), ohne
Haken alle. Gegenstück zu ``{% auswahl_formular %}`` und ``static/js/auswahl.js``."""


def ids(request) -> list[int]:
    return [int(x) for x in request.GET.getlist("id") if x.isdigit()]


def filtern(request, qs):
    gewaehlt = ids(request)
    return qs.filter(pk__in=gewaehlt) if gewaehlt else qs
