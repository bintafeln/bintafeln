from django.contrib.auth import get_user_model
from django.shortcuts import redirect

FREIE_PFADE = ("/einrichtung/", "/static/", "/media/", "/healthz/")


def admin_existiert() -> bool:
    return get_user_model().objects.filter(is_superuser=True, is_active=True).exists()


class EinrichtungMiddleware:
    """Leitet auf die Einrichtungsseite um, solange kein aktiver Admin existiert."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(FREIE_PFADE) and not admin_existiert():
            return redirect("core:einrichtung")
        return self.get_response(request)
