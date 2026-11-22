// Nachrichten aufs Handy für Mitarbeitende (ADR 0158): Kachel „Nachrichten auf dieses Gerät“ auf
// „Mein Konto“. Schaltet Web Push für dieses Gerät ein und aus; der Service Worker /push-sw.js
// zeigt die Nachrichten an.
(function () {
  "use strict";
  var box = document.querySelector("[data-push]");
  if (!box) return;
  var ergebnis = box.querySelector(".push-ergebnis");
  function zeigen(was) {
    box.querySelectorAll("[data-zeige]").forEach(function (el) { el.hidden = el.dataset.zeige !== was; });
    box.dataset.pushStand = was;
  }
  var geht = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  var apple = /iPhone|iPad|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (!geht) { zeigen(apple ? "iphone" : "nicht"); return; }
  if (Notification.permission === "denied") { zeigen("blockiert"); return; }

  function senden(url, abo) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      body: JSON.stringify(abo ? { abo: abo.toJSON() } : {}),
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
  function abo() {
    return navigator.serviceWorker.getRegistration(box.dataset.sw).then(function (reg) {
      return reg ? reg.pushManager.getSubscription() : null;
    });
  }

  // Stand: Hat dieser Browser ein Abo, und gehört es zu diesem Konto?
  abo().then(function (vorhanden) {
    if (!vorhanden) return false;
    return senden(box.dataset.stand, vorhanden)
      .then(function (antwort) { return antwort.json(); })
      .then(function (d) { return !!d.an; });
  }).catch(function () { return false; }).then(function (an) { zeigen(an ? "an" : "aus"); });

  box.querySelector(".push-an").addEventListener("click", function () {
    ergebnis.textContent = "";
    navigator.serviceWorker.register(box.dataset.sw)
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
      .then(function (neu) { return senden(box.dataset.an, neu); })
      .then(function (antwort) {
        if (!antwort.ok) throw new Error("Server");
        zeigen("an");
      })
      .catch(function () { zeigen(Notification.permission === "denied" ? "blockiert" : "fehler"); });
  });

  box.querySelector(".push-aus").addEventListener("click", function () {
    ergebnis.textContent = "";
    abo().then(function (vorhanden) {
      if (!vorhanden) return null;
      return senden(box.dataset.aus, vorhanden).then(function () { return vorhanden.unsubscribe(); });
    }).catch(function () { /* auf dem Gerät abgeschaltet ist es dann trotzdem */ })
      .then(function () { zeigen("aus"); });
  });

  box.querySelector(".push-probe").addEventListener("click", function () {
    ergebnis.textContent = "Wird gesendet …";
    senden(box.dataset.probe)
      .then(function (antwort) { return antwort.json(); })
      .then(function (d) {
        ergebnis.textContent = d.ok ? "Gesendet. Die Nachricht sollte gleich erscheinen."
          : "Nicht gesendet. Bitte aus- und wieder einschalten.";
      })
      .catch(function () { ergebnis.textContent = "Nicht gesendet. Bitte noch einmal versuchen."; });
  });
})();
