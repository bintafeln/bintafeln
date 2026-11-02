// Statistik: Grafik (oder „⤢ Groß“) anklicken zeigt sie bildschirmfüllend in einem Dialog.
// „← Zurück“ oder Esc schließt ihn; die Seite darunter bleibt, wo sie war.
(function () {
  "use strict";
  var dialog = document.getElementById("diagramm-gross");
  if (!dialog) return;
  var inhalt = dialog.querySelector(".diagramm-gross-inhalt");
  var titel = document.getElementById("diagramm-gross-titel");
  var vorher = null;

  function oeffnen(id, ausloeser) {
    var abschnitt = document.getElementById(id);
    var bild = abschnitt && abschnitt.querySelector(".diagramm-rahmen svg");
    if (!bild) return;
    vorher = ausloeser;
    titel.textContent = abschnitt.querySelector("h2").textContent;
    inhalt.innerHTML = "";
    var legende = abschnitt.querySelector(".legende");
    if (legende) inhalt.appendChild(legende.cloneNode(true));
    inhalt.appendChild(bild.cloneNode(true));
    dialog.showModal();
  }

  // Delegiert, damit „Groß“ auch in Abschnitten funktioniert, die htmx nachlädt
  // (anklickbare Legende tauscht den Abschnitt aus).
  document.addEventListener("click", function (e) {
    var el = e.target.closest("[data-gross]");
    if (el) oeffnen(el.getAttribute("data-gross"), el);
  });
  dialog.querySelector("[data-zurueck]").addEventListener("click", function () { dialog.close(); });
  dialog.addEventListener("close", function () {
    inhalt.innerHTML = "";
    if (vorher && vorher.focus) vorher.focus({ preventScroll: true });
  });
})();
