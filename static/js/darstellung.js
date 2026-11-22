// Darstellung „Wie das Gerät“ (ADR 0164): Steht das Gerät auf dunkel, bekommt die Seite den
// Nachtmodus (data-nacht am <html>). Läuft im Kopf der Seite vor dem ersten Zeichnen, damit die
// Seite nicht erst hell aufblitzt; folgt auch, wenn das Gerät abends selbst umschaltet.
(function () {
  "use strict";
  var wurzel = document.documentElement;
  if (wurzel.dataset.darstellung !== "geraet" || !window.matchMedia) return;
  var dunkel = window.matchMedia("(prefers-color-scheme: dark)");
  function setzen() { wurzel.toggleAttribute("data-nacht", dunkel.matches); }
  setzen();
  if (dunkel.addEventListener) dunkel.addEventListener("change", setzen);
})();
