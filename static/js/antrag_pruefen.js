// Antragsformular: Pflichtangaben vor dem Absenden prüfen, damit niemand glaubt, der Antrag sei
// abgeschickt, obwohl etwas fehlt. Der Absende-Knopf bleibt sichtbar „gesperrt“, solange
// Pflichtangaben (Felder mit data-pflicht) fehlen; darunter steht, wie viele noch offen sind. Ein
// Klick darauf schickt nichts ab, sondern markiert alle fehlenden Felder rot, zeigt über dem Knopf
// einen Kasten mit allem, was fehlt (mit Sprung zum Feld), und springt zum ersten. Ohne JavaScript
// prüft der Server wie bisher; kommt das Formular mit Fehlern zurück, springt die Seite zum
// großen Fehlerkasten oben.
(function () {
  "use strict";
  var form = document.querySelector("form[data-antrag-pruefen]");
  if (!form) return;
  form.noValidate = true; // eigene, deutliche Anzeige statt der kleinen Browser-Blasen
  var knopf = form.querySelector(".antrag-absenden");
  var kasten = document.getElementById("antrag-pruefung");
  var offen = form.querySelector(".antrag-noch-offen");
  var textPflicht = form.dataset.textPflicht || "";
  var textOffen = form.dataset.textOffen || "";
  var textHaken = form.dataset.textHaken || textPflicht;

  function sichtbar(einheit) {
    // Zugeklappte Personen zählen mit, ausgeblendete Felder (z. B. per Auswahl) nicht
    return einheit.getClientRects().length > 0 || !!einheit.closest("details");
  }

  function eingaben(einheit) {
    return Array.prototype.slice.call(
      einheit.querySelectorAll("input:not([type=hidden]), select, textarea"));
  }

  function fehlt(einheit) {
    var felder = eingaben(einheit);
    if (!felder.length) return false;
    var wahl = felder.filter(function (f) { return f.type === "checkbox" || f.type === "radio"; });
    if (wahl.length) return !wahl.some(function (f) { return f.checked; });
    var datei = felder.filter(function (f) { return f.type === "file"; });
    if (datei.length) return !datei.some(function (f) { return f.files && f.files.length; });
    return felder.every(function (f) { return !String(f.value || "").trim(); });
  }

  function falsch(einheit) {
    return eingaben(einheit).some(function (f) { return f.value && !f.checkValidity(); });
  }

  function bezeichnung(einheit) {
    var label = einheit.querySelector("label");
    var text = (label ? label.textContent : "").replace(/\*/g, "").replace(/\s+/g, " ").trim();
    return text.length > 80 ? text.slice(0, 77) + "…" : text;
  }

  // Alle Einheiten, die jetzt nicht stimmen: Pflichtfelder ohne Angabe, Angaben im falschen Format
  // und weitere Personen mit Geburtsdatum, aber ohne Vornamen (wie die Prüfung im Server).
  function probleme() {
    var liste = [];
    form.querySelectorAll(".feld").forEach(function (einheit) {
      if (!sichtbar(einheit)) return;
      if ((einheit.hasAttribute("data-pflicht") && fehlt(einheit)) || falsch(einheit)) {
        liste.push(einheit);
      }
    });
    form.querySelectorAll("input[name$='_geburtsdatum']").forEach(function (geb) {
      var n = /^p(\d+)_geburtsdatum$/.exec(geb.name);
      var vorname = n && form.querySelector("[name='p" + n[1] + "_vorname']");
      var einheit = vorname && vorname.closest(".feld");
      if (geb.value.trim() && vorname && !vorname.value.trim() && liste.indexOf(einheit) < 0) {
        liste.push(einheit);
      }
    });
    return liste;
  }

  function markieren(einheit) {
    einheit.classList.add("hat-fehler");
    if (!einheit.querySelector(".fehler")) {
      var hinweis = document.createElement("small");
      hinweis.className = "fehler";
      hinweis.setAttribute("data-geprueft", "");
      hinweis.textContent = einheit.classList.contains("feld-haken") ? textHaken : textPflicht;
      einheit.appendChild(hinweis);
    }
  }

  function aufheben(einheit) {
    einheit.classList.remove("hat-fehler");
    einheit.querySelectorAll(".fehler").forEach(function (f) { f.remove(); });
  }

  function anker(einheit) {
    var feld = eingaben(einheit)[0];
    if (feld && !feld.id) feld.id = "antrag-feld-" + Math.random().toString(36).slice(2);
    return feld;
  }

  function knopfStand(liste) {
    if (!knopf) return;
    var gesperrt = liste.length > 0;
    knopf.classList.toggle("knopf-gesperrt", gesperrt);
    knopf.setAttribute("aria-disabled", gesperrt ? "true" : "false");
    if (offen) {
      offen.hidden = !gesperrt;
      offen.textContent = gesperrt ? textOffen.replace("{anzahl}", liste.length) : "";
    }
  }

  function kastenFuellen(liste) {
    if (!kasten) return;
    var ul = kasten.querySelector("ul");
    ul.textContent = "";
    liste.forEach(function (einheit) {
      var feld = anker(einheit);
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = "#" + (feld ? feld.id : "");
      a.textContent = bezeichnung(einheit);
      a.addEventListener("click", function (e) {
        if (!feld) return;
        e.preventDefault();
        var zu = feld.closest("details");
        if (zu) zu.open = true;
        feld.scrollIntoView({ block: "center" });
        feld.focus({ preventScroll: true });
      });
      li.appendChild(a);
      ul.appendChild(li);
    });
    kasten.hidden = liste.length === 0;
  }

  function aktualisieren() {
    var liste = probleme();
    // Was inzwischen stimmt, verliert die rote Markierung sofort
    form.querySelectorAll(".feld.hat-fehler").forEach(function (einheit) {
      if (liste.indexOf(einheit) < 0) aufheben(einheit);
    });
    knopfStand(liste);
    if (kasten && !kasten.hidden) kastenFuellen(liste);
    return liste;
  }

  form.addEventListener("input", aktualisieren);
  form.addEventListener("change", aktualisieren);

  form.addEventListener("submit", function (e) {
    var liste = aktualisieren();
    if (!liste.length) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    liste.forEach(markieren);
    kastenFuellen(liste);
    var erstes = liste[0];
    var zu = erstes.closest("details");
    if (zu) zu.open = true;
    var feld = anker(erstes);
    erstes.scrollIntoView({ block: "center", behavior: "smooth" });
    if (feld) feld.focus({ preventScroll: true });
  });

  knopfStand(probleme());

  // Vom Server mit Fehlern zurück: zum großen Kasten oben springen
  var serverKasten = document.getElementById("antrag-fehler");
  if (serverKasten) {
    serverKasten.scrollIntoView({ block: "start" });
    serverKasten.focus({ preventScroll: true });
  }
})();
