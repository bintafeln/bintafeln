// Menü links einfahren und wieder ausfahren (breite Bildschirme). Der Zustand bleibt im Browser
// gespeichert; die Datei steht im <head> ohne „defer“, damit das Menü beim Laden nicht aufblitzt.
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
