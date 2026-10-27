// Auswahlfeld „Springen zu“ (z. B. Statistik): springt sofort zum gewählten Abschnitt.
(function () {
  "use strict";
  document.querySelectorAll("select[data-sprung]").forEach(function (feld) {
    feld.addEventListener("change", function () {
      var ziel = feld.value && document.getElementById(feld.value);
      if (!ziel) return;
      ziel.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", "#" + feld.value);
      feld.value = "";
    });
  });
})();
