from apps.core.models import TafelEinstellungen
from apps.konten.rollen import rollen_von


def tafel(request):
    return {
        "tafel": TafelEinstellungen.laden(),
        "rollen": rollen_von(request.user) if hasattr(request, "user") else set(),
    }
