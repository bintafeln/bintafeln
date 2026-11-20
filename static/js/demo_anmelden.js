// Demo-Betrieb: „Anmelden als …“ trägt Benutzername und Passwort des gewählten Demo-Zugangs in
// das Anmeldeformular ein und meldet an. Ohne JavaScript bleibt die Tabelle zum Abtippen.
(function () {
  "use strict";
  var kasten = document.getElementById("demo-zugaenge");
  var name = document.querySelector('input[name="username"]');
  var passwort = document.querySelector('input[name="password"]');
  if (!kasten || !name || !passwort) return;
  kasten.addEventListener("click", function (ereignis) {
    var knopf = ereignis.target.closest("[data-demo-name]");
    if (!knopf) return;
    name.value = knopf.dataset.demoName;
    passwort.value = knopf.dataset.demoPasswort;
    name.form.requestSubmit ? name.form.requestSubmit() : name.form.submit();
  });
})();
