// Druckansicht eines PDFs (ADR 0141): „Drucken“ öffnet den Druckdialog des Geräts, „Zurück“
// führt zur vorigen Seite oder schließt das Fenster, wenn es für das PDF geöffnet wurde.
// Querformat: Die Seite meldet dem Drucker die Ausrichtung der ersten PDF-Seite.
(function () {
  "use strict";
  var ansicht = document.querySelector(".druckansicht");
  if (!ansicht) return;
  if (ansicht.dataset.quer === "1") {
    var stil = document.createElement("style");
    stil.textContent = "@page { size: landscape; }";
    document.head.appendChild(stil);
  }
  var drucken = ansicht.querySelector("[data-drucken]");
  if (drucken) drucken.addEventListener("click", function () { window.print(); });
  var zurueck = ansicht.querySelector("[data-zurueck]");
  if (zurueck) zurueck.addEventListener("click", function () {
    if (window.history.length > 1) { window.history.back(); return; }
    window.close();
    setTimeout(function () { window.location.href = "/"; }, 300);
  });
})();
