// Wartezeit aufs Handy (ADR 0090, 0134): Seite alle paar Sekunden neu laden und die
// Benachrichtigung (Push-Nachricht) ein- und ausschalten. Während der Browser nach der Erlaubnis
// fragt, lädt die Seite nicht neu. Ohne JavaScript lädt ein <meta refresh> neu, ohne Push.
(function () {
  "use strict";
  var anzeige = document.querySelector("[data-aktualisieren]");
  var pause = false;
  if (anzeige) {
    var sekunden = parseInt(anzeige.dataset.aktualisieren, 10) || 30;
    var neu = function () {
      if (pause) { setTimeout(neu, 3000); return; }
      location.reload();
    };
    setTimeout(neu, sekunden * 1000);
  }

  var box = document.querySelector("[data-push]");
  if (!box) return;
  function zeigen(was) {
    box.querySelectorAll("[data-zeige]").forEach(function (el) { el.hidden = el.dataset.zeige !== was; });
  }
  var geht = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  var apple = /iPhone|iPad|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (!geht) { zeigen(apple ? "iphone" : "nicht"); return; }
  if (Notification.permission === "denied") { zeigen("blockiert"); return; }
  zeigen(box.dataset.istAn ? "an" : "aus");

  function senden(url, daten) {
    return fetch(url, {
      method: "POST", credentials: "same-origin", body: JSON.stringify(daten || {}),
      headers: { "Content-Type": "application/json", "X-CSRFToken": box.dataset.csrf },
    });
  }
  function bytes(text) {
    var b64 = (text + "===".slice((text.length + 3) % 4)).replace(/-/g, "+").replace(/_/g, "/");
    var roh = atob(b64);
    var feld = new Uint8Array(roh.length);
    for (var i = 0; i < roh.length; i++) feld[i] = roh.charCodeAt(i);
    return feld;
  }

  box.querySelector(".push-an").addEventListener("click", function () {
    pause = true;
    navigator.serviceWorker.register(box.dataset.sw, { scope: box.dataset.bereich })
      .then(function () { return navigator.serviceWorker.ready; })
      .then(function (reg) {
        return Notification.requestPermission().then(function (erlaubt) {
          if (erlaubt !== "granted") throw new Error("nicht erlaubt");
          return reg.pushManager.getSubscription().then(function (alt) {
            return alt || reg.pushManager.subscribe({
              userVisibleOnly: true, applicationServerKey: bytes(box.dataset.schluessel),
            });
          });
        });
      })
      .then(function (abo) { return senden(box.dataset.an, { abo: abo.toJSON(), sprache: box.dataset.sprache }); })
      .then(function (antwort) {
        if (!antwort.ok) throw new Error("Server");
        box.dataset.istAn = "1";
        zeigen("an");
      })
      .catch(function () { zeigen(Notification.permission === "denied" ? "blockiert" : "fehler"); })
      .then(function () { pause = false; });
  });

  box.querySelector(".push-aus").addEventListener("click", function () {
    senden(box.dataset.aus).then(function () {
      delete box.dataset.istAn;
      zeigen("aus");
      return navigator.serviceWorker.getRegistration(box.dataset.bereich);
    }).then(function (reg) {
      return reg && reg.pushManager.getSubscription().then(function (abo) { return abo && abo.unsubscribe(); });
    }).catch(function () { /* abgeschaltet ist es auf dem Server ohnehin */ });
  });
})();
