from django import template
from django.core.exceptions import FieldDoesNotExist

register = template.Library()

M2M_OPERATIONEN = {"add": "hinzugefügt", "delete": "entfernt", "clear": "alle entfernt"}


def _feldname(modell, feld: str) -> str:
    try:
        return str(modell._meta.get_field(feld).verbose_name)
    except (AttributeError, FieldDoesNotExist):
        return feld


@register.filter
def aenderungen(eintrag) -> list[tuple[str, str]]:
    """Bereitet die Änderungen eines Protokolleintrags als (Feld, Text) auf."""
    modell = eintrag.content_type.model_class()
    anzeige = eintrag.changes_display_dict
    ergebnis = []
    for feld, werte in eintrag.changes_dict.items():
        name = _feldname(modell, feld)
        if isinstance(werte, dict) and werte.get("type") == "m2m":
            operation = M2M_OPERATIONEN.get(werte.get("operation"), werte.get("operation"))
            objekte = ", ".join(map(str, werte.get("objects", [])))
            ergebnis.append((name, f"{operation}: {objekte}"))
        else:
            alt, neu = anzeige.get(name, werte)
            ergebnis.append((name, f"{alt} → {neu}"))
    return ergebnis
