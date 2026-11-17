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
  // Mit Teilen-Menü (iPad/iPhone, auch in der App ohne Browserleiste): das PDF teilen, dort
  // „Drucken“; sonst der Druckdialog des Browsers.
  if (drucken) drucken.addEventListener("click", function () {
    var link = ansicht.querySelector("a[download]");
    if (link && navigator.canShare && navigator.share) {
      fetch(link.href).then(function (a) { return a.blob(); }).then(function (blob) {
        var datei = new File([blob], link.getAttribute("download"), { type: "application/pdf" });
        if (navigator.canShare({ files: [datei] })) {
          return navigator.share({ files: [datei], title: datei.name });
        }
        window.print();
      }).catch(function () { /* abgebrochen */ });
      return;
    }
    window.print();
  });
  var zurueck = ansicht.querySelector("[data-zurueck]");
  if (zurueck) zurueck.addEventListener("click", function () {
    if (window.history.length > 1) { window.history.back(); return; }
    window.close();
    setTimeout(function () { window.location.href = "/"; }, 300);
  });
})();
