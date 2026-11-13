// Service Worker für „Wartezeit aufs Handy“ (ADR 0134): zeigt Push-Nachrichten an, auch wenn die
// Seite geschlossen ist; ein Tippen auf die Nachricht öffnet die Wartezeit. Ausgeliefert von
// views_warten.service_worker unter /warten/sw.js (Bereich /warten/).
"use strict";
var SYMBOL = "__SYMBOL__";
var START = "__START__";

self.addEventListener("push", function (e) {
  var d = {};
  try { d = e.data ? e.data.json() : {}; } catch (fehler) { d = { text: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.titel || "", {
    body: d.text || "", icon: SYMBOL, badge: SYMBOL, tag: "wartezeit", renotify: true,
    requireInteraction: true, vibrate: [300, 100, 300, 100, 300],
  }));
});

self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (liste) {
    for (var i = 0; i < liste.length; i++) {
      if (liste[i].url.indexOf(START) >= 0 && "focus" in liste[i]) return liste[i].focus();
    }
    return self.clients.openWindow(START);
  }));
});
