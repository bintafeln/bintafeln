// Auswahl in Listen: Kästchen ganz links je Zeile (name="id"), im Kopf „alle/keine“
// (data-alle="id"). Die Kästchen dürfen über form="…" zu einem Formular außerhalb der Tabelle
// gehören. Zeigt die Zahl der angehakten Zeilen in [data-auswahl-zahl]; ohne Haken gilt alles.
(function () {
  function kaestchen(form, name) {
    return Array.from(form.elements).filter(function (e) {
      return e.type === "checkbox" && e.name === name;
    });
  }
  function zaehlen(form) {
    const anzeige = document.querySelector('[data-auswahl-zahl="' + (form.id || "") + '"]') ||
      form.querySelector("[data-auswahl-zahl]");
    if (!anzeige) return;
    const n = kaestchen(form, "id").filter(function (c) { return c.checked; }).length;
    anzeige.textContent = n ? n + " ausgewählt" : "keine ausgewählt – es gilt die ganze Liste";
  }
  document.addEventListener("change", function (e) {
    const feld = e.target;
    const form = feld.form;
    if (!form) return;
    if (feld.dataset.alle) {
      kaestchen(form, feld.dataset.alle).forEach(function (c) { c.checked = feld.checked; });
    }
    zaehlen(form);
  });
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form[data-auswahl]").forEach(zaehlen);
  });
  document.addEventListener("htmx:afterSwap", function () {
    document.querySelectorAll("form[data-auswahl]").forEach(zaehlen);
  });
})();
