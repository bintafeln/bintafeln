// Kopfzeile selbst kürzen (ohne Bibliothek): Passt nicht alles in eine Zeile, werden nacheinander
// die Elemente mit .kuerz-1, .kuerz-2 … ausgeblendet (Klassen .kopf-kurz-N am <header>).
// Auf schmalen Bildschirmen steht die Suche ohnehin in einer eigenen Zeile und zählt nicht mit.
(function () {
  "use strict";
  var STUFEN = 5;
  var SCHMAL = "(max-width: 47.99rem)";

  function sichtbar(kopf) {
    var schmal = window.matchMedia(SCHMAL).matches;
    var liste = [];
    Array.prototype.forEach.call(kopf.children, function (el) {
      if (schmal && el.classList.contains("kopf-suche")) return;
      if (el.offsetParent === null || el.getClientRects().length === 0) return;
      liste.push(el.getBoundingClientRect());
    });
    return liste;
  }

  // Umgebrochen, wenn ein Element ganz unterhalb eines anderen liegt (gleiche Zeile überlappt).
  function umgebrochen(kopf) {
    var r = sichtbar(kopf);
    for (var i = 0; i < r.length; i++) {
      for (var j = 0; j < r.length; j++) {
        if (r[i].top >= r[j].bottom - 1) return true;
      }
    }
    return false;
  }

  function anpassen() {
    var kopf = document.querySelector("header.kopf");
    if (!kopf) return;
    for (var n = 1; n <= STUFEN; n++) kopf.classList.remove("kopf-kurz-" + n);
    for (var stufe = 1; stufe <= STUFEN && umgebrochen(kopf); stufe++) {
      kopf.classList.add("kopf-kurz-" + stufe);
    }
  }

  var wartet = null;
  function spaeter() {
    if (wartet) window.cancelAnimationFrame(wartet);
    wartet = window.requestAnimationFrame(function () { wartet = null; anpassen(); });
  }

  document.addEventListener("DOMContentLoaded", anpassen);
  window.addEventListener("load", spaeter);
  window.addEventListener("resize", spaeter);
  // Nachgeladene Teile der Kopfzeile (Wetter) ändern die Breite
  document.addEventListener("htmx:afterSettle", function (e) {
    if (e.target && e.target.closest && e.target.closest("header.kopf")) spaeter();
  });
})();
