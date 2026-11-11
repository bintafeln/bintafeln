"""Modul „Übernahme aus einem anderen Programm“.

Das Modul hieß früher anders. Bestehende Installationen behalten ihre Zuordnungen: Diese
Migration benennt die alte Tabelle um, statt eine neue anzulegen, trägt das eingeschaltete Modul
in den Tafel-Einstellungen um und hält das Änderungsprotokoll zusammen. Die alten technischen
Namen stehen nur noch hier, weil die Migration sie sonst nicht finden könnte.
"""

from django.db import migrations, models

ALT_APP, ALT_MODELL = "bexat", "bexateinstellungen"
ALT_TABELLE = f"{ALT_APP}_{ALT_MODELL}"
NEU_APP, NEU_MODELL = "uebernahme", "uebernahmeeinstellungen"
NEU_TABELLE = f"{NEU_APP}_{NEU_MODELL}"


def _tabellen(schema_editor) -> set[str]:
    return set(schema_editor.connection.introspection.table_names())


def _umtragen(apps, schema_editor, von_app, von_modell, nach_app, nach_modell) -> None:
    """Eingeschaltetes Modul, Inhaltstyp (für das Änderungsprotokoll) und Migrationseintrag."""
    Tafel = apps.get_model("core", "TafelEinstellungen")
    for tafel in Tafel.objects.all():
        if von_app in (tafel.module or []):
            tafel.module = [nach_app if m == von_app else m for m in tafel.module]
            tafel.save(update_fields=["module"])
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(app_label=nach_app, model=nach_modell).delete()
    ContentType.objects.filter(app_label=von_app, model=von_modell).update(
        app_label=nach_app, model=nach_modell
    )


def vor(apps, schema_editor):
    if ALT_TABELLE in _tabellen(schema_editor):
        schema_editor.execute(
            f"ALTER TABLE {schema_editor.quote_name(ALT_TABELLE)} "
            f"RENAME TO {schema_editor.quote_name(NEU_TABELLE)}"
        )
        schema_editor.execute("DELETE FROM django_migrations WHERE app = %s", [ALT_APP])
    else:
        schema_editor.create_model(apps.get_model(NEU_APP, "UebernahmeEinstellungen"))
    _umtragen(apps, schema_editor, ALT_APP, ALT_MODELL, NEU_APP, NEU_MODELL)


def zurueck(apps, schema_editor):
    """Für das Zurückgehen auf eine ältere Version: Tabelle und Einträge wieder wie vorher."""
    schema_editor.execute(
        f"ALTER TABLE {schema_editor.quote_name(NEU_TABELLE)} "
        f"RENAME TO {schema_editor.quote_name(ALT_TABELLE)}"
    )
    schema_editor.execute(
        "INSERT INTO django_migrations (app, name, applied) VALUES (%s, %s, now())",
        [ALT_APP, "0001_initial"],
    )
    _umtragen(apps, schema_editor, NEU_APP, NEU_MODELL, ALT_APP, ALT_MODELL)


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("core", "0013_module"),
    ]

    operations = [
        # Erst nur der Stand im Programm, dann die Tabelle: umbenennen oder neu anlegen
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="UebernahmeEinstellungen",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "ausgabestellen",
                            models.JSONField(
                                blank=True,
                                default=dict,
                                help_text="Nur nötig, wenn der Export die Ausgabestellen nicht "
                                "selbst enthält. Eine Zuordnung je Zeile, z. B. „1 = Innenstadt“.",
                                verbose_name="Ausgabestellen (Nummer → Name)",
                            ),
                        ),
                        (
                            "einkommensarten",
                            models.JSONField(
                                blank=True,
                                default=dict,
                                help_text="Die Nummern stehen in der Konfiguration des bisherigen "
                                "Programms. Eine Zuordnung je Zeile, z. B. „6 = Rente“. Ohne "
                                "Eintrag bleibt die Einkommensart beim Import leer.",
                                verbose_name="Einkommensarten (Nummer → Text)",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Einstellungen für die Übernahme",
                        "verbose_name_plural": "Einstellungen für die Übernahme",
                    },
                ),
            ],
        ),
        migrations.RunPython(vor, zurueck),
    ]
