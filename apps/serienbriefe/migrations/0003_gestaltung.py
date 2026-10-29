import re
from html import escape, unescape

from django.db import migrations, models


def _ist_html(text):
    return bool(re.search(r"<[a-zA-Z/][^>]*>", text or ""))


def in_absaetze(apps, schema_editor):
    """Vorlagen aus reinem Text (Absätze durch Leerzeilen) werden zu HTML-Absätzen (ADR 0088)."""
    for v in apps.get_model("serienbriefe", "Vorlage").objects.all():
        if _ist_html(v.text):
            continue
        absaetze = [a.strip() for a in v.text.replace("\r\n", "\n").split("\n\n")]
        v.text = "".join(
            "<p>" + escape(a, quote=False).replace("\n", "<br>") + "</p>" for a in absaetze if a
        )
        v.save(update_fields=["text"])


def als_text(apps, schema_editor):
    """Rückweg für ältere Versionen: HTML wieder als Text mit Leerzeilen zwischen Absätzen."""
    for v in apps.get_model("serienbriefe", "Vorlage").objects.all():
        if not _ist_html(v.text):
            continue
        text = re.sub(r"(?i)<br\s*/?>", "\n", v.text)
        text = re.sub(r"(?i)<li[^>]*>", "\n- ", text)
        text = re.sub(r"(?i)</(p|div|h[1-6]|ul|ol|blockquote)>", "\n\n", text)
        text = unescape(re.sub(r"<[^>]+>", "", text))
        v.text = re.sub(r"\n{3,}", "\n\n", text).strip()
        v.save(update_fields=["text"])



class Migration(migrations.Migration):

    dependencies = [
        ("serienbriefe", "0002_vorlagen"),
    ]

    operations = [
        migrations.AddField(
            model_name="vorlage",
            name="briefkopf",
            field=models.BooleanField(
                default=True,
                help_text="Logo, Name, Anschrift und Kontakt der Tafel oben rechts (aus den Tafel-Einstellungen). Aus, wenn Sie auf eigenes Briefpapier drucken.",
                verbose_name="Briefkopf",
            ),
        ),
        migrations.AddField(
            model_name="vorlage",
            name="fusszeile",
            field=models.TextField(
                blank=True,
                help_text="Steht unten auf jeder Seite des Briefs und unter jeder E-Mail, z. B. Bankverbindung, Vereinsregister, Vorstand. Leer = keine Fußzeile.",
                verbose_name="Fußzeile",
            ),
        ),
        migrations.AlterField(
            model_name="vorlage",
            name="text",
            field=models.TextField(
                help_text="Gestalten wie in einem Schreibprogramm. Platzhalter aus der Liste „Platzhalter“ in den Text ziehen oder antippen (fügt sie an der Schreibmarke ein); im Reiter HTML stehen sie als {anrede}, {spendensumme} usw.",
                verbose_name="Text",
            ),
        ),
        migrations.RunPython(in_absaetze, als_text),
    ]
