// Hinweis auf die Sprachwahl im Antragsformular: ein roter, blinkender Pfeil zeigt einmal je
// Sitzung für einige Sekunden auf die Auswahl oben; passt die gewählte Staatsangehörigkeit nicht
// zur Sprache der Seite, erscheint er in der passenden Sprache mit einem Knopf zum Umstellen.
// Beim Umstellen nimmt die Seite die schon eingetragenen Angaben mit (nur in diesem Tab, nach dem
// Laden gelöscht); hochgeladene Dateien muss man neu wählen.
(function () {
  var auswahl = document.getElementById("sprache");
  var hinweis = document.getElementById("sprach-hinweis");
  if (!auswahl || !hinweis) return;
  var texte = JSON.parse(document.getElementById("sprach-hinweise").textContent);
  var landSprache = JSON.parse(document.getElementById("land-sprache").textContent);
  var jetzt = auswahl.value;
  var formular = document.querySelector("form.antrag-formular");
  var ENTWURF = "bintafeln-antrag-entwurf", GESEHEN = "bintafeln-sprachhinweis";
  var timer = null, beimLaden = false;

  function speicher(art, schluessel, wert) {
    try {
      if (art === "lesen") return sessionStorage.getItem(schluessel);
      if (art === "loeschen") return sessionStorage.removeItem(schluessel);
      sessionStorage.setItem(schluessel, wert);
    } catch (e) { return null; }
  }

  function zeile(code, mitKnopf) {
    var t = texte[code];
    var p = document.createElement("p");
    p.lang = code;
    p.dir = t.rtl ? "rtl" : "ltr";
    p.textContent = t.text;
    if (mitKnopf) {
      var knopf = document.createElement("button");
      knopf.type = "button";
      knopf.className = "knopf sprach-hinweis-wechseln";
      knopf.textContent = "→ " + t.name;
      knopf.addEventListener("click", function () { wechseln(code); });
      p.appendChild(document.createTextNode(" "));
      p.appendChild(knopf);
    }
    return p;
  }

  function zeigen(codes, sekunden) {
    var feld = hinweis.querySelector(".sprach-hinweis-texte");
    feld.textContent = "";
    codes.forEach(function (code, i) { feld.appendChild(zeile(code, i === 0 && code !== jetzt)); });
    // weiter unten gescrollt: oben am Bildschirm anheften, der Pfeil zeigt nach oben zur Auswahl
    hinweis.classList.toggle("fest", auswahl.getBoundingClientRect().bottom < 0);
    hinweis.hidden = false;
    pfeilAusrichten();
    clearTimeout(timer);
    timer = setTimeout(function () { hinweis.hidden = true; }, sekunden * 1000);
  }

  // Der Pfeil zeigt genau auf die Sprachwahl, wo auch immer sie steht (am Handy z. B. links in
  // der zweiten Zeile der Kopfzeile)
  function pfeilAusrichten() {
    if (hinweis.hidden) return;
    var ziel = auswahl.getBoundingClientRect(), kasten = hinweis.getBoundingClientRect();
    var x = ziel.left + ziel.width / 2 - kasten.left;
    hinweis.style.setProperty("--pfeil-x", Math.max(24, Math.min(kasten.width - 24, x)) + "px");
  }

  function entwurfSichern() {
    if (!formular) return;
    var paare = [];
    new FormData(formular).forEach(function (wert, name) {
      if (typeof wert === "string" && name !== "csrfmiddlewaretoken" && name !== "webseite") {
        paare.push([name, wert]);
      }
    });
    speicher("schreiben", ENTWURF, JSON.stringify(paare));
  }

  function entwurfLaden() {
    var roh = speicher("lesen", ENTWURF);
    speicher("loeschen", ENTWURF);
    if (!roh || !formular) return;
    var werte = {};
    beimLaden = true;
    JSON.parse(roh).forEach(function (paar) { (werte[paar[0]] = werte[paar[0]] || []).push(paar[1]); });
    Array.prototype.forEach.call(formular.elements, function (el) {
      if (!el.name || !(el.name in werte) || el.type === "file") return;
      if (el.type === "checkbox" || el.type === "radio") el.checked = werte[el.name].indexOf(el.value) >= 0;
      else el.value = werte[el.name][0];
      el.dispatchEvent(new Event("change", { bubbles: true }));
    });
    beimLaden = false;
  }

  function wechseln(code) {
    entwurfSichern();
    auswahl.value = code;
    auswahl.form.submit();
  }

  auswahl.addEventListener("change", function () { wechseln(auswahl.value); });
  window.addEventListener("resize", pfeilAusrichten);
  hinweis.querySelector(".sprach-hinweis-zu").addEventListener("click", function () {
    hinweis.hidden = true;
  });
  document.addEventListener("change", function (e) {
    var el = e.target;
    if (beimLaden || !el.matches || !el.matches("select[name$='staatsangehoerigkeit']")) return;
    var option = el.options[el.selectedIndex];
    var code = option && landSprache[option.dataset.land];
    if (code && code !== jetzt && texte[code]) zeigen([code, jetzt], 20);
  });

  entwurfLaden();
  if (!speicher("lesen", GESEHEN)) {
    speicher("schreiben", GESEHEN, "1");
    zeigen([jetzt], 10);
  }
})();
