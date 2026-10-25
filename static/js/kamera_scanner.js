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

  // Fragt ohne Abfrage nach, ob die Kamera schon erlaubt oder gesperrt ist ("granted",
  // "denied", "prompt"); manche Browser (z. B. Firefox, ältere Safari) kennen das nicht.
  async function berechtigung() {
    try {
      if (navigator.permissions && navigator.permissions.query) {
        return (await navigator.permissions.query({ name: "camera" })).state;
      }
    } catch (e) { /* unbekannt */ }
    return "prompt";
  }

  // Erst die Rückkamera in guter Auflösung; kennt das Gerät das nicht, irgendeine Kamera.
  async function kameraOeffnen() {
    try {
      return await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } },
        audio: false,
      });
    } catch (e) {
      if (e && (e.name === "OverconstrainedError" || e.name === "NotFoundError")) {
        return await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      }
      throw e;
    }
  }

  // Schritte zum Freigeben, passend zum Gerät
  function anleitung(kopf) {
    var ua = navigator.userAgent || "";
    var schritte;
    if (/iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) {
      schritte = [
        "In Safari links in der Adressleiste auf „aA“ (oder das Symbol mit den Reglern) tippen.",
        "„Website-Einstellungen“ wählen und bei „Kamera“ „Erlauben“ oder „Fragen“ einstellen.",
        "Klappt das nicht: iPhone-Einstellungen → Apps → Safari → Kamera → „Erlauben“.",
        "Zurück in bintafeln „Erneut versuchen“ antippen.",
      ];
    } else if (/Android/.test(ua)) {
      schritte = [
        "Links neben der Adresse auf das Schloss- oder Regler-Symbol tippen.",
        "„Berechtigungen“ (bzw. „Website-Einstellungen“) öffnen und „Kamera“ auf „Zulassen“ stellen.",
        "Fehlt dort die Kamera: Android-Einstellungen → Apps → Chrome (bzw. Ihr Browser) → " +
          "Berechtigungen → Kamera → „Zulassen“.",
        "Zurück in bintafeln „Erneut versuchen“ antippen (ggf. die Seite neu laden).",
      ];
    } else {
      schritte = [
        "Links in der Adressleiste auf das Schloss- oder Kamera-Symbol klicken.",
        "Bei „Kamera“ „Zulassen“ wählen.",
        "„Erneut versuchen“ klicken (ggf. die Seite neu laden).",
      ];
    }
    return [kopf].concat(schritte);
  }

  function einrichten(feld) {
    var knopf = document.getElementById(feld.dataset.kamera);
    var dialog = document.getElementById(feld.dataset.kamera + "-dialog");
    if (!knopf || !dialog || feld.dataset.kameraBereit) return;
    feld.dataset.kameraBereit = "1";
    var video = dialog.querySelector("video");
    var meldung = dialog.querySelector(".kamera-meldung");
    var hinweis = dialog.querySelector(".kamera-hilfe");
    var HINWEIS = hinweis.textContent;
    var strom = null;
    var laeuft = false;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      if (window.isSecureContext) return;  // Gerät ohne Kamera: Knopf bleibt verborgen
    }
    knopf.hidden = false;

    var nochmal = dialog.querySelector(".kamera-nochmal");

    // text: ein Satz oder eine Liste von Zeilen; Zeilen ab der zweiten werden nummerierte Schritte
    function zeigen(text, mitNochmal) {
      meldung.textContent = "";
      var zeilen = Array.isArray(text) ? text : (text ? [text] : []);
      if (zeilen.length) {
        var kopf = document.createElement("p");
        kopf.textContent = zeilen[0];
        meldung.appendChild(kopf);
      }
      if (zeilen.length > 1) {
        var liste = document.createElement("ol");
        zeilen.slice(1).forEach(function (z) {
          var li = document.createElement("li");
          li.textContent = z;
          liste.appendChild(li);
        });
        meldung.appendChild(liste);
      }
      meldung.hidden = !zeilen.length;
      if (nochmal) nochmal.hidden = !mitNochmal;
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

    async function starten() {
      stoppen();
      zeigen("");
      if (!window.isSecureContext || !navigator.mediaDevices) {
        if (feld.dataset.kameraHttps) {
          // Die Tafel bietet im Heimnetz auch https an (ADR 0041): dorthin wechseln
          zeigen(["Die Kamera gibt der Browser nur über https frei. Diese Tafel ist auch über https " +
                  "erreichbar:",
                  "Unten „Über https öffnen“ antippen.",
                  "Beim ersten Mal warnt der Browser vor dem Zertifikat: „Erweitert“ bzw. „Details“ " +
                    "und dann „Weiter zu …“ wählen. Das Zertifikat stellt der eigene Server aus.",
                  "Dort erneut anmelden und „Kamera“ antippen; der Browser fragt dann nach der Freigabe."]);
          var link = document.createElement("a");
          link.href = feld.dataset.kameraHttps;
          link.className = "knopf kamera-https";
          link.textContent = "Über https öffnen";
          meldung.appendChild(link);
          return;
        }
        zeigen(["Die Kamera gibt der Browser nur über eine sichere Verbindung frei (Adresse beginnt " +
                "mit „https“). Diese Seite ist über http geöffnet, deshalb fragt der Browser gar " +
                "nicht erst nach der Kamera.",
                "Bitte die Kundennummer eintippen oder einen Handscanner verwenden.",
                "Admin, im Produktivbetrieb: bintafeln mit eigener Adresse (BINTAFELN_DOMAIN) " +
                  "betreiben, dann ist https automatisch an.",
                "Admin, zum Testen im Heimnetz: in der Datei .env BINTAFELN_HEIMNETZ_ADRESSE auf " +
                  "die IP des Servers setzen und neu starten; dann geht auch https mit der IP-Adresse."]);
        return;
      }
      var status = await berechtigung();
      if (status === "denied") {
        zeigen(anleitung("Die Kamera ist für diese Seite gesperrt. So geben Sie sie frei:"), true);
        return;
      }
      if (status !== "granted") {
        hinweis.textContent = "Gleich fragt der Browser, ob diese Seite die Kamera nutzen darf. " +
          "Bitte „Zulassen“ bzw. „Erlauben“ antippen.";
      }
      try {
        strom = await kameraOeffnen();
      } catch (e) {
        hinweis.textContent = HINWEIS;
        var name = e && e.name;
        if (name === "NotAllowedError" || name === "SecurityError") {
          zeigen(anleitung("Der Zugriff auf die Kamera wurde nicht erlaubt. So geben Sie ihn frei:"), true);
        } else if (name === "NotReadableError" || name === "AbortError") {
          zeigen(["Die Kamera wird gerade von einer anderen App benutzt.",
                  "Andere Apps mit Kamera (z. B. Videoanruf, Kamera-App) schließen.",
                  "Dann „Erneut versuchen“ antippen."], true);
        } else {
          zeigen("Es wurde keine Kamera gefunden. Bitte die Kundennummer eintippen.", true);
        }
        return;
      }
      hinweis.textContent = HINWEIS;
      video.srcObject = strom;
      await video.play().catch(function () {});
      laeuft = true;
      try {
        lesen(await detektor(feld));
      } catch (e) {
        stoppen();
        zeigen("Der Barcode-Leser konnte nicht geladen werden. Bitte die Kundennummer eingeben.");
      }
    }

    knopf.addEventListener("click", function () {
      dialog.showModal();
      starten();
    });
    if (nochmal) nochmal.addEventListener("click", starten);

    dialog.addEventListener("close", stoppen);
    dialog.querySelector(".kamera-schliessen").addEventListener("click", schliessen);
  }

  function alleEinrichten() {
    document.querySelectorAll("input[data-kamera]").forEach(einrichten);
  }
  alleEinrichten();
  // Der Einlass tauscht das Suchfeld per HTMX aus (nach dem Anmelden zurück zur Suche)
  document.addEventListener("htmx:afterSettle", alleEinrichten);
})();
