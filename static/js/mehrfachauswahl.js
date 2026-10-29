// Mehrfachauswahl als aufklappbares Menü (apps/core/forms.py, Mehrfachauswahl): oben steht, was
// gewählt ist; Suchfeld und „alle/keine“ erscheinen nur mit JavaScript. Ein Klick daneben klappt
// das Menü wieder zu.
(function () {
  "use strict";
  document.querySelectorAll("details[data-mehrfach]").forEach(function (menue) {
    var text = menue.querySelector(".mehrfach-text");
    var kopf = menue.querySelector(".mehrfach-kopf");
    var kaestchen = Array.prototype.slice.call(menue.querySelectorAll('input[type="checkbox"]'));
    var suche = menue.querySelector("[data-mehrfach-suche]");
    var knoepfe = menue.querySelector(".mehrfach-knoepfe");
    if (suche) suche.hidden = false;
    if (knoepfe) knoepfe.hidden = false;

    function zeigen() {
      var namen = kaestchen.filter(function (k) { return k.checked; })
        .map(function (k) { return k.parentNode.textContent.trim(); });
      text.textContent = namen.length ? namen.join(", ") : menue.dataset.leer;
      var zahl = kopf.querySelector(".mehrfach-zahl");
      if (!zahl && namen.length) {
        zahl = document.createElement("span");
        zahl.className = "mehrfach-zahl";
        kopf.appendChild(zahl);
      }
      if (zahl) { zahl.textContent = namen.length; zahl.hidden = !namen.length; }
    }
    kaestchen.forEach(function (k) { k.addEventListener("change", zeigen); });
    if (suche) {
      suche.addEventListener("input", function () {
        var begriff = suche.value.trim().toLowerCase();
        kaestchen.forEach(function (k) {
          k.parentNode.hidden = begriff && k.parentNode.textContent.toLowerCase().indexOf(begriff) < 0;
        });
      });
      // Enter im Suchfeld schickt nicht das ganze Formular ab
      suche.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
    }
    function setzen(wert) {
      kaestchen.forEach(function (k) { if (!k.parentNode.hidden) k.checked = wert; });
      zeigen();
    }
    var alle = menue.querySelector("[data-mehrfach-alle]");
    var keine = menue.querySelector("[data-mehrfach-keine]");
    if (alle) alle.addEventListener("click", function () { setzen(true); });
    if (keine) keine.addEventListener("click", function () { setzen(false); });
    menue.addEventListener("toggle", function () {
      if (menue.open && suche) suche.focus();
    });
    document.addEventListener("click", function (e) {
      if (menue.open && !menue.contains(e.target)) menue.open = false;
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && menue.open) { menue.open = false; kopf.focus(); }
    });
  });
})();
