from django.apps import AppConfig


class TourenConfig(AppConfig):
    name = "apps.touren"
    label = "touren"
    verbose_name = "Touren und Stationen"

    def ready(self):
        # Stationen und ihre Einträge im Adressbuch gleichen sich in beide Richtungen ab (ADR 0184)
        from django.db.models.signals import post_save, pre_save

        from apps.adressen.models import Adresse
        from apps.kunden.models import Ausgabestelle
        from apps.touren import adressbuch, ausgabestellen
        from apps.touren.models import Station

        for modell in (Station, Adresse):
            pre_save.connect(adressbuch.vor_speichern, sender=modell,
                             dispatch_uid=f"touren-abgleich-vor-{modell.__name__}")  # fmt: skip
            post_save.connect(adressbuch.nach_speichern, sender=modell,
                              dispatch_uid=f"touren-abgleich-nach-{modell.__name__}")  # fmt: skip
        post_save.connect(ausgabestellen.nach_speichern, sender=Ausgabestelle,
                          dispatch_uid="touren-ausgabestelle-nach")  # fmt: skip
