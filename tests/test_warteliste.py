"""Modul Warteliste (ADR 0051): Status, Einladen, Termine, Abgleich, Dubletten, Streichungen."""

import datetime as dt
import re

import pytest
from django.core import mail as django_mail
from django.urls import reverse
from django.utils import timezone

from apps.antraege import auskunft
from apps.antraege.models import Antrag
from apps.core import geheimnis
from apps.core.models import MailEinstellungen, TafelEinstellungen
from apps.konten import rollen
from apps.kunden.models import Haushalt, Person, Zusatzfeld
from apps.warteliste import ablauf
from apps.warteliste.models import (
    Einladung,
    Streichung,
    Termin,
    WartelisteEinstellungen,
    Wartestand,
)

pytestmark = pytest.mark.django_db
S = Wartestand.Status


@pytest.fixture
def modul_an(admin):
    t = TafelEinstellungen.laden()
    t.module = ["warteliste"]
    t.name = "Tafel Musterstadt"
    t.save()


@pytest.fixture
def mailserver():
    m = MailEinstellungen.laden()
    m.server, m.port, m.benutzer, m.absender = "mail.example.org", 587, "tafel", "t@example.org"
    m.passwort_verschluesselt = geheimnis.verschluesseln("erfunden")
    m.save()
    return m


def antrag(vorname="Erika", nachname="Beispiel", tage=3, **mehr):
    a = Antrag.objects.create(vorname=vorname, nachname=nachname, **mehr)
    Antrag.objects.filter(pk=a.pk).update(eingegangen_am=timezone.now() - dt.timedelta(days=tage))
    a.refresh_from_db()
    return a


def ws(a):
    return Wartestand.objects.get(antrag=a)


def termin(tage=7):
    return Termin.objects.create(datum=timezone.localdate() + dt.timedelta(days=tage),
                                 von=dt.time(10), bis=dt.time(12))  # fmt: skip


# ── Status und Automatik ─────────────────────────────────────────────────────


def test_automatik_neu_wartend_und_wartezeit():
    alt, heute_neu = antrag(tage=3), antrag("Neu", "Heute", tage=0)
    ablauf.automatik()
    assert ws(alt).status == S.WARTEND and ws(heute_neu).status == S.NEU
    ablauf.status_setzen(ws(alt), S.WARTEZEIT, "Büro", timezone.localdate() - dt.timedelta(1))
    assert "Wartezeit bis" in alt.anmerkungen.get().text
    ablauf.automatik()
    assert ws(alt).status == S.WARTEZEIT_UM
    with pytest.raises(ValueError):
        ablauf.status_setzen(ws(alt), S.WARTEZEIT, "Büro")


def test_automatik_streichen_moeglich_und_direkt():
    e = WartelisteEinstellungen.laden()
    a, b = antrag(), antrag("Max", "Probe")
    ablauf.automatik()
    alt = Termin.objects.create(datum=timezone.localdate() - dt.timedelta(days=20), von=dt.time(9))
    ablauf.einladen([a, b], alt, "Büro", mail_senden=False)
    ablauf.automatik()
    assert ws(a).status == S.STREICHEN_MOEGLICH
    e.automatik = e.Automatik.STREICHEN
    e.save()
    ablauf.automatik()
    a.refresh_from_db()
    assert ws(a).status == S.GESTRICHEN and a.status == Antrag.Status.ABGELEHNT
    assert Streichung.objects.filter(antragsnummer=a.nummer, weg="automatik").exists()
    # Streichungsliste nach der Frist leer
    Streichung.objects.update(gestrichen_am=timezone.now() - dt.timedelta(days=40))
    ablauf.automatik()
    assert not Streichung.objects.exists()


def test_aufgenommen_und_abgelehnt_werden_uebernommen():
    a, b = antrag(), antrag("Max", "Probe")
    ablauf.automatik()
    a.kundennummer = "4711"
    a.status_setzen(Antrag.Status.ERLEDIGT, "Büro")
    b.status_setzen(Antrag.Status.ABGELEHNT, "Büro")
    ablauf.automatik()
    assert ws(a).status == S.AUFGENOMMEN and ws(b).status == S.GESTRICHEN


def test_entschuldigt_vermerkt_termin_und_streichen_zuruecknehmen():
    a = antrag()
    t = termin()
    ablauf.einladen([a], t, "Büro", mail_senden=False)
    ablauf.status_setzen(ws(a), S.ENTSCHULDIGT, "Büro")
    assert f"Entschuldigt für den Termin {t}" in a.anmerkungen.last().text
    ablauf.status_setzen(ws(a), S.GESTRICHEN, "Büro")
    a.refresh_from_db()
    assert a.status == Antrag.Status.ABGELEHNT


def test_wieder_bereit_nach_entschuldigt():
    a = antrag()
    t = termin()
    ablauf.einladen([a], t, "Büro", mail_senden=False)
    ablauf.status_setzen(ws(a), S.ENTSCHULDIGT, "Büro")
    # zurückgemeldet: „wieder bereit" löst den alten Termin, bleibt aber eigener Status
    ablauf.status_setzen(ws(a), S.WIEDER_BEREIT, "Büro")
    w = ws(a)
    assert w.status == S.WIEDER_BEREIT and w.termin is None
    assert "Wieder bereit" in a.anmerkungen.last().text
    # und ist wie „wartend" wieder zu einem Termin einladbar
    erg = ablauf.einladen([a], termin(), "Büro", mail_senden=False)
    assert erg[0]["ok"] and ws(a).status == S.EINGELADEN
    ablauf.status_setzen(ws(a), S.WARTEND, "Büro")
    a.refresh_from_db()
    assert a.status == Antrag.Status.IN_BEARBEITUNG and ws(a).status == S.WARTEND


# ── Einladen und Absagen ─────────────────────────────────────────────────────


def test_einladen_mit_und_ohne_mail(mailserver):
    mit = antrag(email="erika@example.org")
    ohne = antrag("Max", "Probe")
    warte = antrag("Wanda", "Warten")
    ablauf.automatik()
    ablauf.status_setzen(ws(warte), S.WARTEZEIT, "Büro", timezone.localdate() + dt.timedelta(30))
    t = termin()
    ergebnisse = ablauf.einladen([mit, ohne, warte], t, "Büro")
    assert [e["ok"] for e in ergebnisse] == [True, False, False]
    assert "keine E-Mail-Adresse" in ergebnisse[1]["hinweis"]
    assert "Wartezeit bis" in ergebnisse[2]["hinweis"]
    assert ws(mit).status == S.EINGELADEN and ws(ohne).status == S.EINGELADEN
    assert ws(warte).status == S.WARTEZEIT
    nachricht = django_mail.outbox[0]
    assert nachricht.to == ["erika@example.org"] and "Einladung zur Anmeldung" in nachricht.subject
    assert "Erika Beispiel" in nachricht.body and "10:00 Uhr bis 12:00 Uhr" in nachricht.body
    mit.refresh_from_db()
    assert mit.status == Antrag.Status.IN_BEARBEITUNG
    assert Einladung.objects.filter(antrag=ohne, weg="E-Mail").exists() is False
    # Absage
    django_mail.outbox.clear()
    ergebnisse = ablauf.absagen(t, [mit, ohne], "Büro")
    assert [e["ok"] for e in ergebnisse] == [True, False]
    assert (
        "ENTFÄLLT" in django_mail.outbox[0].body
        and "Termin entfällt" in django_mail.outbox[0].subject
    )
    assert ws(mit).status == S.WARTEND and ws(mit).termin is None
    assert Einladung.objects.filter(antrag=mit, art="absage").count() == 1


def test_einladung_mail_html_formatiert(mailserver):
    """Die Einladungstexte sind wie die Antragstexte formatierbar: HTML bleibt in der HTML-Mail,
    die Nur-Text-Fassung hat keine Tags."""
    e = WartelisteEinstellungen.laden()
    e.einleitung = "<p>Hallo <strong>{vorname}</strong>, Sie sind dran.</p>"
    e.save()
    a = antrag(email="erika@example.org")
    ablauf.automatik()
    ablauf.einladen([a], termin(), "Büro")
    m = django_mail.outbox[0]
    html = {typ: inhalt for inhalt, typ in m.alternatives}["text/html"]
    assert "<strong>Erika</strong>" in html  # Formatierung bleibt in der HTML-Mail
    assert "<strong>" not in m.body and "Erika" in m.body  # Nur-Text ohne HTML


_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00"
    b"\x00IEND\xaeB`\x82"
)


def test_logo_und_kopfzeile_in_mail(mailserver):
    """Logo der Tafel und die Kopfzeile stehen oben in der Mail (für alle Sprachen gleich)."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.models import TafelEinstellungen

    t = TafelEinstellungen.laden()
    t.logo = SimpleUploadedFile("logo.png", _PNG, content_type="image/png")
    t.save()
    e = WartelisteEinstellungen.laden()
    e.kopfzeile = "<p>Herzlich willkommen bei der Tafel!</p>"
    e.save()
    a = antrag(email="erika@example.org")
    ablauf.automatik()
    ablauf.einladen([a], termin(), "Büro")
    html = {typ: inhalt for inhalt, typ in django_mail.outbox[0].alternatives}["text/html"]
    assert "logo" in html and "<img" in html  # Logo im Kopf
    assert "Herzlich willkommen bei der Tafel!" in html  # Kopfzeile darüber


def test_einladung_haengt_wegbeschreibung_an(mailserver):
    """Die hinterlegte Wegbeschreibung hängt an der Einladung, nicht an der Absage."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    e = WartelisteEinstellungen.laden()
    e.wegbeschreibung = SimpleUploadedFile(
        "weg.pdf", b"%PDF-1.4 Test", content_type="application/pdf"
    )
    e.save()
    a = antrag(email="erika@example.org")
    ablauf.automatik()
    t = termin()
    ablauf.einladen([a], t, "Büro")
    namen = [anhang[0] for anhang in django_mail.outbox[0].attachments]
    assert any("weg" in n and n.endswith(".pdf") for n in namen)
    # Absage: kein Anhang
    django_mail.outbox.clear()
    ablauf.absagen(t, [a], "Büro")
    assert django_mail.outbox[0].attachments == []


def test_wegbeschreibung_hochladen_und_entfernen(admin_client, modul_an):
    from django.core.files.uploadedfile import SimpleUploadedFile

    url = reverse("warteliste:einstellungen")
    datei = SimpleUploadedFile("weg.pdf", b"%PDF-1.4", content_type="application/pdf")
    admin_client.post(url, {"anhang": "1", "wegbeschreibung": datei})
    assert WartelisteEinstellungen.laden().wegbeschreibung  # jetzt hinterlegt
    admin_client.post(url, {"anhang": "1", "entfernen": "1"})
    assert not WartelisteEinstellungen.laden().wegbeschreibung  # wieder entfernt


def test_einstellungen_seite_hat_editor_und_vorschau(admin_client, modul_an):
    inhalt = admin_client.get(reverse("warteliste:einstellungen")).content.decode()
    assert "js/html_editor.js" in inhalt and "data-editor" in inhalt  # grafischer Editor
    assert "mail-vorschau" in inhalt and "{vorname}" in inhalt  # Vorschau + Platzhalter
    # „Standard"-Knopf: die Vorgabe steht als data-standard am Editor-Feld bereit
    assert "data-standard=" in inhalt
    assert "wir können Ihnen folgenden Termin anbieten" in inhalt


def test_sprachen_seite_hat_editor_und_vorschau(admin_client, modul_an):
    inhalt = admin_client.get(reverse("warteliste:texte_sprache", args=["tr"])).content.decode()
    assert "js/html_editor.js" in inhalt and "data-editor" in inhalt  # gleicher Editor wie Deutsch
    assert "mail-vorschau" in inhalt  # gerenderte Vorschau statt Nur-Text


def test_gestrichene_werden_nicht_eingeladen():
    a = antrag()
    ablauf.automatik()
    ablauf.status_setzen(ws(a), S.GESTRICHEN, "Büro")
    assert ablauf.einladen([a], termin(), "Büro", mail_senden=False)[0]["ok"] is False


def test_ort_aus_tafel_oder_einstellungen():
    t = TafelEinstellungen.laden()
    t.name, t.strasse, t.plz, t.ort = "Tafel Musterstadt", "Beispielweg 1", "12345", "Musterstadt"
    t.save()
    assert ablauf.ort(termin()) == "Tafel Musterstadt\nBeispielweg 1\n12345 Musterstadt"
    e = WartelisteEinstellungen.laden()
    e.ort = "Büro im Hinterhof"
    e.save()
    assert ablauf.ort(termin()) == "Büro im Hinterhof"
    assert ablauf.ort(Termin(datum=timezone.localdate(), von=dt.time(9), ort="Saal")) == "Saal"


def test_liste_name_vorname_getrennt_und_sortierbar(admin_client, modul_an):
    antrag(vorname="Berta", nachname="Zander")
    antrag(vorname="Anton", nachname="Anders")
    ablauf.automatik()
    inhalt = admin_client.get(reverse("warteliste:liste")).content.decode()
    assert ">Nachname</a>" in inhalt and ">Vorname</a>" in inhalt  # getrennte Spalten
    assert "⬇ Herunterladen …" in inhalt  # Export-Aufklapper oben rechts (einheitlich)
    nach_v = admin_client.get(reverse("warteliste:liste"), {"sort": "vorname"}).context["eintraege"]
    assert [w.antrag.vorname for w in nach_v] == ["Anton", "Berta"]
    # Weitere Spalten sind jetzt auch sortierbar (kein Fehler).
    liste = reverse("warteliste:liste")
    assert admin_client.get(liste, {"sort": "geburtsdatum"}).status_code == 200
    assert admin_client.get(liste, {"sort": "-wohnort"}).status_code == 200


def test_filter_wird_gemerkt_und_wieder_angezeigt(admin_client, admin, modul_an):
    """Ein angewendeter Filter wird am Konto gemerkt (auch über das Abmelden hinaus) und beim
    nächsten (parameterlosen) Aufruf der Seite wieder angezeigt – ohne „Filtern" zu drücken."""
    liste = reverse("warteliste:liste")
    admin_client.get(liste, {"art": "verlaengerung"})  # Filter anwenden → wird gemerkt
    antwort = admin_client.get(liste)  # Aufruf ohne Parameter (z. B. über das Menü)
    assert antwort.status_code == 302 and "art=verlaengerung" in antwort["Location"]
    admin.refresh_from_db()
    assert admin.warteliste_ansicht["filter"] == "art=verlaengerung"
    seite = admin_client.get(liste, {"art": "verlaengerung"}).content.decode()
    assert "?filter=zuruecksetzen" in seite  # Knopf „Zurücksetzen“ neben „Filtern“
    # „Zurücksetzen“ entfernt alle Filter dieser Seite, auch den gemerkten
    assert admin_client.get(liste, {"filter": "zuruecksetzen"}).status_code == 302
    antwort = admin_client.get(liste)
    assert antwort.status_code == 200 and antwort.context["f"]["art"] == ""
    assert "?filter=zuruecksetzen" not in antwort.content.decode()


def test_status_alle_offenen_bleibt_gewaehlt(admin_client, modul_an):
    """Wer von einem Status (z. B. „eingeladen“) zurück auf „alle offenen“ wechselt, bleibt dort
    – früher sprang die Seite auf den gemerkten Status zurück."""
    liste = reverse("warteliste:liste")
    admin_client.get(liste, {"status": "eingeladen", "art": "neu"})
    seite = admin_client.get(liste, {"status": "eingeladen", "art": "neu"}).content.decode()
    assert 'href="?status=&amp;art=neu"' in seite  # „alle offenen“ behält die übrigen Filter
    antwort = admin_client.get(liste, {"status": "", "art": "neu"})
    assert antwort.status_code == 200 and antwort.context["f"]["status"] == ""
    antwort = admin_client.get(liste)  # gemerkt ist jetzt „alle offenen“
    assert antwort.status_code == 302 and "status=eingeladen" not in antwort["Location"]


def test_liste_nach_nummer_sortierbar(admin_client, modul_an):
    a, b, c = antrag(vorname="A"), antrag(vorname="B"), antrag(vorname="C")
    ablauf.automatik()
    nummern = sorted(x.laufnummer for x in (a, b, c))
    auf = admin_client.get(reverse("warteliste:liste"), {"sort": "nummer"}).context["eintraege"]
    assert [w.antrag.laufnummer for w in auf] == nummern  # aufsteigend
    ab = admin_client.get(reverse("warteliste:liste"), {"sort": "-nummer"}).context["eintraege"]
    assert [w.antrag.laufnummer for w in ab] == nummern[::-1]  # absteigend


# ── Dubletten und Abgleich ───────────────────────────────────────────────────


def test_dubletten_und_zusammenfuehren(admin):
    a = antrag("Erika", "Beispiel", geburtsdatum=dt.date(1980, 2, 3))
    b = antrag("Erika", "Beispiell", geburtsdatum=dt.date(1980, 2, 3))
    antrag("Max", "Anders")
    paare = ablauf.dubletten()
    assert len(paare) == 1 and {paare[0]["a"], paare[0]["b"]} == {a, b}
    ablauf.ignorieren(a, b, admin)
    assert ablauf.dubletten() == []
    c = antrag("Erika", "Beispiel")
    paar = ablauf.dubletten()[0]
    ablauf.zusammenfuehren(paar["a"], paar["b"], "Büro")
    weg = paar["b"]
    assert ws(weg).status == S.GESTRICHEN
    assert f"Antrag {weg.nummer}" in paar["a"].anmerkungen.last().text
    assert c in (paar["a"], paar["b"])


def test_abgleich_und_dubletten_laden_ergebnis_nach(admin_client, modul_an, monkeypatch):
    """Beide Seiten erscheinen sofort und laden ihr Ergebnis per htmx nach, damit sie bei großem
    Kundenstamm nicht hängen."""
    from apps.warteliste import vorberechnung

    monkeypatch.setattr(vorberechnung, "_im_hintergrund", lambda fn: fn())  # synchron rechnen
    antrag("Erika", "Beispiel", geburtsdatum=dt.date(1980, 2, 3))
    antrag("Erika", "Beispiell", geburtsdatum=dt.date(1980, 2, 3))
    ablauf.automatik()
    seite = admin_client.get(reverse("warteliste:abgleich")).content.decode()
    assert "warteliste/abgleich/treffer/" in seite and "geprüft … das kann" in seite
    dubl = admin_client.get(reverse("warteliste:dubletten")).content.decode()
    assert "warteliste/dubletten/paare/" in dubl
    paare = admin_client.get(reverse("warteliste:dubletten_ergebnis")).content.decode()
    assert "streichen" in paare  # die gefundenen Paare kommen aus dem Nachlade-Endpunkt


def test_dublette_per_htmx_entfernt_nur_das_paar(admin_client, modul_an, monkeypatch):
    """Eine Aktion auf ein Paar tauscht per htmx nur dieses Paar aus (hier: entfernt), statt alle
    offenen Anträge neu zu vergleichen (das dauert bei vielen Anträgen lange)."""
    from apps.warteliste import vorberechnung

    monkeypatch.setattr(vorberechnung, "_im_hintergrund", lambda fn: fn())  # synchron rechnen
    a = antrag("Erika", "Beispiel", geburtsdatum=dt.date(1980, 2, 3))
    b = antrag("Erika", "Beispiell", geburtsdatum=dt.date(1980, 2, 3))
    ergebnis = admin_client.get(reverse("warteliste:dubletten_ergebnis")).content.decode()
    assert f'id="paar-{a.pk}-{b.pk}"' in ergebnis or f'id="paar-{b.pk}-{a.pk}"' in ergebnis
    assert "hx-post=" in ergebnis and 'hx-target="#paar-' in ergebnis
    antwort = admin_client.post(
        reverse("warteliste:dublette"),
        {"a": a.pk, "b": b.pk, "aktion": "ignorieren"},
        HTTP_HX_REQUEST="true",
    )
    assert antwort.status_code == 200 and antwort.content == b""
    assert ablauf.dubletten() == []  # Paar ist erledigt, Liste wurde nicht neu aufgebaut


def test_vorberechnung_warm_und_auffrischen(admin_client, modul_an, monkeypatch):
    """Doppelte Anträge kommen vorberechnet aus dem Cache (sofort), neue Anträge werden im
    Hintergrund nachgezogen; läuft eine Auffrischung, baut die Seite einen Selbst-Nachlader ein
    (ADR 0109)."""
    from apps.warteliste import vorberechnung

    monkeypatch.setattr(vorberechnung, "_im_hintergrund", lambda fn: fn())  # synchron auffrischen

    antrag("Erika", "Beispiel", geburtsdatum=dt.date(1980, 2, 3))
    antrag("Erika", "Beispiell", geburtsdatum=dt.date(1980, 2, 3))
    paare, frisch, _ = vorberechnung.dubletten_daten()  # erstes Mal: wird gerechnet
    assert frisch and len(paare) == 1

    # Dritter ähnlicher Antrag → Stand veraltet: altes Ergebnis sofort, Auffrischung angestoßen
    antrag("Erika", "Beispiel", geburtsdatum=dt.date(1980, 2, 3))
    paare, frisch, _ = vorberechnung.dubletten_daten()
    assert not frisch and len(paare) == 1  # noch das alte Ergebnis
    paare, frisch, _ = vorberechnung.dubletten_daten()
    assert frisch and len(paare) > 1  # danach sind die neuen Paare dabei

    # Läuft die Auffrischung, zeigt die Seite einen Selbst-Nachlader
    admin_client.get(reverse("warteliste:dubletten_ergebnis"))  # Cache ist warm
    antrag("Erika", "Beispiel", geburtsdatum=dt.date(1980, 2, 3))  # Signatur ändert sich
    seite = admin_client.get(reverse("warteliste:dubletten_ergebnis")).content.decode()
    assert "Wird im Hintergrund aktualisiert" in seite


def test_dubletten_erstmalig_nicht_blockierend(admin_client, modul_an, monkeypatch):
    """Beim allerersten Öffnen (Cache kalt) blockiert nichts: statt synchron zu rechnen, läuft die
    Rechnung im Hintergrund, die Seite zeigt „wird vorbereitet" und lädt sich nach (ADR 0109)."""
    from apps.warteliste import vorberechnung

    monkeypatch.setattr(vorberechnung, "_im_hintergrund", lambda fn: None)  # läuft noch
    antrag("Erika", "Beispiel", geburtsdatum=dt.date(1980, 2, 3))
    antrag("Erika", "Beispiell", geburtsdatum=dt.date(1980, 2, 3))
    paare, frisch, laeuft = vorberechnung.dubletten_daten()
    assert paare is None and not frisch and laeuft  # noch nichts berechnet, Rechnung angestoßen
    seite = admin_client.get(reverse("warteliste:dubletten_ergebnis")).content.decode()
    assert "im Hintergrund vorbereitet" in seite and "Keine möglichen Dubletten" not in seite


def test_vorwaermen_stoesst_beide_rechnungen_an(modul_an, monkeypatch):
    """Beim Betreten des Warteliste-Bereichs werden Dubletten und Abgleich im Hintergrund
    vorgerechnet; läuft schon eine Rechnung, wird nicht doppelt gestartet (ADR 0109)."""
    from apps.warteliste import vorberechnung

    gestartet = []
    monkeypatch.setattr(vorberechnung, "_im_hintergrund", lambda fn: gestartet.append(fn))
    vorberechnung.veraltet(dubletten=True, abgleich=True)  # sicher kalt
    vorberechnung.vorwaermen()
    assert len(gestartet) == 2  # Dubletten und Abgleich angestoßen
    gestartet.clear()
    vorberechnung.vorwaermen()  # läuft bereits → kein zweiter Start
    assert gestartet == []


def _abgleich_daten_anlegen():
    """Ein offener Antrag mit passendem Haushalt im Kundenstamm (etwas zum Vorrechnen)."""
    h = Haushalt.objects.create(kundennummer="900")
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika",
                          nachname="Beispiel", geburtsdatum=dt.date(1980, 2, 3))  # fmt: skip
    antrag(geburtsdatum=dt.date(1980, 2, 3))
    ablauf.automatik()


def test_vorwaermen_synchron_rechnet_sofort(modul_an):
    """Der Warmlauf (synchron=True, für den periodischen Hintergrund-Job) rechnet sofort, ohne
    Thread – danach ist das Ergebnis im Cache."""
    from django.core.cache import cache

    from apps.warteliste import vorberechnung

    cache.clear()
    _abgleich_daten_anlegen()
    assert vorberechnung.kalt()  # noch nichts gerechnet
    vorberechnung.vorwaermen(synchron=True)
    assert not vorberechnung.kalt()
    daten, frisch, _ = vorberechnung.abgleich_daten()  # sofort aus dem Cache
    assert frisch and daten


def test_befehl_warteliste_vorwaermen(modul_an):
    """Der Management-Befehl (vom 15-Minuten-Loop aufgerufen) füllt den Cache."""
    from django.core.cache import cache
    from django.core.management import call_command

    from apps.warteliste import vorberechnung

    cache.clear()
    _abgleich_daten_anlegen()
    assert vorberechnung.kalt()
    call_command("warteliste_vorwaermen")
    assert not vorberechnung.kalt()


def test_menue_waermt_bei_kaltem_cache(modul_an, monkeypatch):
    """Ist der Cache leer, stößt schon der Blick aufs Menü das Vorrechnen an (ergänzt den Timer)."""
    from django.core.cache import cache

    from apps.warteliste import modul, vorberechnung

    monkeypatch.setattr(vorberechnung, "_im_hintergrund", lambda fn: fn())  # synchron
    cache.clear()
    _abgleich_daten_anlegen()
    assert vorberechnung.kalt()
    modul.menue(lambda *a, **k: {})  # Menü bauen → wärmt im Hintergrund
    assert not vorberechnung.kalt()


def test_kundenabgleich_sperrzeit_und_ausnahmen():
    heute = timezone.localdate()
    h = Haushalt.objects.create(kundennummer="900", ausweis_gueltig_bis=heute - dt.timedelta(60))
    p = Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika",
                              nachname="Beispiel", geburtsdatum=dt.date(1980, 2, 3))  # fmt: skip
    a = antrag(geburtsdatum=dt.date(1980, 2, 3))
    e = ablauf.kundenabgleich([a], heute)[0]
    assert e["sperr"] and "Sperrzeit bis" in e["treffer"][0]["hinweise"][0]["text"]
    # Ausnahme über ein Zusatzfeld
    feld = Zusatzfeld.objects.create(schluessel="schwerbehindert", bezeichnung="Schwerbehindert",
                                     typ=Zusatzfeld.Typ.JA_NEIN)  # fmt: skip
    p.zusatz = {"schwerbehindert": True}
    p.save()
    w = WartelisteEinstellungen.laden()
    w.ausnahme_feld = feld
    w.save()
    hinweis = ablauf.kundenabgleich([a], heute)[0]["treffer"][0]["hinweise"][0]
    assert hinweis["art"] == "ok" and "Schwerbehindert" in hinweis["text"]
    # Ausweis noch gültig
    h.ausweis_gueltig_bis = heute + dt.timedelta(30)
    h.save()
    hinweis = ablauf.kundenabgleich([a], heute)[0]["treffer"][0]["hinweise"][0]
    assert "Verlängerung statt Neuanmeldung" in hinweis["text"]
    # Sperrzeit vorbei
    w.ausnahme_feld = None
    w.save()
    h.ausweis_gueltig_bis = heute - dt.timedelta(400)
    h.save()
    hinweis = ablauf.kundenabgleich([a], heute)[0]["treffer"][0]["hinweise"][0]
    assert hinweis["art"] == "ok" and "Sperrzeit vorbei" in hinweis["text"]


def test_ausnahme_nur_wenn_alle_erwachsenen_sie_erfuellen():
    """Ein Haushalt mit einer Person über 60 und einer jüngeren ohne Merkmal bekommt keine
    Ausnahme von der Sperrzeit – erst wenn jede erwachsene Person eine Bedingung erfüllt."""
    heute = timezone.localdate()
    h = Haushalt.objects.create(kundennummer="901", ausweis_gueltig_bis=heute - dt.timedelta(60))
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Beispiel",
                          geburtsdatum=dt.date(heute.year - 65, 1, 1))  # fmt: skip
    juenger = Person.objects.create(haushalt=h, vorname="Paul", nachname="Beispiel",
                                    geburtsdatum=dt.date(heute.year - 45, 1, 1))  # fmt: skip
    Person.objects.create(haushalt=h, vorname="Kind", nachname="Beispiel",
                          geburtsdatum=dt.date(heute.year - 8, 1, 1))  # fmt: skip
    hinw = ablauf.hinweise(h, h.hauptperson, heute)
    assert hinw[0]["art"] == "sperr" and "Sperrzeit bis" in hinw[0]["text"]
    assert any("nicht alle Erwachsenen" in x["text"] and "Paul Beispiel" in x["text"] for x in hinw)
    assert ablauf.folge(hinw).startswith("Wartezeit bis")
    # Erfüllt auch die zweite erwachsene Person eine Bedingung (hier das Merkmal), gilt die
    # Ausnahme; das Kind zählt nicht mit.
    feld = Zusatzfeld.objects.create(schluessel="schwerbehindert", bezeichnung="Schwerbehindert",
                                     typ=Zusatzfeld.Typ.JA_NEIN)  # fmt: skip
    w = WartelisteEinstellungen.laden()
    w.ausnahme_feld = feld
    w.save()
    juenger.zusatz = {"schwerbehindert": True}
    juenger.save()
    h = Haushalt.objects.get(pk=h.pk)
    hinw = ablauf.hinweise(h, h.hauptperson, heute)
    assert hinw[0]["art"] == "ok" and "direkt verlängern" in hinw[0]["text"]


def test_ausnahme_zaehlt_auch_die_personen_im_antrag():
    """Im Kundenstamm steht nur die frühere Hauptperson (über 60); im Antrag meldet sie sich mit
    einer jüngeren erwachsenen Person an. Dann gilt die Ausnahme nicht: Die Bedingung muss für
    den Haushalt von heute stimmen, nicht nur für den früheren."""
    from apps.antraege.models import AntragPerson

    heute = timezone.localdate()
    h = Haushalt.objects.create(kundennummer="903", ausweis_gueltig_bis=heute - dt.timedelta(60))
    alt = dt.date(heute.year - 63, 1, 1)
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Beispiel",
                          geburtsdatum=alt)  # fmt: skip
    a = antrag(geburtsdatum=alt)
    # allein: Ausnahme gilt (die Hauptperson im Antrag ist dieselbe wie im Kundenstamm)
    hinw = ablauf.hinweise(h, h.hauptperson, heute, antrag=a)
    assert hinw[0]["art"] == "ok" and "direkt verlängern" in hinw[0]["text"]
    # ein Kind im Antrag ändert daran nichts
    AntragPerson.objects.create(antrag=a, vorname="Kim", nachname="Beispiel",
                                geburtsdatum=dt.date(heute.year - 9, 5, 5))  # fmt: skip
    assert ablauf.hinweise(h, h.hauptperson, heute, antrag=a)[0]["art"] == "ok"
    # eine jüngere erwachsene Person im Antrag: keine Ausnahme, die Sperrzeit gilt
    AntragPerson.objects.create(antrag=a, vorname="Paul", nachname="Beispiel",
                                geburtsdatum=dt.date(heute.year - 51, 2, 17))  # fmt: skip
    hinw = ablauf.hinweise(h, h.hauptperson, heute, antrag=a)
    assert hinw[0]["art"] == "sperr" and "Sperrzeit bis" in hinw[0]["text"]
    assert any("Paul Beispiel (51 Jahre, im Antrag)" in x["text"] for x in hinw)
    assert ablauf.folge(hinw).startswith("Wartezeit bis")
    # so entscheidet auch „Ja, derselbe Haushalt“: Wartezeit statt direkt verlängern
    meldung = ablauf.entscheiden(a, "903", True, "chefin", heute)
    assert "Wartezeit bis" in meldung
    assert "direkt verlängern" not in a.anmerkungen.latest("pk").text
    # ohne Antrag (z. B. reine Auskunft zum Kundenstamm) bleibt es bei dessen Personen
    assert ablauf.hinweise(h, h.hauptperson, heute)[0]["art"] == "ok"


def test_gesperrte_werden_nicht_eingeladen():
    """Ein gesperrter Haushalt gilt im Abgleich nie als einladbar: „derselbe Haushalt“ setzt die
    Wartezeit bis nach dem Ablauf der Sperre – auch wenn sonst eine Ausnahme gälte."""
    from apps.kunden.models import Sperre

    heute = timezone.localdate()
    h = Haushalt.objects.create(kundennummer="902", ausweis_gueltig_bis=heute - dt.timedelta(400))
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Beispiel",
                          geburtsdatum=dt.date(heute.year - 70, 2, 3))  # fmt: skip
    ende = heute + dt.timedelta(days=90)
    Sperre.objects.create(haushalt=h, von=heute - dt.timedelta(days=10), bis=ende)
    a = antrag(geburtsdatum=dt.date(heute.year - 70, 2, 3))
    ablauf.automatik()
    e = ablauf.kundenabgleich([a], heute)[0]
    assert e["sperr"] and "gesperrt bis" in e["treffer"][0]["hinweise"][0]["text"]
    assert "möglicherweise Kunde 902" in ablauf.sperre_offen(a, heute)
    meldung = ablauf.entscheiden(a, "902", True, "Büro", heute)
    bis = ende + dt.timedelta(days=1)
    assert f"Wartezeit bis {bis:%d.%m.%Y}" in meldung
    assert ws(a).status == S.WARTEZEIT and ws(a).wartezeit_bis == bis
    assert not ablauf.einladen([a], termin(), "Büro", mail_senden=False)[0]["ok"]
    # Unbefristet gesperrt: zunächst ein Jahr Wartezeit
    Sperre.objects.filter(haushalt=h).update(bis=None)
    h = Haushalt.objects.get(pk=h.pk)
    hinw = ablauf.hinweise(h, h.hauptperson, heute)
    assert "unbefristet gesperrt" in hinw[0]["text"]
    assert hinw[0]["bis"] == heute + dt.timedelta(days=365)


def test_offene_sperren_wie_einzeln_und_zwischengespeichert(monkeypatch):
    """Die Sperrhinweise der Listenseite stimmen mit sperre_offen() überein und werden beim zweiten
    Aufruf aus dem Cache bedient, ohne den Kundenstamm erneut abzufragen."""
    from django.core.cache import cache

    cache.clear()
    heute = timezone.localdate()
    h = Haushalt.objects.create(kundennummer="900", ausweis_gueltig_bis=heute - dt.timedelta(60))
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika",
                          nachname="Beispiel", geburtsdatum=dt.date(1980, 2, 3))  # fmt: skip
    a = antrag(geburtsdatum=dt.date(1980, 2, 3))
    Wartestand.objects.get_or_create(antrag=a)
    sperren = ablauf.offene_sperren([a], heute)
    assert a.pk in sperren and sperren[a.pk] == ablauf.sperre_offen(a, heute)

    # Zweiter Aufruf kommt aus dem Cache – sperre_offen wird nicht erneut berechnet.
    def nicht_erneut(*args, **kwargs):
        pytest.fail("sperre_offen trotz Cache erneut aufgerufen")

    monkeypatch.setattr(ablauf, "sperre_offen", nicht_erneut)
    assert ablauf.offene_sperren([a], heute) == sperren


def test_abgleich_seite_hat_regler_und_prozent(admin_client, modul_an, monkeypatch):
    from apps.warteliste import vorberechnung

    monkeypatch.setattr(vorberechnung, "_im_hintergrund", lambda fn: fn())  # synchron rechnen
    h = Haushalt.objects.create(kundennummer="900")
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Beispiel",
                          geburtsdatum=dt.date(1980, 2, 3))  # fmt: skip
    antrag(geburtsdatum=dt.date(1980, 2, 3))
    ablauf.automatik()  # legt die Wartestände an, damit der Antrag auf der Abgleich-Seite steht
    seite = admin_client.get(reverse("warteliste:abgleich")).content.decode()
    assert "js/abgleich.js" in seite and "warteliste/abgleich/treffer/" in seite  # lädt nach
    treffer = admin_client.get(reverse("warteliste:abgleich_ergebnis")).content.decode()
    assert "% Übereinstimmung" in treffer
    assert 'id="min-score"' in treffer and "data-punkte=" in treffer
    # „Zurück zu“ zeigt auf die echte Abgleich-Seite, nicht auf den Fragment-Endpunkt – sonst
    # landet man nach dem Bestätigen auf der Trefferliste ohne Layout.
    assert f'name="weiter" value="{reverse("warteliste:abgleich")}"' in treffer


def test_menue_zaehler_abgleich_nur_neu_und_wartend(modul_an, monkeypatch):
    """Der Menü-Zähler zählt nur Anträge, die die Abgleich-Seite in der Vorgabe auch zeigt
    (Status „neu“/„wartend“). Ein offener Antrag mit ähnlichem Haushalt, der aber schon eingeladen
    ist, steht nur unter „alle offenen prüfen“ und darf den Zähler nicht hochzählen – sonst stünde
    im Menü eine Zahl, die geöffnete Seite wäre aber leer."""
    from django.core.cache import cache

    from apps.warteliste import vorberechnung

    cache.clear()
    monkeypatch.setattr(vorberechnung, "_im_hintergrund", lambda fn: fn())  # synchron rechnen
    # Zwei Anträge, beide mit passendem Haushalt im Kundenstamm (ungeprüfter Treffer).
    for nr, gb in (("900", dt.date(1980, 2, 3)), ("901", dt.date(1975, 5, 6))):
        h = Haushalt.objects.create(kundennummer=nr)
        Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika",
                               nachname="Beispiel", geburtsdatum=gb)  # fmt: skip
    a = antrag(geburtsdatum=dt.date(1980, 2, 3))
    b = antrag(geburtsdatum=dt.date(1975, 5, 6))
    ablauf.automatik()  # beide werden „wartend“
    # Einen der beiden einladen → nicht mehr „neu“/„wartend“, bleibt aber offen und hat weiter
    # einen ungeprüften Treffer.
    ablauf.einladen([b], termin(), "Büro", mail_senden=False)
    assert ws(b).status == S.EINGELADEN

    vorberechnung.veraltet(abgleich=True)
    daten, _, _ = vorberechnung.abgleich_daten()  # rechnet synchron und füllt den Cache
    assert {e["antrag_pk"] for e in daten} == {a.pk, b.pk}  # beide stehen im Ergebnis
    assert vorberechnung.anzahl_abgleich() == 1  # der Zähler zählt nur den „wartenden“


def test_zahl_im_menue_zaehlt_nur_treffer_ab_der_schwelle():
    """Die Zahl am Menüpunkt „Abgleich mit Kundenstamm“ zählt nur Anträge mit einem Treffer ab
    65 % – schwächere blendet die Seite in der Vorgabe aus, die Zahl stünde sonst für nichts."""
    from django.core.cache import cache

    from apps.warteliste import vorberechnung

    def eintrag(status, *punkte):
        return {"status": status, "treffer": [{"punkte": p} for p in punkte]}

    cache.set(vorberechnung.ABG, {"daten": [
        eintrag("neu", 60), eintrag("wartend", 64, 55), eintrag("neu", 65),
        eintrag("wartend", 58, 90), eintrag("eingeladen", 100)]})  # fmt: skip
    assert vorberechnung.anzahl_abgleich() == 2
    cache.set(vorberechnung.ABG, {"daten": [eintrag("neu", 60)]})
    assert vorberechnung.anzahl_abgleich() is None  # dann steht gar keine Zahl im Menü
    cache.clear()


def test_entscheidung_erneuert_nur_den_einen_antrag(modul_an, admin_client, monkeypatch):
    """Nach „Ja/Nein“ im Abgleich bleibt das gespeicherte Ergebnis: nur der entschiedene Antrag
    wird erneuert. Die Zahl im Menü bleibt, und nichts sucht den ganzen Kundenstamm neu durch."""
    from django.core.cache import cache

    from apps.warteliste import vorberechnung
    from apps.warteliste.models import AbgleichEntscheidung

    cache.clear()
    # zwei ganz verschiedene Namen, damit jeder Antrag nur seinen einen Treffer hat
    for nr, vorname, nachname, gb in (
        ("900", "Erika", "Beispiel", dt.date(1980, 2, 3)),
        ("901", "Konrad", "Zimmermann", dt.date(1975, 5, 6)),
    ):
        h = Haushalt.objects.create(kundennummer=nr)
        Person.objects.create(haushalt=h, ist_hauptperson=True, vorname=vorname,
                              nachname=nachname, geburtsdatum=gb)  # fmt: skip
    a = antrag(geburtsdatum=dt.date(1980, 2, 3))
    b = antrag(vorname="Konrad", nachname="Zimmermann", geburtsdatum=dt.date(1975, 5, 6))
    ablauf.automatik()
    vorberechnung.vorwaermen(synchron=True)
    assert vorberechnung.anzahl_abgleich() == 2
    # ab jetzt darf nie wieder alles gerechnet werden
    monkeypatch.setattr(vorberechnung, "_rechnen_abgleich",
                        lambda: pytest.fail("ganzer Kundenstamm neu durchsucht"))  # fmt: skip
    ziel = reverse("warteliste:abgleich_entscheiden")
    admin_client.post(ziel, {"antrag": a.pk, "kundennummer": "900", "gleich": "0"})
    assert vorberechnung.anzahl_abgleich() == 1  # die Zahl bleibt, nur einer weniger
    daten, frisch, laeuft = vorberechnung.abgleich_daten()
    assert frisch and not laeuft and {e["antrag_pk"] for e in daten} == {b.pk}
    assert not vorberechnung.kalt()
    # Zurücknehmen: der Treffer steht wieder da, wieder ohne alles neu zu rechnen
    entscheidung = AbgleichEntscheidung.objects.get(antrag=a)
    admin_client.post(ziel, {"zuruecknehmen": entscheidung.pk})
    daten, frisch, _ = vorberechnung.abgleich_daten()
    assert frisch and {e["antrag_pk"] for e in daten} == {a.pk, b.pk}
    assert vorberechnung.anzahl_abgleich() == 2


def test_entscheidung_bei_veraltetem_stand_frischt_weiter_auf(modul_an, monkeypatch):
    """War das Ergebnis schon vor der Entscheidung veraltet, bleibt es das (und wird wie gewohnt im
    Hintergrund aufgefrischt); ohne gespeichertes Ergebnis passiert nichts."""
    from django.core.cache import cache

    from apps.warteliste import vorberechnung

    cache.clear()
    _abgleich_daten_anlegen()
    a = Antrag.objects.get()
    vorberechnung.abgleich_antrag_erneuern(a.pk, vorberechnung.abgleich_signatur())
    assert vorberechnung.kalt()  # nichts gespeichert: nichts zu erneuern
    vorberechnung.vorwaermen(synchron=True)
    alt = "anderer Stand"
    vorberechnung.abgleich_antrag_erneuern(a.pk, alt)
    assert cache.get(vorberechnung.ABG)["signatur"] != alt
    stand = dict(cache.get(vorberechnung.ABG), signatur=alt)
    cache.set(vorberechnung.ABG, stand, 60)
    vorberechnung.abgleich_antrag_erneuern(a.pk, "noch ein anderer")
    assert cache.get(vorberechnung.ABG)["signatur"] == alt  # bleibt veraltet


def test_auskunft_enthaelt_warteliste(pdf_text):
    a = antrag()
    ablauf.einladen([a], termin(), "Büro", mail_senden=False)
    from django.http import HttpResponse

    inhalt = pdf_text(HttpResponse(auskunft.antrag_pdf(a), content_type="application/pdf"))
    assert "Warteliste" in inhalt and "eingeladen" in inhalt


# ── Seiten ───────────────────────────────────────────────────────────────────


def test_modul_aus(admin_client):
    assert admin_client.get(reverse("warteliste:liste")).status_code == 404


def test_seiten(modul_an, admin_client, mailserver, pdf_text):
    a = antrag(email="erika@example.org", staatsangehoerigkeit="Ukraine")
    b = antrag("Max", "Probe", staatsangehoerigkeit="Syrien")
    seite = admin_client.get(reverse("warteliste:liste")).content.decode()
    assert ">Beispiel</a>" in seite and ">Probe</a>" in seite  # Nachname getrennt
    filter_ = {"staat_modus": "nicht", "staat": ["Syrien"]}
    seite = admin_client.get(reverse("warteliste:liste"), filter_).content.decode()
    assert ">Beispiel</a>" in seite and ">Probe</a>" not in seite
    datum = (timezone.localdate() + dt.timedelta(days=5)).isoformat()
    einladung = {"ids": [a.pk, b.pk], "datum": datum, "von": "10:00", "bis": "11:30", "mail": "on"}
    # Erst die Vorschau: wer eingeladen wird und ein Beispiel der Mail – noch nichts gesendet
    vorschau = admin_client.post(reverse("warteliste:einladen"), einladung).content.decode()
    assert "Einladung prüfen" in vorschau and "Jetzt senden" in vorschau
    assert "Beispiel, Erika" in vorschau and "So sieht die Einladung aus" in vorschau
    assert not Termin.objects.exists() and not django_mail.outbox
    assert ws(a).status != S.EINGELADEN
    antwort = admin_client.post(reverse("warteliste:einladen"), {**einladung, "bestaetigt": "1"})
    assert antwort.status_code == 200 and "Einladung an erika@example.org gesendet" in (
        antwort.content.decode()
    )
    t = Termin.objects.get()
    seite = admin_client.get(reverse("warteliste:termin", args=[t.pk])).content.decode()
    assert "Beispiel, Erika" in seite
    pdf = admin_client.get(reverse("warteliste:druckliste", args=[t.pk]))
    assert pdf["Content-Type"] == "application/pdf"
    # Druckliste zum Abhaken: Spalten Erschienen und Bemerkung, kein Status, keine Telefonnummer
    text = pdf_text(pdf)
    assert "Erschienen" in text and "Bemerkung" in text
    assert "Status" not in text and "Telefon" not in text
    admin_client.post(reverse("warteliste:status"), {
        "ids": [b.pk], "status": "erschienen", "zurueck": reverse("warteliste:termin", args=[t.pk]),
    })  # fmt: skip
    assert ws(b).status == S.ERSCHIENEN
    antwort = admin_client.post(reverse("warteliste:status"), {
        "ids": [b.pk], "status": "erschienen", "zurueck": "https://boese.example.org/",
    })  # fmt: skip
    assert antwort.url == reverse("warteliste:liste")
    admin_client.post(reverse("warteliste:termin_absagen", args=[t.pk]), {"ids": [a.pk]})
    assert ws(a).status == S.WARTEND
    hin = admin_client.get(reverse("warteliste:eintrag", args=[a.pk]))
    assert hin.status_code == 302 and hin.url == reverse("antraege:antrag", args=[a.pk])
    for name in ("termine", "abgleich", "dubletten", "streichungsliste", "einstellungen"):
        assert admin_client.get(reverse(f"warteliste:{name}")).status_code == 200, name
    assert (
        admin_client.get(reverse("warteliste:streichungsliste"), {"pdf": 1})["Content-Type"]
        == "application/pdf"
    )
    seite = admin_client.get(reverse("warteliste:einstellungen")).content.decode()
    assert "Erika Musterfrau" in seite  # Vorschau
    # Termin mit Eingeladenen lässt sich nicht löschen
    admin_client.post(reverse("warteliste:einladen"),
                      {"ids": [a.pk], "termin": t.pk, "bestaetigt": "1"})  # fmt: skip
    admin_client.post(reverse("warteliste:termin_loeschen", args=[t.pk]))
    assert Termin.objects.filter(pk=t.pk).exists()


def test_export_csv_pdf_und_mail(modul_an, admin_client, mailserver):
    antrag(email="erika@example.org", staatsangehoerigkeit="Ukraine")
    antrag("Max", "Probe", staatsangehoerigkeit="Syrien")
    csv_ = admin_client.get(reverse("warteliste:export"))
    assert csv_["Content-Type"].startswith("text/csv")
    text = csv_.content.decode("utf-8")
    assert "Staatsangehörigkeit" in text
    assert "Beispiel, Erika" in text and "Probe, Max" in text
    # Der Export beachtet denselben Filter wie die Liste
    gefiltert = admin_client.get(
        reverse("warteliste:export"), {"staat_modus": "nicht", "staat": ["Syrien"]}
    ).content.decode("utf-8")
    assert "Beispiel, Erika" in gefiltert and "Probe, Max" not in gefiltert
    # PDF
    pdf = admin_client.get(reverse("warteliste:export"), {"aktion": "pdf"})
    assert pdf["Content-Type"] == "application/pdf"
    # E-Mail mit PDF und CSV im Anhang
    antwort = admin_client.get(
        reverse("warteliste:export"), {"aktion": "mail", "email": "buero@example.org"}
    )
    assert antwort.status_code == 302
    assert django_mail.outbox and django_mail.outbox[0].to == ["buero@example.org"]
    assert len(django_mail.outbox[0].attachments) == 2


def test_rechte(modul_an, client, anmelden, benutzer_mit_rolle):
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    assert client.get(reverse("warteliste:liste")).status_code == 200
    assert client.get(reverse("warteliste:einstellungen")).status_code == 403
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert client.get(reverse("warteliste:liste")).status_code == 403


def test_hilfe_und_menue(modul_an, admin_client):
    seite = admin_client.get(reverse("core:hilfe")).content.decode()
    assert 'id="warteliste"' in seite
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert "Abgleich mit Kundenstamm" in seite and "Warteliste und Einladungen" in seite


def test_abgleich_entscheiden_sperrzeit_und_einladen(admin_client, modul_an, monkeypatch):
    """Treffer bestätigen: Sperrzeit wird zur Wartezeit; ungeprüft lädt „Einladen“ nicht ein."""
    from apps.warteliste import vorberechnung
    from apps.warteliste.models import AbgleichEntscheidung

    monkeypatch.setattr(vorberechnung, "_im_hintergrund", lambda fn: fn())  # synchron rechnen

    heute = timezone.localdate()
    h = Haushalt.objects.create(kundennummer="900", ausweis_gueltig_bis=heute - dt.timedelta(60))
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Beispiel",
                          geburtsdatum=dt.date(1980, 2, 3))  # fmt: skip
    a = antrag(geburtsdatum=dt.date(1980, 2, 3))
    ablauf.automatik()
    # Die Seite selbst zeigt nur den Platzhalter; die Hinweise lädt htmx über warteliste:sperren.
    liste = admin_client.get(reverse("warteliste:liste")).content.decode()
    assert "warteliste/sperren/" in liste and "⚠ Sperrzeit? Prüfen" not in liste
    hinweise = admin_client.get(reverse("warteliste:sperren")).content.decode()
    assert "mit möglicher Sperrzeit" in hinweise and "⚠ Sperrzeit? Prüfen" in hinweise
    ergebnis = ablauf.einladen([a], termin(), "Büro", mail_senden=False)
    assert not ergebnis[0]["ok"] and "erst im Abgleich prüfen" in ergebnis[0]["hinweis"]

    treffer = admin_client.get(reverse("warteliste:abgleich_ergebnis")).content.decode()
    assert "✓ Ja, derselbe Haushalt – Wartezeit bis" in treffer and "✗ Nein" in treffer
    antwort = admin_client.post(reverse("warteliste:abgleich_entscheiden"),
                                {"antrag": a.pk, "kundennummer": "900", "gleich": "1"},
                                follow=True)  # fmt: skip
    assert "derselbe Haushalt wie Kunde 900 – Wartezeit bis" in antwort.content.decode()
    a.refresh_from_db()
    ws = Wartestand.objects.get(antrag=a)
    assert ws.status == "wartezeit" and ws.wartezeit_bis > heute and a.kundennummer == "900"
    assert "Abgleich: derselbe Haushalt wie Kunde 900" in a.anmerkungen.first().text
    seite = admin_client.get(reverse("warteliste:abgleich")).content.decode()
    assert "Zuletzt geprüft" in seite
    treffer = admin_client.get(reverse("warteliste:abgleich_ergebnis")).content.decode()
    assert "Kein ungeprüfter Antrag" in treffer
    assert (
        "⚠ Sperrzeit? Prüfen"
        not in admin_client.get(reverse("warteliste:sperren")).content.decode()
    )

    # Zurücknehmen bringt den Treffer zurück
    d = AbgleichEntscheidung.objects.get()
    admin_client.post(reverse("warteliste:abgleich_entscheiden"), {"zuruecknehmen": d.pk})
    assert not AbgleichEntscheidung.objects.exists()


def test_abgleich_entscheiden_per_htmx_tauscht_nur_den_block(admin_client, modul_an, monkeypatch):
    """Per htmx wird nach „Ja" nur der eine Antrag-Block ausgetauscht (hier: entfernt), nicht die
    ganze Liste neu gerechnet (sonst 10–20 s bei großem Kundenstamm)."""
    from apps.warteliste import vorberechnung
    from apps.warteliste.models import AbgleichEntscheidung

    monkeypatch.setattr(vorberechnung, "_im_hintergrund", lambda fn: fn())  # synchron rechnen

    heute = timezone.localdate()
    h = Haushalt.objects.create(kundennummer="900", ausweis_gueltig_bis=heute - dt.timedelta(60))
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Beispiel",
                          geburtsdatum=dt.date(1980, 2, 3))  # fmt: skip
    a = antrag(geburtsdatum=dt.date(1980, 2, 3))
    ablauf.automatik()
    # Die Entscheiden-Knöpfe tauschen gezielt den Block dieses Antrags aus.
    treffer = admin_client.get(reverse("warteliste:abgleich_ergebnis")).content.decode()
    assert f'hx-target="#antrag-{a.pk}"' in treffer and "hx-post=" in treffer
    assert f'id="antrag-{a.pk}"' in treffer
    # „Ja" per htmx → Antwort ist leer (Block verschwindet), kein Neuaufbau der Liste.
    antwort = admin_client.post(
        reverse("warteliste:abgleich_entscheiden"),
        {"antrag": a.pk, "kundennummer": "900", "gleich": "1"},
        HTTP_HX_REQUEST="true",
    )
    assert antwort.status_code == 200 and antwort.content == b""
    assert AbgleichEntscheidung.objects.filter(antrag=a, gleich=True).exists()


def test_abgleich_nein_und_gueltiger_ausweis(admin_client, modul_an):
    heute = timezone.localdate()
    h = Haushalt.objects.create(kundennummer="901", ausweis_gueltig_bis=heute + dt.timedelta(90))
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Beispiel",
                          geburtsdatum=dt.date(1980, 2, 3))  # fmt: skip
    a = antrag(geburtsdatum=dt.date(1980, 2, 3))
    b = antrag(vorname="Erika", geburtsdatum=dt.date(1980, 2, 3))
    url = reverse("warteliste:abgleich_entscheiden")
    admin_client.post(url, {"antrag": a.pk, "kundennummer": "901", "gleich": "0"})
    assert ablauf.kundenabgleich(Antrag.objects.filter(pk=a.pk)) == []  # ausgeblendet
    admin_client.post(url, {"antrag": b.pk, "kundennummer": "901", "gleich": "1",
                            "weiter": reverse("warteliste:eintrag", args=[b.pk])})  # fmt: skip
    b.refresh_from_db()
    assert b.art == "verlaengerung" and b.kundennummer == "901"
    antwort = admin_client.post(url, {"antrag": b.pk, "kundennummer": "999", "gleich": "1"},
                                follow=True)  # fmt: skip
    assert "gibt es nicht mehr" in antwort.content.decode()


def test_streichungsliste_suche_und_anmerkungen(admin_client, modul_an):
    from apps.warteliste.models import Streichung

    Streichung.objects.create(antragsnummer="17", name="Probe, Gisela", von="Büro")
    Streichung.objects.create(antragsnummer="23", name="Muster, Jonas", von="Büro")
    url = reverse("warteliste:streichungsliste")
    seite = admin_client.get(url, {"q": "gisela"}).content.decode()
    assert "Probe, Gisela" in seite and "Muster, Jonas" not in seite and "hx-get" in seite
    assert "Nichts gefunden" in admin_client.get(url, {"q": "zzz"}).content.decode()

    a = antrag()
    ablauf.automatik()
    admin_client.post(reverse("antraege:anmerkung", args=[a.pk]),
                      {"text": "Hat angerufen, kommt ab Dezember"})  # fmt: skip
    assert a.anmerkungen.last().text == "Hat angerufen, kommt ab Dezember"
    admin_client.post(reverse("antraege:anmerkung", args=[a.pk]), {"text": "Zweite Anmerkung"})
    liste = admin_client.get(reverse("warteliste:liste")).content.decode()
    assert 'name="spalte" value="anmerkung"' in liste and "Spalten wählen" in liste
    # Die Liste zeigt jetzt alle Anmerkungen, nicht nur die letzte.
    assert "Hat angerufen, kommt ab Dezember" in liste and "Zweite Anmerkung" in liste


def test_ansicht_wird_je_konto_gemerkt(admin_client, admin, modul_an):
    antrag()
    ablauf.automatik()
    url = reverse("warteliste:liste")
    # Jede Spalte ist sortierbar – auch die früher nicht sortierbaren Kontakt/Personen/Anmerkung.
    for schluessel in ("kontakt", "personen", "anmerkung", "name"):
        antwort = admin_client.get(url, {"sort": schluessel})
        assert antwort.status_code == 200 and antwort.context["f"]["sort"] == schluessel
    # Die zuletzt gewählte Sortierung wird am Konto gemerkt und ohne Parameter wieder angewandt.
    admin.refresh_from_db()
    assert admin.warteliste_ansicht["sort"] == "name"
    admin_client.get(url, {"sort": "-geburtsdatum"})
    # Ohne Parameter greift der am Konto gemerkte Stand (Filter samt Sortierung).
    assert admin_client.get(url, follow=True).context["f"]["sort"] == "-geburtsdatum"
    # Spaltenwahl je Konto: Geburtsdatum ausblenden.
    admin_client.post(reverse("warteliste:spalten"),
                      {"spalte": ["eingang", "nummer", "kontakt", "status"]})  # fmt: skip
    admin.refresh_from_db()
    assert "geburtsdatum" in admin.listen_spalten_aus["warteliste"]
    inhalt = admin_client.get(url, follow=True).content.decode()
    # Spaltenkopf weg (die Spaltenwahl listet den Namen weiter auf).
    assert "Nach Geburtsdatum sortieren" not in inhalt
    assert "Nach Kontakt sortieren" in inhalt
    # Kapazitätsübersicht ein-/ausklappen wird gemerkt.
    admin_client.post(reverse("warteliste:ansicht"), {"kapazitaet_zu": "1"})
    admin.refresh_from_db()
    assert admin.warteliste_ansicht["kapazitaet_zu"] is True
    assert admin_client.get(url, follow=True).context["kapazitaet_zu"] is True


# ── Einladung in zwei Sprachen ───────────────────────────────────────────────


def test_mitgelieferte_uebersetzungen_vollstaendig():
    import re

    from apps.antraege import sprachen

    de = ablauf.mitgeliefert("de")
    for f in WartelisteEinstellungen.TEXTFELDER:
        assert de[f] == ablauf.vorgabe(f)  # Grundlage = Vorgabe des Modells
    for s in sprachen.SPRACHEN:
        t = ablauf.mitgeliefert(s.code)
        assert set(t) == set(de), s.code
        for k, v in t.items():
            assert v.strip() and set(re.findall(r"\{\w+\}", v)) == set(
                re.findall(r"\{\w+\}", de[k])), (s.code, k)  # fmt: skip


def test_einladung_deutsch_und_sprache_der_staatsangehoerigkeit(mailserver):
    a = antrag(email="erika@example.org", staatsangehoerigkeit="Türkei", sprache="en")
    ablauf.einladen([a], termin(), "Büro")
    m = django_mail.outbox[0]
    tr = ablauf.mitgeliefert("tr")
    assert m.subject.startswith("Einladung zur Anmeldung") and " / Kayıt için davet" in m.subject
    assert "10:00 Uhr bis 12:00 Uhr" in m.body and "Saat:    10:00 – 12:00" in m.body
    assert m.body.index("Bitte bringen Sie mit") < m.body.index(tr["l_mitbringen"])
    assert "Invitation" not in m.body  # Staatsangehörigkeit vor Formularsprache
    html = m.alternatives[0][0]
    assert 'lang="tr" dir="ltr"' in html and "Kayıt için davet" in html
    # Absage zweisprachig, Arabisch von rechts nach links
    b = antrag(email="sami@example.org", staatsangehoerigkeit="Syrien")
    t = termin(8)
    ablauf.einladen([b], t, "Büro")
    django_mail.outbox.clear()
    ablauf.absagen(t, [b], "Büro")
    m = django_mail.outbox[0]
    assert "ENTFÄLLT" in m.body and ablauf.mitgeliefert("ar")["l_entfaellt"] in m.body
    assert 'lang="ar" dir="rtl"' in m.alternatives[0][0]


def test_geaenderter_text_ohne_uebersetzung_nur_deutsch(mailserver):
    e = WartelisteEinstellungen.laden()
    e.einleitung = "wir laden Sie herzlich ein:"
    e.save()
    assert ablauf.eigene_deutsche_texte() == {"einleitung": "wir laden Sie herzlich ein:"}
    assert "einleitung" in ablauf.fehlende("tr")
    ablauf.einladen([antrag(email="erika@example.org", staatsangehoerigkeit="Türkei")], termin(),
                    "Büro")  # fmt: skip
    m = django_mail.outbox[0]
    assert "Kayıt" not in m.subject and "----------" not in m.body
    # Eigene Übersetzung → wieder zweisprachig; Absage braucht die Einleitung nicht
    from apps.warteliste.models import WartelisteText

    WartelisteText.objects.create(sprache="tr", einleitung="sizi davet ediyoruz:")
    assert ablauf.fehlende("tr") == []
    django_mail.outbox.clear()
    ablauf.einladen([antrag(email="ali@example.org", staatsangehoerigkeit="Türkei")], termin(9),
                    "Büro")  # fmt: skip
    assert "sizi davet ediyoruz:" in django_mail.outbox[0].body


def test_ohne_zweite_sprache_nur_deutsch(mailserver):
    ablauf.einladen([antrag(email="erika@example.org")], termin(), "Büro")
    m = django_mail.outbox[0]
    assert " / " not in m.subject and "----------" not in m.body and 'lang="de"' in (
        m.alternatives[0][0])  # fmt: skip


def test_textseiten_und_ki(modul_an, admin_client, monkeypatch):
    from apps.antraege import uebersetzen
    from apps.warteliste.models import WartelisteText

    seite = admin_client.get(reverse("warteliste:einstellungen")).content.decode()
    assert "Für alle Sprachen gibt es Übersetzungen" in seite
    seite = admin_client.get(reverse("warteliste:texte")).content.decode()
    assert "✓ mitgeliefert" in seite and "mit KI" not in seite
    url = reverse("warteliste:texte_sprache", args=["tr"])
    seite = admin_client.get(url).content.decode()
    assert 'lang="tr"' in seite and "Kayıt için davet" in seite  # Platzhalter und Vorschau
    assert admin_client.get(reverse("warteliste:texte_sprache", args=["de"])).url == reverse(
        "warteliste:texte")  # fmt: skip
    e = WartelisteEinstellungen.laden()
    e.gruss = "Herzliche Grüße\nIhre Tafel"
    e.save()
    seite = admin_client.get(reverse("warteliste:texte")).content.decode()
    assert "✗ fehlt: Gruß" in seite
    seite = admin_client.get(reverse("warteliste:einstellungen")).content.decode()
    assert "28 Sprachen ohne Übersetzung" in seite
    admin_client.post(url, {"gruss": "Selamlar\nTafel"})
    assert WartelisteText.objects.get(sprache="tr").gruss == "Selamlar\nTafel"
    assert "✓ eigene Übersetzung" in admin_client.get(reverse("warteliste:texte")).content.decode()
    # KI: ohne Schlüssel zurück, mit Schlüssel Schritt für Schritt
    start = reverse("warteliste:uebersetzen")
    assert admin_client.post(start).url == reverse("warteliste:texte")
    monkeypatch.setattr(uebersetzen, "verfuegbar", lambda: True)
    gesehen = []

    def falsch_uebersetzen(texte, code, zweck=""):
        gesehen.append((texte, code, zweck))
        return {"gruss": f"Gruß {code}"}

    monkeypatch.setattr(uebersetzen, "uebersetzen", falsch_uebersetzen)
    assert (
        "Geänderte Texte mit KI" in admin_client.get(reverse("warteliste:texte")).content.decode()
    )
    assert "uebersetzen/en/" in admin_client.post(start).content.decode()
    schritt = admin_client.post(reverse("warteliste:uebersetzen_sprache", args=["en"]))
    assert "✓" in schritt.content.decode() and "uebersetzen/ar/" in schritt.content.decode()
    assert gesehen == [({"gruss": "Herzliche Grüße\nIhre Tafel"}, "en", ablauf.EINLADUNG_ZWECK)]
    assert WartelisteText.objects.get(sprache="en").gruss == "Gruß en"

    def kaputt(*a, **k):
        raise uebersetzen.UebersetzungsFehler("Keine Verbindung")

    monkeypatch.setattr(uebersetzen, "uebersetzen", kaputt)
    letzte = admin_client.post(reverse("warteliste:uebersetzen_sprache", args=["ur"]))
    assert "Keine Verbindung" in letzte.content.decode() and "Fertig" in letzte.content.decode()


def test_liste_zeigt_gruppenkapazitaet(admin_client, modul_an):
    """Oben auf der Warteliste stehen die freien Plätze je Kundengruppe (ADR 0061)."""
    from apps.kunden.models import Kundengruppe

    Kundengruppe.objects.create(name="Montagsgruppe", maximum=10)
    inhalt = admin_client.get(reverse("warteliste:liste")).content.decode()
    assert "Gruppenkapazitäten" in inhalt
    assert "Montagsgruppe" in inhalt and "freie Plätze" in inhalt


def test_suche_findet_anmerkungen(admin_client, modul_an):
    a = antrag(vorname="Zeynep", nachname="Yildiz")
    b = antrag(vorname="Omar", nachname="Nasser")
    ablauf.automatik()
    ablauf.anmerken(a, "Hat noch keinen Bescheid vom Jobcenter", "Büro")
    liste = reverse("warteliste:liste")
    treffer = admin_client.get(liste, {"suche": "Jobcenter"}).context["eintraege"]
    assert [w.antrag.pk for w in treffer] == [a.pk] and b.pk not in [w.antrag.pk for w in treffer]
    # mehrere passende Anmerkungen → trotzdem nur eine Zeile (distinct)
    ablauf.anmerken(a, "Jobcenter-Unterlagen fehlen noch", "Büro")
    treffer = list(admin_client.get(liste, {"suche": "Jobcenter"}).context["eintraege"])
    assert len(treffer) == 1


def test_antragsseite_zeigt_warteliste_abschnitt(admin_client, modul_an):
    """Ein Antrag aus der Warteliste öffnet die ganze Antragsseite; der Warteliste-Abschnitt
    (Einladen, ähnliche Haushalte) erscheint dort (ADR 0115); den Status gibt es nur oben."""
    a = antrag(geburtsdatum=dt.date(1980, 2, 3))
    ablauf.automatik()  # legt den Wartestand an
    seite = admin_client.get(reverse("antraege:antrag", args=[a.pk])).content.decode()
    assert 'id="warteliste"' in seite and "Status setzen" not in seite
    # Nur ein Status: der der Warteliste, oben bei den Angaben – ohne die Antrags-Auswahl
    assert seite.count('name="status"') == 1 and 'value="in_bearbeitung"' not in seite
    assert 'class="status wl-wartend"' in seite and 'data-pflicht-bei="status=wartezeit"' in seite
    assert reverse("warteliste:antrag_treffer", args=[a.pk]) in seite  # Treffer werden nachgeladen
    # Status von der Antragsseite aus setzen führt wieder zur Antragsseite zurück
    antwort = admin_client.post(
        reverse("warteliste:status"),
        {"ids": a.pk, "status": "erschienen", "zurueck": reverse("antraege:antrag", args=[a.pk])},
    )
    assert antwort.status_code == 302 and antwort.url == reverse("antraege:antrag", args=[a.pk])
    assert ws(a).status == S.ERSCHIENEN
    # Ohne Datum bei „Wartezeit“: Fehler und zurück zur Antragsseite (nicht zur Warteliste)
    antwort = admin_client.post(
        reverse("warteliste:status"),
        {"ids": a.pk, "status": "wartezeit", "zurueck": reverse("antraege:antrag", args=[a.pk])},
    )
    assert antwort.url == reverse("antraege:antrag", args=[a.pk]) and ws(a).status == S.ERSCHIENEN
    # Der Treffer-Abschnitt lädt eigenständig (htmx)
    assert admin_client.get(reverse("warteliste:antrag_treffer", args=[a.pk])).status_code == 200


def test_einladen_block_steht_oben(admin_client, modul_an):
    """Der „Ausgewählte einladen“-Block steht jetzt oben (unter den Suchfeldern, über der Tabelle);
    die Status-Aktion bleibt unten."""
    seite = admin_client.get(reverse("warteliste:liste")).content.decode()
    assert "Ausgewählte einladen" in seite
    assert seite.index("Ausgewählte einladen") < seite.index("<table")
    assert seite.index("<table") < seite.index("Status der Ausgewählten")


def test_menue_zeigt_offene_faelle(admin_client, modul_an, monkeypatch):
    """Im Menü steht neben „Abgleich mit Kundenstamm“ und „Doppelte Anträge“ die Zahl der offenen
    Fälle – aus dem vorberechneten Cache, ohne teure Neuberechnung (ADR 0109)."""
    from apps.core.menue import _eintrag
    from apps.warteliste import modul, vorberechnung

    monkeypatch.setattr(vorberechnung, "_im_hintergrund", lambda fn: fn())  # synchron rechnen
    # Ohne vorberechneten Stand kein Abzeichen (das Menü rechnet nie selbst).
    assert vorberechnung.anzahl_dubletten() is None

    antrag("Erika", "Beispiel", geburtsdatum=dt.date(1980, 2, 3))
    antrag("Erika", "Beispiell", geburtsdatum=dt.date(1980, 2, 3))
    vorberechnung.dubletten_daten()  # füllt den Cache wie beim Öffnen der Seite
    assert vorberechnung.anzahl_dubletten() == 1

    eintraege = {e["titel"]: e for _, e in dict(modul.menue(_eintrag))["Anträge und Warteliste"]}
    assert eintraege["Doppelte Anträge"].get("zahl") == 1
    assert "Dubletten" in eintraege["Doppelte Anträge"].get("zahl_titel", "")
    # Für den Abgleich wurde noch nichts berechnet → kein Abzeichen (statt teuer zu rechnen).
    assert "zahl" not in eintraege["Abgleich mit Kundenstamm"]


def test_nach_aufnahme_zurueck_zur_terminliste(admin_client, modul_an, client, anmelden,
                                               benutzer_mit_rolle, recht_nehmen):  # fmt: skip
    Haushalt.objects.create(kundennummer="905")
    a = antrag(kundennummer="905")
    fertig = reverse("antraege:aufnahme_fertig", args=[a.pk])
    # Ohne Termin (auch heute keiner): nur die üblichen Wege
    seite = admin_client.get(fertig).content.decode()
    assert "Zurück zur Terminliste" not in seite and "Zur Antragsliste" in seite
    # Heutiger Termin, wenn der Antrag zu keinem eingeladen war
    heute = termin(tage=0)
    seite = admin_client.get(fertig).content.decode()
    assert f'href="{reverse("warteliste:termin", args=[heute.pk])}"' in seite
    # Sonst der Termin, zu dem eingeladen war
    eigener = termin(tage=-2)
    ablauf.wartestaende_anlegen()
    Wartestand.objects.filter(antrag=a).update(termin=eigener, status=S.AUFGENOMMEN)
    seite = admin_client.get(fertig).content.decode()
    assert f'href="{reverse("warteliste:termin", args=[eigener.pk])}"' in seite
    assert "Zurück zur Terminliste" in seite
    # Wer die Warteliste nicht sehen darf, bekommt den Link nicht
    recht_nehmen(rollen.BUERO, "warteliste.sehen")
    anmelden(client, benutzer_mit_rolle("dora", rollen.BUERO))
    seite = client.get(fertig).content.decode()
    assert "Kunde 905 aufgenommen" in seite and "Zurück zur Terminliste" not in seite


def test_termine_zaehlen_eingeladen_entschuldigt_erschienen_aufgenommen(admin_client, modul_an):
    """Die Übersicht der Termine zählt: jede Einladung zum Termin, entschuldigt oder abgesagt,
    erschienen (einschließlich aufgenommen) und aufgenommen – Erschienene ohne gültigen Bescheid
    bleiben erschienen, aber nicht aufgenommen."""
    t = termin(tage=0)
    leute = [antrag(f"P{i}", "Beispiel") for i in range(6)]
    ablauf.automatik()
    ablauf.einladen(leute, t, "Büro", mail_senden=False)
    ablauf.absagen(t, [leute[0]], "Büro")  # danach wieder „wartend“ ohne Termin
    Wartestand.objects.filter(antrag=leute[1]).update(status=S.ENTSCHULDIGT)
    Wartestand.objects.filter(antrag=leute[2]).update(status=S.ERSCHIENEN)  # ohne Bescheid
    for a in leute[3:5]:
        a.kundennummer = "9" + str(a.pk)
        a.save()
        a.status_setzen(Antrag.Status.ERLEDIGT, "Büro")  # aufgenommen (noch ohne Automatik)
    seite = admin_client.get(reverse("warteliste:termine")).content.decode()
    zeile = seite.split(reverse("warteliste:termin", args=[t.pk]))[1].split("</tr>")[0]
    zahlen = re.findall(r'data-titel="[^"]+">(\d+)</td>', zeile)
    assert zahlen == ["6", "2", "3", "2"]  # eingeladen, entschuldigt/abgesagt, erschienen, aufg.
    assert "Alle" not in seite


def test_terminliste_zeigt_aufgenommene_sofort_ohne_aktionen(admin_client, modul_an):
    """Nach der Aufnahme steht der Antragsteller auf der Terminliste sofort als „aufgenommen“ –
    ohne Häkchen und mit Link zum Kunden; noch einmal aufnehmen führt zum Kunden."""
    Haushalt.objects.create(kundennummer="906")
    t = termin(tage=0)
    a, b = antrag(), antrag("Max", "Probe")
    ablauf.automatik()
    Wartestand.objects.filter(antrag__in=[a, b]).update(termin=t, status=S.EINGELADEN)
    a.kundennummer = "906"  # wie nach dem Aufnahme-Assistenten
    a.save()
    a.status_setzen(Antrag.Status.ERLEDIGT, "Büro")
    seite = admin_client.get(reverse("warteliste:termin", args=[t.pk])).content.decode()
    assert ws(a).status == S.AUFGENOMMEN  # ohne auf die Automatik zu warten
    assert f'value="{a.pk}"' not in seite and f'value="{b.pk}"' in seite
    assert f'href="{reverse("kunden:haushalt", args=["906"])}"' in seite and "Kunde 906" in seite
    antrag_seite = admin_client.get(reverse("antraege:antrag", args=[a.pk])).content.decode()
    assert "Zum Kunden 906" in antrag_seite
    assert reverse("antraege:aufnahme", args=[a.pk]) not in antrag_seite
    antwort = admin_client.get(reverse("antraege:aufnahme", args=[a.pk]))
    assert antwort.url == reverse("kunden:haushalt", args=["906"])


def test_antragsstatus_ohne_wartestand_und_ohne_recht(
    admin_client, modul_an, client, anmelden, benutzer_mit_rolle, recht_nehmen
):
    """Ohne Wartestand bleibt der Antragsstatus; ohne Recht zum Bearbeiten nur die Anzeige."""
    a = antrag(geburtsdatum=dt.date(1980, 2, 3))
    seite = admin_client.get(reverse("antraege:antrag", args=[a.pk])).content.decode()
    assert 'value="in_bearbeitung"' in seite  # noch kein Wartestand: Antragsstatus
    ablauf.automatik()
    Wartestand.objects.filter(antrag=a).update(status=S.EINGELADEN)
    seite = admin_client.get(reverse("antraege:antrag", args=[a.pk])).content.decode()
    assert '<option value="eingeladen" selected disabled>' in seite  # von selbst entstanden
    recht_nehmen(rollen.BUERO, "warteliste.bearbeiten")
    anmelden(client, benutzer_mit_rolle("dora", rollen.BUERO))
    seite = client.get(reverse("antraege:antrag", args=[a.pk])).content.decode()
    assert 'class="status wl-eingeladen"' in seite and 'name="status"' not in seite


def test_termin_von_heute_ist_nach_dem_ende_vergangen(admin_client, modul_an):
    """Ein Termin von heute steht nur bis zu seinem Ende bei den kommenden – danach bei den
    vergangenen, und einladen kann man zu ihm nicht mehr."""
    heute = timezone.localdate()
    morgens = Termin.objects.create(datum=heute, von=dt.time(10), bis=dt.time(11, 30))
    ohne_ende = Termin.objects.create(datum=heute, von=dt.time(15))
    morgen = Termin.objects.create(datum=heute + dt.timedelta(days=1), von=dt.time(10))
    gestern = Termin.objects.create(datum=heute - dt.timedelta(days=1), von=dt.time(10))

    def um(stunde, minute=0):
        zeit = timezone.make_aware(dt.datetime.combine(heute, dt.time(stunde, minute)))
        return set(ablauf.kommende_termine(zeit))

    assert um(9) == {morgens, ohne_ende, morgen}
    assert um(11, 30) == {morgens, ohne_ende, morgen}  # läuft noch bis zur letzten Minute
    assert um(11, 31) == {ohne_ende, morgen}
    assert um(15, 1) == {morgen}  # ohne Ende: vorbei, sobald der Beginn vorbei ist
    assert gestern not in um(0, 1)
    # Die Seite teilt genauso
    seite = admin_client.get(reverse("warteliste:termine"))
    kommend, vergangen = set(seite.context["kommend"]), set(seite.context["vergangen"])
    assert kommend == set(ablauf.kommende_termine()) and gestern in vergangen
    assert kommend | vergangen == {morgens, ohne_ende, morgen, gestern}
    assert not kommend & vergangen


# ── Termin in den eigenen Kalender ───────────────────────────────────────────


def test_termin_als_kalendereintrag(admin_client, modul_an, mailserver):
    """„In meinen Kalender“: Tag, Uhrzeit, Ort und Zahl der Eingeladenen – ohne Namen."""
    from apps.warteliste import kalender

    a, b, c = antrag(email="erika@example.org"), antrag("Max", "Probe"), antrag("Ina", "Test")
    ablauf.automatik()
    t = Termin.objects.create(datum=dt.date(2026, 12, 3), von=dt.time(10), bis=dt.time(11, 30),
                              ort="Tafelbüro; Hinterhaus\nMusterweg 1, 12345 Neustadt",
                              anmerkung="Bitte Schlüssel holen")  # fmt: skip
    ablauf.einladen([a, b, c], t, "Büro")
    ablauf.status_setzen(ws(c), S.ENTSCHULDIGT, "Büro")
    assert kalender.erwartet(t) == 2  # wer entschuldigt ist, zählt nicht mehr

    antwort = admin_client.get(reverse("warteliste:termin_kalender", args=[t.pk]))
    assert antwort["Content-Type"] == "text/calendar; charset=utf-8"
    assert 'filename="neuanmeldung-2026-12-03.ics"' in antwort["Content-Disposition"]
    text = antwort.content.decode()
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    entfaltet = text.replace("\r\n ", "")
    # 10:00–11:30 Uhr in Berlin (Winterzeit) = 09:00–10:30 UTC
    assert "DTSTART:20261203T090000Z" in entfaltet and "DTEND:20261203T103000Z" in entfaltet
    assert "SUMMARY:Neuanmeldung (2 Eingeladene)" in entfaltet
    assert r"LOCATION:Tafelbüro\; Hinterhaus\, Musterweg 1\, 12345 Neustadt" in entfaltet
    assert "Bitte Schlüssel holen" in entfaltet
    assert reverse("warteliste:termin", args=[t.pk]) in entfaltet
    assert f"UID:warteliste-termin-{t.pk}@" in entfaltet
    assert all(len(z.encode()) <= 75 for z in text.split("\r\n"))
    for name in ("Beispiel", "Probe", "Erika", "example.org"):  # keine Personendaten
        assert name not in text
    # Knöpfe: auf der Terminseite, in der Terminliste und nach dem Einladen
    ziel = reverse("warteliste:termin_kalender", args=[t.pk])
    assert ziel in admin_client.get(reverse("warteliste:termin", args=[t.pk])).content.decode()
    assert ziel in admin_client.get(reverse("warteliste:termine")).content.decode()


def test_kalendereintrag_ohne_ende_und_einzahl(admin_client, modul_an):
    from apps.warteliste import kalender

    a = antrag()
    ablauf.automatik()
    t = Termin.objects.create(datum=dt.date(2026, 7, 2), von=dt.time(14))
    ablauf.einladen([a], t, "Büro", mail_senden=False)
    text = kalender.ics(t, ablauf.ort(t), "tafel.example").replace("\r\n ", "")
    # 14:00 Uhr Sommerzeit = 12:00 UTC; ohne Ende eine Stunde
    assert "DTSTART:20260702T120000Z" in text and "DTEND:20260702T130000Z" in text
    assert "SUMMARY:Neuanmeldung (1 Eingeladene/r)" in text
    assert "UID:warteliste-termin-" in text and "@tafel.example" in text


def test_kalendereintrag_nur_mit_recht(client, admin, modul_an, benutzer_mit_rolle, anmelden):
    t = termin()
    c = anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert c.get(reverse("warteliste:termin_kalender", args=[t.pk])).status_code == 403
