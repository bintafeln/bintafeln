// Menü links einfahren und wieder ausfahren (breite Bildschirme); aufgeklappte Punkte ganz zeigen.
// Der Zustand bleibt im Browser gespeichert; die Datei steht im <head> ohne „defer“, damit das
// Menü beim Laden nicht aufblitzt.
(function () {
  "use strict";
  var SCHLUESSEL = "bintafeln-menue-eingefahren";
  var html = document.documentElement;

  function lesen() {
    try { return localStorage.getItem(SCHLUESSEL) === "1"; } catch (e) { return false; }
  }

  function setzen(zu) {
    html.classList.toggle("menue-eingefahren", zu);
    try { localStorage.setItem(SCHLUESSEL, zu ? "1" : "0"); } catch (e) { /* ohne Speicher */ }
    document.querySelectorAll("[data-menue-ausfahren]").forEach(function (k) {
      k.setAttribute("aria-expanded", zu ? "false" : "true");
    });
  }

  html.classList.toggle("menue-eingefahren", lesen());
  document.addEventListener("DOMContentLoaded", function () {
    // Auf Werkseinstellungen zurückgesetzt (Admin): gemerkte Ansichten dieses Browsers vergessen
    var stand = document.body.dataset.ansichtStand;
    try {
      if (stand !== undefined && localStorage.getItem("bintafeln-ansicht-stand") !== stand) {
        if (localStorage.getItem("bintafeln-ansicht-stand") !== null) {
          Object.keys(localStorage).forEach(function (k) {
            if (k.indexOf("bintafeln-") === 0) localStorage.removeItem(k);
          });
          html.classList.remove("menue-eingefahren");
        }
        localStorage.setItem("bintafeln-ansicht-stand", stand);
      }
    } catch (e) { /* ohne Speicher */ }
    // Aufgeklappter Menüpunkt weiter unten: ganz zeigen, also das Menü (bzw. die Seite) so weit
    // hochschieben, dass alle Unterpunkte zu sehen sind; der Titel bleibt dabei immer sichtbar
    var nav = document.querySelector(".seitenmenue");
    var geklickt = false;
    if (nav) {
      nav.addEventListener("click", function (e) {
        if (e.target.closest("summary")) geklickt = true;
      });
      nav.addEventListener("toggle", function (e) {
        var bereich = e.target;
        if (!geklickt || !bereich.open) return;
        geklickt = false;
        var ruhig = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        requestAnimationFrame(function () {
          bereich.scrollIntoView({ block: "nearest", behavior: ruhig ? "auto" : "smooth" });
        });
      }, true);  // „toggle“ steigt nicht auf
    }
    document.querySelectorAll("[data-menue-einfahren]").forEach(function (k) {
      k.addEventListener("click", function () { setzen(true); });
    });
    document.querySelectorAll("[data-menue-ausfahren]").forEach(function (k) {
      k.addEventListener("click", function () {
        setzen(false);
        var menue = document.querySelector(".seitenmenue");
        if (menue) menue.focus();
      });
    });
  });
})();
