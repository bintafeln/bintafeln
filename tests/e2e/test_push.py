"""Browser-Test: Nachrichten aufs eigene Gerät einschalten (ADR 0158)."""

from django.urls import reverse
from playwright.sync_api import expect


def test_nachrichten_auf_dieses_geraet_einschalten(angemeldet, admin, monkeypatch):
    """„Mein Konto → Nachrichten auf dieses Gerät“ (ADR 0158): einschalten, Probe, ausschalten.
    Den Push-Dienst des Browsers gibt es im Test nicht; er ist durch ein Abo mit erfundener
    Adresse ersetzt."""
    from apps.core import push
    from apps.core.models import PushAbo
    from tests.test_aufruf_handy import _browser

    gesendet = []
    monkeypatch.setattr(push, "_senden", lambda a, d, k: gesendet.append(a) or 201)
    _, p256dh, auth = _browser()
    seite = angemeldet(admin)
    seite.add_init_script(
        """(() => {
      let abo = null;
      const neu = () => ({
        toJSON: () => ({ endpoint: "https://fcm.googleapis.com/fcm/send/test",
                         keys: { p256dh: "P256DH", auth: "AUTH" } }),
        unsubscribe: () => { abo = null; return Promise.resolve(true); },
      });
      const reg = { pushManager: {
        getSubscription: () => Promise.resolve(abo),
        subscribe: () => { abo = neu(); return Promise.resolve(abo); },
      } };
      Object.defineProperty(navigator, "serviceWorker", { value: {
        register: () => Promise.resolve(reg), ready: Promise.resolve(reg),
        getRegistration: () => Promise.resolve(reg),
      } });
      window.PushManager = window.PushManager || function () {};
      window.Notification = { permission: "default",
                              requestPermission: () => Promise.resolve("granted") };
    })();""".replace("P256DH", p256dh).replace("AUTH", auth)
    )
    seite.goto(reverse("konten:mein_konto"))
    kachel = seite.locator("#push")
    expect(kachel.get_by_text("Im Moment: ausgeschaltet.")).to_be_visible()
    kachel.get_by_role("button", name="🔔 Einschalten").click()
    expect(kachel.get_by_text("Im Moment: eingeschaltet.")).to_be_visible()
    assert PushAbo.objects.get().benutzer == admin
    kachel.get_by_role("button", name="Probe-Nachricht schicken").click()
    expect(kachel.locator(".push-ergebnis")).to_contain_text("Gesendet")
    assert gesendet == ["https://fcm.googleapis.com/fcm/send/test"]
    kachel.get_by_role("button", name="Ausschalten").click()
    expect(kachel.get_by_text("Im Moment: ausgeschaltet.")).to_be_visible()
    assert not PushAbo.objects.exists()
