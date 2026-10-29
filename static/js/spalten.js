// Spalten einer Tabelle ein- und ausblenden: <table data-spalten="name">, Kopf- und Datenzellen mit
// data-spalte="x", Häkchen (value="x") in einem Element mit data-spalten-wahl="name". Was zu
// Beginn aus ist, steht in data-vorgabe-aus. Die Wahl merkt sich der Browser (localStorage
// bintafeln-spalten-<name>); nach einem htmx-Austausch der Liste gilt sie weiter. Ohne
// JavaScript sind alle Spalten zu sehen.
(function () {
  "use strict";

  function lesen(name, vorgabe) {
    try {
      var wert = localStorage.getItem("bintafeln-spalten-" + name);
      return wert === null ? vorgabe : JSON.parse(wert);
    } catch (e) { return vorgabe; }
  }

  function anwenden(name, aus) {
    document.querySelectorAll('table[data-spalten="' + name + '"] [data-spalte]').forEach(function (zelle) {
      zelle.hidden = aus.indexOf(zelle.dataset.spalte) >= 0;
    });
  }

  function einrichten() {
    document.querySelectorAll("[data-spalten-wahl]").forEach(function (wahl) {
      var name = wahl.dataset.spaltenWahl;
      var vorgabe = (wahl.dataset.vorgabeAus || "").split(" ").filter(Boolean);
      var aus = lesen(name, vorgabe);
      wahl.hidden = false;
      wahl.querySelectorAll("input[type=checkbox]").forEach(function (k) {
        k.checked = aus.indexOf(k.value) < 0;
        if (k.dataset.verbunden) return;
        k.dataset.verbunden = "1";
        k.addEventListener("change", function () {
          var neu = [];
          wahl.querySelectorAll("input[type=checkbox]").forEach(function (x) {
            if (!x.checked) neu.push(x.value);
          });
          try { localStorage.setItem("bintafeln-spalten-" + name, JSON.stringify(neu)); } catch (e) { /* ohne Speicher */ }
          anwenden(name, neu);
        });
      });
      anwenden(name, aus);
    });
  }

  einrichten();
  document.addEventListener("htmx:afterSwap", einrichten);
})();
