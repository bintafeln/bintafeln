// Ablage für Nachweise im Antragsformular: Dateien hineinziehen, auswählen oder mit dem Handy
// fotografieren. Alle landen im gewöhnlichen Dateifeld (DataTransfer), das Formular schickt sie
// wie bisher. Ohne JavaScript bleibt das Dateifeld sichtbar und funktioniert allein.
(function () {
  "use strict";

  var TYPEN = ["image/jpeg", "image/png", "application/pdf"];

  function einrichten(rahmen) {
    var feld = rahmen.querySelector("input[type=file]");
    if (!feld || typeof DataTransfer === "undefined") return;
    var max = parseInt(rahmen.dataset.max, 10) || 5;
    var gewaehlt = [];

    function element(name, klasse, text) {
      var e = document.createElement(name);
      if (klasse) e.className = klasse;
      if (text) e.textContent = text;
      return e;
    }

    var flaeche = element("div", "ablage");
    flaeche.appendChild(element("p", "ablage-text", rahmen.dataset.textZiehen));
    var knoepfe = element("div", "ablage-knoepfe");
    var waehlen = element("button", "knopf knopf-zweitrangig", rahmen.dataset.textWaehlen);
    var foto = element("button", "knopf knopf-zweitrangig", rahmen.dataset.textFoto);
    waehlen.type = foto.type = "button";
    knoepfe.appendChild(waehlen);
    knoepfe.appendChild(foto);
    flaeche.appendChild(knoepfe);
    var liste = element("ul", "ablage-liste");
    var meldung = element("p", "fehler ablage-fehler");
    meldung.hidden = true;
    meldung.setAttribute("role", "alert");

    // Kamera: eigenes Feld ohne Namen, die Aufnahme wandert in das eigentliche Feld
    var kamera = document.createElement("input");
    kamera.type = "file";
    kamera.accept = "image/*";
    kamera.setAttribute("capture", "environment");
    kamera.hidden = true;

    feld.classList.add("ablage-feld");
    feld.parentNode.insertBefore(flaeche, feld);
    flaeche.after(liste);
    liste.after(meldung);
    rahmen.appendChild(kamera);

    function zeigen() {
      var dt = new DataTransfer();
      gewaehlt.forEach(function (d) { dt.items.add(d); });
      feld.files = dt.files;
      liste.innerHTML = "";
      gewaehlt.forEach(function (d, nr) {
        var li = element("li", "", d.name + " (" + Math.max(1, Math.round(d.size / 1024)) + " KB) ");
        var weg = element("button", "ablage-entfernen", "✕");
        weg.type = "button";
        weg.title = weg.ariaLabel = rahmen.dataset.textEntfernen;
        weg.addEventListener("click", function () { gewaehlt.splice(nr, 1); zeigen(); });
        li.appendChild(weg);
        liste.appendChild(li);
      });
    }

    function hinzu(dateien) {
      var fehler = "";
      Array.prototype.forEach.call(dateien, function (d) {
        if (TYPEN.indexOf(d.type) < 0) { fehler = rahmen.dataset.textTyp; return; }
        if (gewaehlt.length >= max) {
          fehler = rahmen.dataset.textAnzahl.replace("{anzahl}", max);
          return;
        }
        gewaehlt.push(d);
      });
      meldung.textContent = fehler;
      meldung.hidden = !fehler;
      zeigen();
    }

    waehlen.addEventListener("click", function () { feld.click(); });
    foto.addEventListener("click", function () { kamera.click(); });
    // Das Dateifeld ersetzt sonst die Auswahl; hier wird ergänzt
    feld.addEventListener("change", function () {
      var neu = Array.prototype.slice.call(feld.files);
      if (neu.length && neu.every(function (d) { return gewaehlt.indexOf(d) < 0; })) hinzu(neu);
    });
    kamera.addEventListener("change", function () { hinzu(kamera.files); kamera.value = ""; });
    ["dragenter", "dragover"].forEach(function (art) {
      flaeche.addEventListener(art, function (e) { e.preventDefault(); flaeche.classList.add("ablage-ueber"); });
    });
    ["dragleave", "drop"].forEach(function (art) {
      flaeche.addEventListener(art, function () { flaeche.classList.remove("ablage-ueber"); });
    });
    flaeche.addEventListener("drop", function (e) {
      e.preventDefault();
      if (e.dataTransfer && e.dataTransfer.files) hinzu(e.dataTransfer.files);
    });
  }

  document.querySelectorAll("[data-ablage]").forEach(einrichten);
})();
