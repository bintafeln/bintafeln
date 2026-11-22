// Tour am Handy: Beim Öffnen zur nächsten offenen Station springen (sobald schon eine angefahren
// ist). Führt die Adresse selbst an eine Stelle (#halt-3, #fahrt), bleibt es dabei.
(function () {
  "use strict";
  if (window.location.hash) { return; }
  var ziel = document.querySelector("[data-tour-aktuell]");
  if (ziel && ziel.scrollIntoView) {
    ziel.scrollIntoView({ block: "start" });
  }
})();
