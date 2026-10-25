"""Musterdaten für Test-Installationen. Alles erfunden."""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.urls import reverse

from apps.antraege.models import Antrag
from apps.core.models import TafelEinstellungen
from apps.kunden.models import Ausgabestelle, Haushalt, Kundengruppe

pytestmark = pytest.mark.django_db


def test_musterdaten_ersetzen_und_lassen_stehen(admin, admin_client, capsys):
    t = TafelEinstellungen.laden()
    t.name = "Tafel Musterstadt e.V."
    t.save()
    stelle = Ausgabestelle.objects.create(name="Zentrale", strasse="Hofweg 1")
    Kundengruppe.objects.create(name="Zentrale Fr 13:30", ausgabestelle=stelle, wochentage="Fr")
    alt = Haushalt.objects.create(kundennummer="99999")
    with pytest.raises(CommandError, match="--ja"):
        call_command("musterdaten")
    call_command("musterdaten", "--ja", "--passwort", "Muster-Passwort-123", "--haushalte", "30")
    ausgabe = capsys.readouterr().out
    assert "Haushalte: 30" in ausgabe and "Muster-Passwort-123" in ausgabe
    assert not Haushalt.objects.filter(pk=alt.pk).exists() and Haushalt.objects.count() == 30
    assert TafelEinstellungen.laden().name == "Tafel Musterstadt e.V."
    stelle.refresh_from_db()
    assert stelle.strasse == "Hofweg 1" and Ausgabestelle.objects.count() == 1
    assert get_user_model().objects.filter(pk=admin.pk).exists()  # eigenes Konto bleibt
    konten = get_user_model().objects.filter(username__startswith="muster-")
    assert konten.count() == 12 and konten.get(username="muster-gesperrt").is_active is False
    assert konten.get(username="muster-ausgabe-stelle").ausgabestellen.get() == stelle
    assert konten.get(username="muster-buero").check_password("Muster-Passwort-123")
    assert Antrag.objects.count() == 18
    # erneut ausführbar, ohne Doppelte
    call_command("musterdaten", "--ja", "--haushalte", "5")
    assert Haushalt.objects.count() == 5 and konten.count() == 12
    # Seiten funktionieren mit den Daten
    for name in ("kunden:uebersicht", "statistik:uebersicht", "adressen:liste", "spenden:liste",
                 "mitglieder:liste", "antraege:liste", "ausgabe:kasse"):  # fmt: skip
        assert admin_client.get(reverse(name)).status_code == 200, name
