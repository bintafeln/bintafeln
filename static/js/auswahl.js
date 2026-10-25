// Auswahl in Listen: Kästchen ganz links je Zeile, im Kopf „alle/keine“ (data-alle="<name>").
// Zeigt die Zahl der angehakten Zeilen in [data-auswahl-zahl]; ohne Haken gilt die ganze Liste.
(function () {
  function zaehlen(form) {
    const anzeige = form.querySelector("[data-auswahl-zahl]");
    if (!anzeige) return;
    const n = form.querySelectorAll('input[type="checkbox"][name="id"]:checked').length;
    anzeige.textContent = n ? n + " ausgewählt" : "keine ausgewählt – es gilt die ganze Liste";
  }
  document.addEventListener("change", function (e) {
    const feld = e.target;
    const form = feld.form;
    if (!form) return;
    if (feld.dataset.alle) {
      form.querySelectorAll('input[type="checkbox"][name="' + feld.dataset.alle + '"]')
        .forEach(function (c) { c.checked = feld.checked; });
    }
    zaehlen(form);
  });
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form[data-auswahl]").forEach(zaehlen);
  });
})();
