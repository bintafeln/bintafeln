from django.db import migrations, models


def recht_zu_rollen(apps, schema_editor):
    """Bisher: sichtbar mit einem Recht. Jetzt: sichtbar für Rollen – also alle Rollen, die das
    Recht heute haben. Hat es keine (nur Admins durften), bleibt der Link bei den Admins."""
    Link = apps.get_model("links", "Link")
    Rolle = apps.get_model("konten", "Rolle")
    Group = apps.get_model("auth", "Group")
    rollen = list(Rolle.objects.select_related("gruppe"))
    for link in Link.objects.exclude(recht=""):
        gruppen = [r.gruppe for r in rollen if link.recht in (r.rechte or [])]
        if not gruppen:
            gruppen = [Group.objects.get_or_create(name="Admin")[0]]
        link.rollen.set(gruppen)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("konten", "0009_rollen_und_rechte"),
        ("links", "0002_bild"),
    ]

    operations = [
        migrations.AddField(
            model_name="link",
            name="rollen",
            field=models.ManyToManyField(
                blank=True,
                help_text="Nichts angehakt = alle Angemeldeten; sonst nur, wer eine der Rollen "
                "hat. Admins sehen immer alle Links.",
                related_name="+",
                to="auth.group",
                verbose_name="Sichtbar für",
            ),
        ),
        # zurück: die Rollen fallen weg, das frühere Recht lässt sich nicht wiederherstellen
        migrations.RunPython(recht_zu_rollen, migrations.RunPython.noop),
        migrations.RemoveField(model_name="link", name="recht"),
    ]
