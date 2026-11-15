// Live-Vorschau neben dem Serienbrief-Editor: schickt das Formular (ohne zu speichern) an
// serienbriefe:vorlage_bild und zeigt die erste Seite des PDFs als Bild. Neu geladen wird erst,
// wenn sich das Formular kurz nicht mehr ändert; ist die Vorschau ausgeblendet (schmaler
// Bildschirm), passiert nichts.
(function () {
  "use strict";

  var bild = document.querySelector("img[data-brief-vorschau]");
  if (!bild) return;
  var formular = document.getElementById(bild.dataset.formular);
  var karte = bild.closest(".brief-vorschau");
  var stand = karte.querySelector("[data-brief-vorschau-stand]");
  var RUHE = 700; // ms ohne Änderung, bevor neu geladen wird
  var gesehen = null, seit = 0, geladen = null, laeuft = false, blobAdresse = null, erstes = true;

  function inhalt() { return new URLSearchParams(new FormData(formular)).toString(); }

  function laden(daten) {
    laeuft = true;
    geladen = daten;
    karte.classList.add("laedt");
    var seiten = 1;
    fetch(bild.dataset.briefVorschau, {method: "POST", body: new FormData(formular), credentials: "same-origin"})
      .then(function (antwort) {
        if (!antwort.ok) throw new Error("Status " + antwort.status);
        seiten = parseInt(antwort.headers.get("X-Seiten") || "1", 10);
        return antwort.blob();
      })
      .then(function (blob) {
        if (blobAdresse) URL.revokeObjectURL(blobAdresse);
        blobAdresse = URL.createObjectURL(blob);
        bild.src = blobAdresse;
        stand.textContent = seiten > 1
          ? "Seite 1 von " + seiten + " mit einem erfundenen Empfänger. Antippen zeigt alle Seiten als PDF."
          : "Mit einem erfundenen Empfänger. Antippen öffnet das PDF.";
      })
      .catch(function () {
        geladen = null; // in ein paar Sekunden erneut versuchen
        seit = Date.now() + 5000;
        stand.textContent = "Die Vorschau ist gerade nicht möglich. „Vorschau (PDF)“ zeigt den Brief trotzdem.";
      })
      .finally(function () {
        laeuft = false;
        karte.classList.remove("laedt");
      });
  }

  function pruefen() {
    if (laeuft || karte.offsetParent === null) return;
    var daten = inhalt();
    if (daten !== gesehen) { gesehen = daten; seit = Date.now(); }
    if (daten !== geladen && Date.now() - seit >= (erstes ? 0 : RUHE)) { erstes = false; laden(daten); }
  }

  window.setInterval(pruefen, 300);
  pruefen();
})();
