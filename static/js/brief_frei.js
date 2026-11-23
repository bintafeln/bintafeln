// Grafiken frei auf der Seite einer Serienbrief-Vorlage (ADR 0166), z. B. Unterschriften.
// Pflegt das versteckte Feld mit der Liste [{grafik, x, y, breite, seite}] (Millimeter ab der
// linken oberen Ecke der A4-Seite). Bedienung auf zwei Wegen: in der Live-Vorschau ziehen (und an
// der Ecke unten rechts die Größe ändern, Pfeiltasten verschieben um 1 mm, mit Umschalt um 5 mm)
// oder in der Tabelle die Maße eintragen – Letzteres geht auch am Handy ohne Vorschau. Jede
// Änderung löst am versteckten Feld „change“ aus; autosave.js speichert dann wie gewohnt.
(function () {
  "use strict";

  var box = document.querySelector("[data-brief-frei]");
  if (!box) return;
  var feld = document.getElementById(box.dataset.feld);
  if (!feld) return;
  var adresse = box.dataset.briefFrei;
  var token = feld.form && feld.form.querySelector("[name=csrfmiddlewaretoken]");
  var ebene = document.querySelector("[data-brief-frei-ebene]");
  var rahmen = box.querySelector(".frei-tabelle"), tbody = rahmen.querySelector("tbody");
  var wahl = box.querySelector("#frei-wahl"), setzen = box.querySelector("[data-frei-setzen]");
  var datei = box.querySelector("[data-frei-datei]");
  var freistellen = box.querySelector("[data-frei-freistellen]");
  var fehler = box.querySelector("[data-frei-fehler]");
  var SEITE_B = 210, SEITE_H = 297, MIN = 5;
  var grafiken = {};
  var eintraege = [];
  try { eintraege = JSON.parse(feld.value || "[]"); } catch (e) { eintraege = []; }
  if (!Array.isArray(eintraege)) eintraege = [];

  function melden(text) { fehler.textContent = text || ""; fehler.hidden = !text; }
  function runden(z) { return Math.round(z * 10) / 10; }
  function begrenzen(z, unten, oben) { return runden(Math.min(Math.max(z, unten), oben)); }
  function hoehe(e) {
    var g = grafiken[e.grafik];
    return g && g.breite ? e.breite * g.hoehe / g.breite : e.breite / 3;
  }

  function merken() {
    feld.value = JSON.stringify(eintraege);
    feld.dispatchEvent(new Event("change", {bubbles: true}));
  }

  // --- Tabelle mit den Maßen ---------------------------------------------------------------
  function zahlfeld(e, schluessel, titel, oben) {
    var td = document.createElement("td");
    td.dataset.titel = titel;
    var f = document.createElement("input");
    f.type = "number";
    f.step = "0.5";
    f.min = schluessel === "breite" ? MIN : 0;
    f.max = oben;
    f.value = e[schluessel];
    f.setAttribute("aria-label", titel);
    f.addEventListener("change", function () {
      var z = parseFloat(String(f.value).replace(",", "."));
      if (isNaN(z)) { f.value = e[schluessel]; return; }
      e[schluessel] = begrenzen(z, schluessel === "breite" ? MIN : 0, oben);
      f.value = e[schluessel];
      zeichnen();
      merken();
    });
    td.appendChild(f);
    return td;
  }

  function tabelle() {
    tbody.textContent = "";
    rahmen.hidden = !eintraege.length;
    eintraege.forEach(function (e, i) {
      var g = grafiken[e.grafik];
      var tr = document.createElement("tr");
      var name = document.createElement("td");
      name.dataset.titel = "Grafik";
      name.textContent = g ? g.name : "…";
      tr.appendChild(name);
      var td = document.createElement("td");
      td.dataset.titel = "Seite";
      var s = document.createElement("select");
      s.setAttribute("aria-label", "Seite");
      [["erste", "erste Seite"], ["letzte", "letzte Seite"]].forEach(function (o) {
        var opt = document.createElement("option");
        opt.value = o[0];
        opt.textContent = o[1];
        opt.selected = e.seite === o[0];
        s.appendChild(opt);
      });
      s.addEventListener("change", function () { e.seite = s.value; merken(); });
      td.appendChild(s);
      tr.appendChild(td);
      tr.appendChild(zahlfeld(e, "x", "Links (mm)", SEITE_B - MIN));
      tr.appendChild(zahlfeld(e, "y", "Oben (mm)", SEITE_H - MIN));
      tr.appendChild(zahlfeld(e, "breite", "Breite (mm)", SEITE_B));
      var weg = document.createElement("td");
      var k = document.createElement("button");
      k.type = "button";
      k.className = "knopf knopf-zweitrangig";
      k.textContent = "Entfernen";
      k.title = "Von der Seite nehmen (die Grafik selbst bleibt erhalten)";
      k.addEventListener("click", function () {
        eintraege.splice(i, 1);
        zeichnen();
        merken();
      });
      weg.appendChild(k);
      tr.appendChild(weg);
      tbody.appendChild(tr);
    });
  }

  // --- Verschiebbare Grafiken über der Vorschau ---------------------------------------------
  function stellen(stueck, e) {
    stueck.style.left = (e.x / SEITE_B * 100) + "%";
    stueck.style.top = (e.y / SEITE_H * 100) + "%";
    stueck.style.width = (e.breite / SEITE_B * 100) + "%";
  }

  function bewegen(stueck, e) {
    var start = null;
    stueck.addEventListener("pointerdown", function (ev) {
      ev.preventDefault();
      stueck.setPointerCapture(ev.pointerId);
      stueck.focus();
      start = {x: ev.clientX, y: ev.clientY, ex: e.x, ey: e.y, eb: e.breite,
        groesse: ev.target.classList.contains("frei-griff")};
      stueck.classList.add("frei-aktiv");
    });
    stueck.addEventListener("pointermove", function (ev) {
      if (!start) return;
      var r = ebene.getBoundingClientRect();
      var dx = (ev.clientX - start.x) / r.width * SEITE_B;
      var dy = (ev.clientY - start.y) / r.height * SEITE_H;
      if (start.groesse) {
        e.breite = begrenzen(start.eb + dx, MIN, SEITE_B - e.x);
      } else {
        e.x = begrenzen(start.ex + dx, 0, SEITE_B - Math.min(e.breite, SEITE_B - MIN));
        e.y = begrenzen(start.ey + dy, 0, SEITE_H - Math.min(hoehe(e), SEITE_H - MIN));
      }
      stellen(stueck, e);
    });
    function ende() {
      if (!start) return;
      var geaendert = e.x !== start.ex || e.y !== start.ey || e.breite !== start.eb;
      start = null;
      stueck.classList.remove("frei-aktiv");
      if (geaendert) { tabelle(); merken(); }
    }
    stueck.addEventListener("pointerup", ende);
    stueck.addEventListener("pointercancel", ende);
    stueck.addEventListener("keydown", function (ev) {
      var schritt = ev.shiftKey ? 5 : 1;
      var d = {ArrowLeft: [-schritt, 0], ArrowRight: [schritt, 0],
        ArrowUp: [0, -schritt], ArrowDown: [0, schritt]}[ev.key];
      if (!d) return;
      ev.preventDefault();
      e.x = begrenzen(e.x + d[0], 0, SEITE_B - MIN);
      e.y = begrenzen(e.y + d[1], 0, SEITE_H - MIN);
      stellen(stueck, e);
      tabelle();
      merken();
    });
  }

  function vorschau() {
    if (!ebene) return;
    ebene.textContent = "";
    eintraege.forEach(function (e) {
      var g = grafiken[e.grafik];
      if (!g) return;
      var stueck = document.createElement("div");
      stueck.className = "frei-stueck";
      stueck.tabIndex = 0;
      stueck.title = g.name + " – ziehen zum Verschieben, Ecke unten rechts für die Größe";
      stueck.setAttribute("aria-label", g.name + " verschieben (Pfeiltasten)");
      var bild = document.createElement("img");
      bild.src = g.adresse;
      bild.alt = "";
      bild.draggable = false;
      stueck.appendChild(bild);
      var griff = document.createElement("span");
      griff.className = "frei-griff";
      griff.setAttribute("aria-hidden", "true");
      stueck.appendChild(griff);
      stellen(stueck, e);
      bewegen(stueck, e);
      ebene.appendChild(stueck);
    });
  }

  function zeichnen() { tabelle(); vorschau(); }

  // --- Grafiken laden, setzen, hochladen ------------------------------------------------------
  function aufnehmen(g) {
    grafiken[g.id] = g;
    if (wahl.querySelector('option[value="' + g.id + '"]')) return;
    var opt = document.createElement("option");
    opt.value = g.id;
    opt.textContent = g.name;
    wahl.appendChild(opt);
  }

  function setzenAuf(id) {
    var g = grafiken[id];
    if (!g) return;
    var breite = 45;
    var naechste = eintraege.length;
    eintraege.push({grafik: g.id, x: begrenzen(25 + (naechste % 3) * 55, 0, SEITE_B - breite),
      y: begrenzen(200 + Math.floor(naechste / 3) * 25, 0, SEITE_H - MIN), breite: breite, seite: "letzte"});
    zeichnen();
    merken();
  }

  setzen.addEventListener("click", function () {
    melden("");
    if (!wahl.value) return melden("Bitte erst eine Grafik wählen.");
    setzenAuf(parseInt(wahl.value, 10));
    wahl.value = "";
  });

  datei.addEventListener("change", function () {
    if (!datei.files.length) return;
    var daten = new FormData();
    daten.append("datei", datei.files[0]);
    if (freistellen.checked) daten.append("freistellen", "1");
    if (token) daten.append("csrfmiddlewaretoken", token.value);
    melden("");
    box.classList.add("laedt");
    fetch(adresse, {method: "POST", body: daten, credentials: "same-origin"})
      .then(function (a) { return a.json().then(function (d) { return {ok: a.ok, d: d}; }); })
      .then(function (x) {
        datei.value = "";
        if (!x.ok) return melden(x.d.fehler || "Hochladen ging nicht.");
        aufnehmen(x.d);
        setzenAuf(x.d.id);
      })
      .catch(function () { melden("Hochladen ging nicht."); })
      .finally(function () { box.classList.remove("laedt"); });
  });

  fetch(adresse, {credentials: "same-origin"})
    .then(function (a) { return a.json(); })
    .then(function (d) {
      d.grafiken.forEach(aufnehmen);
      zeichnen();
    })
    .catch(function () { melden("Die Grafiken konnten nicht geladen werden."); });
})();
