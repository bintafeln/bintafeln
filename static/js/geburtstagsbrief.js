// Geburtstagsbrief auf der Startseite (ADR 0170): Liegt in der Seite ein Brief bereit
// (template.geburtstagsbrief), legt er sich als Dialog über die Seite – festlich, ohne Ton und
// ohne Rütteln. „Gratuliert“ bzw. „Danke!“ schickt das Formular ab (dann kommt er nicht wieder),
// „Später“ und Esc schließen ihn nur bis zum nächsten Besuch der Startseite.
(function () {
  "use strict";

  function zeigen() {
    var vorlage = document.querySelector("template.geburtstagsbrief");
    if (!vorlage || document.querySelector("dialog.geburtstagsbrief-dialog")) return;
    var dialog = document.createElement("dialog");
    dialog.className = "geburtstagsbrief-dialog";
    dialog.setAttribute("aria-label", vorlage.dataset.titel || "Geburtstag");
    dialog.appendChild(vorlage.content.cloneNode(true));
    dialog.addEventListener("close", function () { dialog.remove(); });
    var spaeter = dialog.querySelector("[data-gb-spaeter]");
    if (spaeter) spaeter.addEventListener("click", function () { dialog.close(); });
    document.body.appendChild(dialog);
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", zeigen);
  else zeigen();
})();
