// Unterschreiben mit dem Finger, dem Stift oder der Maus: Ein <canvas data-unterschrift="feld-id">
// zeichnet die Striche und legt das Bild als PNG (data:image/png;base64,…) in das versteckte Feld
// mit dieser id. Ein Knopf mit data-unterschrift-leeren leert das Feld wieder. Der Server prüft
// das Bild; ohne Strich bleibt das Feld leer und das Formular meldet es.
(function () {
  "use strict";

  var MAX_BREITE = 1600;  // Pixel des Bildes

  function einrichten(flaeche) {
    var feld = document.getElementById(flaeche.dataset.unterschrift);
    if (!feld) return;
    var stift = flaeche.getContext("2d");
    var zeichnet = false, gezeichnet = false;

    function anpassen() {
      // interne Größe an die angezeigte anpassen (scharfe Linien); vorhandene Striche gehen
      // dabei verloren, deshalb nur solange noch nichts gezeichnet ist
      if (gezeichnet) return;
      var kasten = flaeche.getBoundingClientRect();
      var dichte = Math.min(window.devicePixelRatio || 1, 2);
      // auf großen Bildschirmen nicht breiter als nötig: sonst wird das Bild unnötig groß
      if (kasten.width * dichte > MAX_BREITE) dichte = MAX_BREITE / kasten.width;
      flaeche.width = Math.round(kasten.width * dichte);
      flaeche.height = Math.round(kasten.height * dichte);
      stift.setTransform(dichte, 0, 0, dichte, 0, 0);
      stift.lineWidth = 2.2;
      stift.lineCap = "round";
      stift.lineJoin = "round";
      stift.strokeStyle = "#111";
    }

    function ort(e) {
      var kasten = flaeche.getBoundingClientRect();
      return [e.clientX - kasten.left, e.clientY - kasten.top];
    }

    flaeche.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      zeichnet = true;
      flaeche.setPointerCapture(e.pointerId);
      var p = ort(e);
      stift.beginPath();
      stift.moveTo(p[0], p[1]);
      stift.lineTo(p[0] + 0.1, p[1] + 0.1);  // ein Punkt bleibt sichtbar
      stift.stroke();
      gezeichnet = true;
    });
    flaeche.addEventListener("pointermove", function (e) {
      if (!zeichnet) return;
      e.preventDefault();
      var p = ort(e);
      stift.lineTo(p[0], p[1]);
      stift.stroke();
    });
    function fertig() {
      if (!zeichnet) return;
      zeichnet = false;
      feld.value = flaeche.toDataURL("image/png");
      flaeche.classList.add("unterschrift-da");
    }
    flaeche.addEventListener("pointerup", fertig);
    flaeche.addEventListener("pointercancel", fertig);

    document.querySelectorAll("[data-unterschrift-leeren='" + feld.id + "']").forEach(function (k) {
      k.addEventListener("click", function () {
        gezeichnet = false;
        feld.value = "";
        flaeche.classList.remove("unterschrift-da");
        anpassen();
      });
    });
    window.addEventListener("resize", anpassen);
    anpassen();
  }

  document.querySelectorAll("canvas[data-unterschrift]").forEach(einrichten);
})();
