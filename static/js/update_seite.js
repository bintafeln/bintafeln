// Update-Seite (ADR 0043): Die Seite lädt den Stand alle paar Sekunden neu. Damit ein vom
// Benutzer geöffnetes oder geschlossenes Protokoll dabei so bleibt und weiter unten mitläuft,
// merken wir uns den Zustand vor dem Austausch und stellen ihn danach wieder her.
(function () {
  "use strict";
  var zustand = null;

  function protokoll() {
    return document.getElementById("update-protokoll");
  }

  document.addEventListener("htmx:beforeSwap", function (ereignis) {
    if (!ereignis.detail.target || ereignis.detail.target.id !== "update-stand") return;
    var d = protokoll();
    if (!d) return;
    var pre = d.querySelector("pre");
    zustand = {
      offen: d.open,
      unten: !pre || pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 5,
      oben: pre ? pre.scrollTop : 0,
    };
  });

  document.addEventListener("htmx:afterSwap", function (ereignis) {
    if (!ereignis.detail.target || ereignis.detail.target.id !== "update-stand") return;
    var d = protokoll();
    if (!d || !zustand) return;
    d.open = zustand.offen;
    var pre = d.querySelector("pre");
    if (pre) pre.scrollTop = zustand.unten ? pre.scrollHeight : zustand.oben;
  });
})();
