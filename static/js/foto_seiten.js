// Foto eines Nachweises mit mehreren Seiten (ADR 0122): Ein Dateifeld ersetzt bei jeder neuen
// Aufnahme seine bisherige Auswahl. Dieses Skript sammelt die Aufnahmen stattdessen: Jede neue
// Auswahl kommt zu den schon gewählten Seiten dazu, die Liste darunter zeigt sie und lässt
// einzelne wieder entfernen. Ohne JavaScript (oder ohne DataTransfer) bleibt das einfache Feld.
(function () {
  "use strict";
  var HOECHSTENS = 10;
  function einrichten(feld) {
    if (feld.dataset.fotoBereit || typeof DataTransfer === "undefined") return;
    feld.dataset.fotoBereit = "1";
    var liste = feld.form.querySelector("[data-foto-liste]");
    var seiten = [];
    function uebernehmen() {
      var sammlung = new DataTransfer();
      seiten.forEach(function (datei) { sammlung.items.add(datei); });
      feld.files = sammlung.files;
      if (!liste) return;
      liste.textContent = "";
      liste.hidden = seiten.length === 0;
      seiten.forEach(function (datei, nr) {
        var zeile = document.createElement("li");
        zeile.textContent = "Seite " + (nr + 1) + ": " + datei.name + " ";
        var weg = document.createElement("button");
        weg.type = "button";
        weg.className = "link-knopf";
        weg.textContent = "entfernen";
        weg.setAttribute("aria-label", "Seite " + (nr + 1) + " entfernen");
        weg.addEventListener("click", function () { seiten.splice(nr, 1); uebernehmen(); });
        zeile.appendChild(weg);
        liste.appendChild(zeile);
      });
    }
    feld.addEventListener("change", function () {
      Array.prototype.forEach.call(feld.files, function (datei) {
        if (seiten.length < HOECHSTENS) seiten.push(datei);
      });
      uebernehmen();
    });
  }
  function alle() {
    Array.prototype.forEach.call(document.querySelectorAll("input[data-foto-seiten]"), einrichten);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", alle);
  else alle();
  document.addEventListener("htmx:afterSwap", alle);
})();
