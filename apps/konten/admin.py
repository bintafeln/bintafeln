from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.konten.models import Benutzer


@admin.register(Benutzer)
class BenutzerAdmin(UserAdmin):
    pass
