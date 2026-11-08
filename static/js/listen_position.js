// Beim Verlassen einer Seite die Scroll-Höhe merken (je Pfad samt Filter) und beim Zurückkommen –
// vor allem über den Zurück-Knopf des Browsers – wieder genau dort landen, statt ganz oben. So
// bleibt man in langen Listen (Adressbuch, Kunden, Anträge, Mitglieder …) an seiner Stelle: Wer
// aus der Liste eine Person öffnet und dann zurückgeht, steht wieder bei derselben Zeile.
//
// Arbeitet rein im Browser (sessionStorage, gilt also nur für das eigene Fenster und endet mit
// ihm). Ohne Speicher oder JavaScript bleibt alles wie bisher (oben). Das Merken der Position nach
// dem Absenden eines Formulars an dieselbe Seite macht weiterhin position.js; die beiden stören
// sich nicht, weil jenes nur bei einem eigenen Schlüssel greift.
(function () {
  "use strict";
  var SCHLUESSEL = "bintafeln-listen-position";
  var HALTBAR = 24 * 60 * 60 * 1000; // einen Tag aufheben
  var MAX = 40; // nicht unbegrenzt viele Seiten merken

  function laden() {
    try {
      return JSON.parse(sessionStorage.getItem(SCHLUESSEL) || "{}");
    } catch (fehler) {
      return {};
    }
  }
  function sichern(stand) {
    try {
      sessionStorage.setItem(SCHLUESSEL, JSON.stringify(stand));
    } catch (fehler) {
      /* ohne Speicher: wie bisher oben */
    }
  }
  function hier() {
    return location.pathname + location.search;
  }

  // Den Browser nicht selbst springen lassen; wir stellen die Höhe her.
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";

  // Position sichern, sobald die Seite verlassen oder versteckt wird (Klick auf eine Person,
  // Zurück/Vor, Tab-Wechsel). „pagehide“ feuert auch, wenn die Seite in den Zwischenspeicher wandert.
  window.addEventListener("pagehide", function () {
    var stand = laden();
    stand[hier()] = { y: window.scrollY, zeit: Date.now() };
    var jetzt = Date.now();
    var paare = Object.keys(stand)
      .filter(function (k) {
        return stand[k] && jetzt - stand[k].zeit < HALTBAR;
      })
      .map(function (k) {
        return [k, stand[k]];
      })
      .sort(function (a, b) {
        return b[1].zeit - a[1].zeit;
      })
      .slice(0, MAX);
    var sauber = {};
    paare.forEach(function (p) {
      sauber[p[0]] = p[1];
    });
    sichern(sauber);
  });

  function herstellen() {
    if (location.hash) return; // eine Sprungmarke hat Vorrang
    var stand = laden()[hier()];
    if (!stand || Date.now() - stand.zeit > HALTBAR || !(stand.y > 0)) return;
    window.scrollTo(0, stand.y);
  }

  // „pageshow“ deckt beide Fälle ab: normales Laden und Rückkehr aus dem Zwischenspeicher (bfcache).
  window.addEventListener("pageshow", herstellen);
})();
