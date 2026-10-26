from django.core.files.storage import default_storage
from django.db import migrations

GRENZE = 400 * 1024  # kleinere Bilder bleiben, wie sie sind


def verkleinern(apps, schema_editor):
    """Große Hintergrundbilder und Logos verkleinern, damit Seiten schneller laden. Das
    Originalbild bleibt als Datei liegen (nichts wird gelöscht); nur der Verweis zeigt auf die
    kleinere Fassung."""
    from apps.core import bilder

    e = apps.get_model("core", "TafelEinstellungen").objects.filter(pk=1).first()
    if e is None:
        return
    geaendert = []
    for feld, kante, transparenz in (("hintergrund_anmeldung", bilder.HINTERGRUND_KANTE, False),
                                     ("hintergrund", bilder.HINTERGRUND_KANTE, False),
                                     ("logo", bilder.LOGO_KANTE, True)):  # fmt: skip
        datei = getattr(e, feld)
        if not datei or not default_storage.exists(datei.name):
            continue
        if default_storage.size(datei.name) <= GRENZE:
            continue
        with default_storage.open(datei.name, "rb") as f:
            neu = bilder.verkleinern(f, kante, transparenz=transparenz)
        if neu is None or neu.size >= default_storage.size(datei.name):
            continue
        ordner = datei.name.rsplit("/", 1)[0]
        name = default_storage.save(f"{ordner}/{neu.name}", neu)
        setattr(e, feld, name)
        geaendert.append(feld)
    if geaendert:
        e.save(update_fields=geaendert)


class Migration(migrations.Migration):
    dependencies = [("core", "0013_module")]

    operations = [migrations.RunPython(verkleinern, migrations.RunPython.noop)]
