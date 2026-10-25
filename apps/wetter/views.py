from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from apps.wetter import wetter


@never_cache
@login_required
def kopf(request):
    """Wetter für die Kopfzeile (wird per HTMX nachgeladen)."""
    stelle = wetter.stelle_fuer(request.user)
    return render(request, "wetter/_kopf.html", {"wetter": wetter.aktuell(stelle)})
