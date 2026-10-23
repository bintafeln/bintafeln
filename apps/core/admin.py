from django.contrib import admin

from apps.core.models import TafelEinstellungen


@admin.register(TafelEinstellungen)
class TafelEinstellungenAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not TafelEinstellungen.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
