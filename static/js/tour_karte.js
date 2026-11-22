// Routenvorschau in der Tourenplanung: Die Google-Karte wird erst nach einem Klick geladen
// („Karte zeigen“); die Wahl merkt sich das Gerät (localStorage bintafeln-tourkarte). Der Baustein
// touren/_karte.html kann per htmx neu geladen werden – dann richtet er sich wieder ein.
(function () {
  "use strict";
  var MERKER = "bintafeln-tourkarte";

  function gemerkt() {
    try { return window.localStorage.getItem(MERKER) === "1"; } catch (fehler) { return false; }
  }

  function merken(an) {
    try {
      if (an) { window.localStorage.setItem(MERKER, "1"); } else { window.localStorage.removeItem(MERKER); }
    } catch (fehler) { /* privater Modus: dann eben ohne Merken */ }
  }

  function zeigen(rahmen) {
    var karten = rahmen.querySelector("[data-tourkarte-karten]");
    if (!karten) { return; }
    karten.querySelectorAll(".tour-karte[data-src]").forEach(function (platz) {
      if (platz.querySelector("iframe")) { return; }
      var bild = document.createElement("iframe");
      bild.src = platz.getAttribute("data-src");
      bild.title = platz.getAttribute("data-titel") || "Route der Tour";
      bild.loading = "lazy";
      bild.referrerPolicy = "strict-origin";
      bild.setAttribute("allowfullscreen", "");
      platz.appendChild(bild);
    });
    karten.hidden = false;
    var frage = rahmen.querySelector("[data-tourkarte-frage]");
    var aus = rahmen.querySelector("[data-tourkarte-aus]");
    if (frage) { frage.hidden = true; }
    if (aus) { aus.hidden = false; }
  }

  function verbergen(rahmen) {
    var karten = rahmen.querySelector("[data-tourkarte-karten]");
    if (karten) {
      karten.hidden = true;
      karten.querySelectorAll("iframe").forEach(function (bild) { bild.remove(); });
    }
    var frage = rahmen.querySelector("[data-tourkarte-frage]");
    var aus = rahmen.querySelector("[data-tourkarte-aus]");
    if (frage) { frage.hidden = false; }
    if (aus) { aus.hidden = true; }
  }

  function einrichten() {
    if (!gemerkt()) { return; }
    document.querySelectorAll("[data-tourkarte]").forEach(zeigen);
  }

  document.addEventListener("click", function (ereignis) {
    var knopf = ereignis.target.closest("[data-tourkarte-zeigen], [data-tourkarte-verbergen]");
    if (!knopf) { return; }
    var rahmen = knopf.closest("[data-tourkarte]");
    if (knopf.hasAttribute("data-tourkarte-zeigen")) {
      merken(true);
      zeigen(rahmen);
    } else {
      merken(false);
      verbergen(rahmen);
    }
  });
  document.body.addEventListener("htmx:afterSwap", einrichten);
  einrichten();
})();
