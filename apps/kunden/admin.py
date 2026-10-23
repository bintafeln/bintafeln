from django.contrib import admin

from apps.kunden import models

for modell in (
    models.Ausgabestelle,
    models.Kundengruppe,
    models.Einkommensart,
    models.Zusatzfeld,
):
    admin.site.register(modell)
