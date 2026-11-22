// Service Worker für Nachrichten an Mitarbeitende (ADR 0158): zeigt Push-Nachrichten an, auch wenn
// bintafeln nicht offen ist; ein Tippen öffnet die Seite, um die es geht. Ausgeliefert von
// views_push.service_worker unter /push-sw.js. Er speichert nichts zwischen und greift in keine
// Seite ein.
"use strict";
var SYMBOL = "__SYMBOL__";
var START = "__START__";

self.addEventListener("push", function (e) {
  var d = {};
  try { d = e.data ? e.data.json() : {}; } catch (fehler) { d = { text: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.titel || "", {
    body: d.text || "", icon: SYMBOL, badge: SYMBOL, tag: d.kennung || "bintafeln", renotify: true,
    requireInteraction: true, vibrate: [300, 100, 300, 100, 300], data: { link: d.link || START },
  }));
});

self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  var link = (e.notification.data && e.notification.data.link) || START;
  var ziel = new URL(link, self.location.origin);
  if (ziel.origin !== self.location.origin) ziel = new URL(START, self.location.origin);
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (liste) {
    for (var i = 0; i < liste.length; i++) {
      if ("focus" in liste[i] && "navigate" in liste[i]) {
        return liste[i].focus().then(function (fenster) { return fenster.navigate(ziel.href); });
      }
    }
    return self.clients.openWindow(ziel.href);
  }));
});
