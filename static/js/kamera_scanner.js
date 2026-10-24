// Kamera als Barcode-Scanner für Eingabefelder mit data-kamera (z. B. Kundennummer am Einlass).
//
// Der Knopf „Kamera“ erscheint nur, wenn der Browser eine Kamera anbietet. Erkannt wird mit dem
// eingebauten BarcodeDetector (Android/Chrome); fehlt er (z. B. iPhone), lädt das Skript die
// mitgelieferte Bibliothek unter static/vendor/barcode-detector (ohne Zugriff auf fremde Server).
// Der gelesene Wert landet im Feld und das Formular wird abgeschickt. Tippen und Handscanner
// (arbeiten als Tastatur) gehen immer weiter.
(function () {
  "use strict";

  var FORMATE = ["code_128", "code_39", "ean_13", "ean_8", "itf", "qr_code"];
  var detektorVersprechen = null;

  function skriptLaden(url) {
    return new Promise(function (ok, fehler) {
      var s = document.createElement("script");
      s.src = url;
      s.onload = ok;
      s.onerror = function () { fehler(new Error("Skript nicht geladen")); };
      document.head.appendChild(s);
    });
  }

  function detektor(feld) {
    if (detektorVersprechen) return detektorVersprechen;
    detektorVersprechen = (async function () {
      if ("BarcodeDetector" in window) {
        try {
          var vorhanden = await window.BarcodeDetector.getSupportedFormats();
          var formate = FORMATE.filter(function (f) { return vorhanden.indexOf(f) >= 0; });
          if (formate.indexOf("code_128") >= 0) return new window.BarcodeDetector({ formats: formate });
        } catch (e) { /* weiter mit der Bibliothek */ }
      }
      await skriptLaden(feld.dataset.kameraSkript);
      var api = window.BarcodeDetectionAPI;
      var wasm = feld.dataset.kameraWasm;
      api.setZXingModuleOverrides({
        locateFile: function (pfad, prefix) { return pfad.endsWith(".wasm") ? wasm : prefix + pfad; },
      });
      return new api.BarcodeDetector({ formats: FORMATE });
    })();
    detektorVersprechen.catch(function () { detektorVersprechen = null; });
    return detektorVersprechen;
  }

  function einrichten(feld) {
    var knopf = document.getElementById(feld.dataset.kamera);
    var dialog = document.getElementById(feld.dataset.kamera + "-dialog");
    if (!knopf || !dialog) return;
    var video = dialog.querySelector("video");
    var meldung = dialog.querySelector(".kamera-meldung");
    var strom = null;
    var laeuft = false;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      if (window.isSecureContext) return;  // Gerät ohne Kamera: Knopf bleibt verborgen
    }
    knopf.hidden = false;

    function zeigen(text) {
      meldung.textContent = text;
      meldung.hidden = !text;
    }

    function stoppen() {
      laeuft = false;
      if (strom) strom.getTracks().forEach(function (t) { t.stop(); });
      strom = null;
      video.srcObject = null;
    }

    function schliessen() {
      stoppen();
      if (dialog.open) dialog.close();
      feld.focus();
    }

    async function lesen(d) {
      while (laeuft) {
        if (video.readyState >= 2) {
          try {
            var codes = await d.detect(video);
            var wert = codes.length ? (codes[0].rawValue || "").trim() : "";
            if (wert && laeuft) {
              if (navigator.vibrate) navigator.vibrate(80);
              schliessen();
              feld.value = wert;
              feld.form.requestSubmit();
              return;
            }
          } catch (e) { /* einzelnes Bild nicht lesbar */ }
        }
        await new Promise(function (ok) { setTimeout(ok, 150); });
      }
    }

    knopf.addEventListener("click", async function () {
      zeigen("");
      dialog.showModal();
      if (!window.isSecureContext || !navigator.mediaDevices) {
        zeigen("Die Kamera kann der Browser nur über eine sichere Verbindung (https) nutzen. " +
               "Bitte die Kundennummer eingeben oder einen Handscanner verwenden.");
        return;
      }
      try {
        strom = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } },
          audio: false,
        });
      } catch (e) {
        zeigen(e && e.name === "NotAllowedError"
          ? "Der Zugriff auf die Kamera wurde nicht erlaubt. Er lässt sich in den Einstellungen des Browsers freigeben."
          : "Es wurde keine Kamera gefunden.");
        return;
      }
      video.srcObject = strom;
      await video.play().catch(function () {});
      laeuft = true;
      try {
        lesen(await detektor(feld));
      } catch (e) {
        stoppen();
        zeigen("Der Barcode-Leser konnte nicht geladen werden. Bitte die Kundennummer eingeben.");
      }
    });

    dialog.addEventListener("close", stoppen);
    dialog.querySelector(".kamera-schliessen").addEventListener("click", schliessen);
  }

  document.querySelectorAll("input[data-kamera]").forEach(einrichten);
})();
