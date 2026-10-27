// Einstellungen ohne Speichern-Knopf: Formulare mit data-autosave speichern jede Änderung sofort
// (Häkchen, Auswahl und Dateien gleich, Text- und Zahlfelder kurz nach dem Tippen). Das
// Formular geht wie bisher an den Server; die Ansicht bleibt unverändert. Leitet der Server weiter,
// war das Speichern erfolgreich; sonst zeigt die Antwort die Fehler, die hier am Feld erscheinen –
// gespeichert bleibt dann der alte Wert. Ohne JavaScript bleibt der Speichern-Knopf sichtbar.
(function () {
  "use strict";

  function hinweis(feld, text, fehler) {
    var rahmen = feld.closest(".feld") || feld.parentNode;
    var alt = rahmen.querySelector(".autosave-meldung");
    if (alt) alt.remove();
    rahmen.querySelectorAll(".fehler").forEach(function (f) { f.remove(); });
    rahmen.classList.toggle("hat-fehler", !!fehler);
    var meldung = document.createElement("small");
    meldung.className = "autosave-meldung" + (fehler ? " fehler" : " autosave-ok");
    meldung.setAttribute("role", fehler ? "alert" : "status");
    meldung.textContent = text;
    rahmen.appendChild(meldung);
    if (!fehler) {
      setTimeout(function () { meldung.classList.add("autosave-weg"); }, 1500);
      setTimeout(function () { meldung.remove(); }, 2500);
    }
  }

  function fehlerAusAntwort(html, feld) {
    var dok = new DOMParser().parseFromString(html, "text/html");
    var texte = [];
    var gleich = feld.id ? dok.getElementById(feld.id) : null;
    var rahmen = gleich && (gleich.closest(".feld") || gleich.parentNode);
    if (rahmen) {
      rahmen.querySelectorAll(".fehler, .errorlist li").forEach(function (f) {
        texte.push(f.textContent.trim());
      });
    }
    if (!texte.length) {
      // Fehler an einem anderen Feld oder für das ganze Formular
      dok.querySelectorAll("form .fehler, form .errorlist li").forEach(function (f) {
        var t = f.textContent.trim();
        if (t && texte.indexOf(t) < 0) texte.push(t);
      });
    }
    return texte;
  }

  document.querySelectorAll("form[data-autosave]").forEach(function (formular) {
    var knopf = formular.querySelector("[data-autosave-knopf]") ||
      formular.querySelector('button[type="submit"]');
    if (knopf) knopf.hidden = true;
    var kette = Promise.resolve();

    function speichern(feld) {
      var daten = new FormData(formular);
      if (knopf && knopf.name) daten.append(knopf.name, knopf.value);
      var mitDatei = Array.prototype.some.call(formular.querySelectorAll('input[type="file"]'),
        function (d) { return d.files && d.files.length; });
      return fetch(formular.action || window.location.href, {
        method: "POST", body: daten, credentials: "same-origin",
        keepalive: !mitDatei,  // auch wenn man gleich weiterklickt
        headers: { "X-Requested-With": "XMLHttpRequest" },
      }).then(function (antwort) {
        return antwort.text().then(function (html) {
          var fehler = antwort.redirected ? [] : fehlerAusAntwort(html, feld);
          if (!antwort.ok) fehler = fehler.length ? fehler : ["Nicht gespeichert (Fehler " + antwort.status + ")."];
          if (fehler.length) {
            hinweis(feld, fehler.join(" "), true);
          } else {
            hinweis(feld, "✓ gespeichert", false);
            // Teile der Seite, die von den Einstellungen abhängen, aus der neuen Seite übernehmen
            var neu = new DOMParser().parseFromString(html, "text/html");
            document.querySelectorAll("[data-autosave-aktualisieren][id]").forEach(function (alt) {
              var ersatz = neu.getElementById(alt.id);
              if (ersatz) alt.innerHTML = ersatz.innerHTML;
            });
            if (feld.type === "file") feld.value = "";  // nicht beim nächsten Mal erneut hochladen
          }
        });
      }).catch(function () {
        hinweis(feld, "Nicht gespeichert – keine Verbindung. Bitte erneut versuchen.", true);
      });
    }

    var zeit = null, offen = null;
    function einreihen(feld) {
      clearTimeout(zeit);
      offen = null;
      kette = kette.then(function () { return speichern(feld); });
    }
    function tippfeld(feld) {
      return feld.tagName === "TEXTAREA" ||
        ["text", "number", "email", "url", "tel", "password", "search"].indexOf(feld.type) >= 0;
    }
    formular.addEventListener("input", function (ereignis) {
      var feld = ereignis.target;
      if (!feld.name || !tippfeld(feld) || feld.closest("[data-nicht-autosave]")) return;
      clearTimeout(zeit);
      offen = feld;
      zeit = setTimeout(function () { einreihen(feld); }, 1200);
    });
    formular.addEventListener("change", function (ereignis) {
      var feld = ereignis.target;
      if (!feld.name || feld.closest("[data-nicht-autosave]")) return;
      if (tippfeld(feld) && offen !== feld) return;  // schon gespeichert, nichts mehr offen
      einreihen(feld);
    });
    // Enter in einem Textfeld speichert ebenfalls, ohne die Seite zu verlassen
    formular.addEventListener("submit", function (ereignis) {
      ereignis.preventDefault();
      var feld = document.activeElement && formular.contains(document.activeElement)
        ? document.activeElement : formular.querySelector("[name]");
      einreihen(feld);
    });
    // Noch nicht gespeicherte Eingabe beim Verlassen der Seite mitnehmen
    window.addEventListener("pagehide", function () { if (offen) einreihen(offen); });
  });
})();
