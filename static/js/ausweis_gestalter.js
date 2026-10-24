// Ausweis-Gestalter: Elemente auf der Karte verschieben, in der Größe ändern und einstellen.
// Maße in Millimetern, von oben links. Gespeichert wird als JSON in versteckten Feldern; der
// Server prüft alles noch einmal (apps/kunden/ausweis.py).
(function () {
  "use strict";
  var daten = JSON.parse(document.getElementById("ausweis-daten").textContent);
  var M = daten.masse;
  var felder = { vorne: document.getElementById("id_vorne"), hinten: document.getElementById("id_hinten") };
  var seiten = {
    vorne: JSON.parse(felder.vorne.value || "[]"),
    hinten: JSON.parse(felder.hinten.value || "[]"),
  };
  var seite = "vorne";
  var auswahl = null;
  var karte = document.getElementById("ausweis-karte");
  var neuTyp = document.getElementById("neu-typ");
  var eigFelder = document.getElementById("eig-felder");
  var eigTitel = document.getElementById("eig-titel");
  var loeschen = document.getElementById("eig-loeschen");
  var PT_MM = 0.3528;

  document.getElementById("gestalter").hidden = false;

  function runden(z) { return Math.round(z * 2) / 2; }
  function grenzen(e) {
    var art = daten.typen[e.typ].art;
    if (art === "barcode") { e.b = Math.max(e.b, M.barcode_b); e.h = Math.max(e.h, M.barcode_h); }
    e.b = Math.min(Math.max(e.b, 2), M.b);
    e.h = Math.min(Math.max(e.h, 1), M.h);
    e.x = Math.min(Math.max(e.x, 0), M.b - e.b);
    e.y = Math.min(Math.max(e.y, 0), M.h - e.h);
  }
  function pflicht(e) { return seite === "vorne" && daten.typen[e.typ].pflicht; }
  function sichern() {
    felder.vorne.value = JSON.stringify(seiten.vorne);
    felder.hinten.value = JSON.stringify(seiten.hinten);
  }
  function text(e) {
    if (e.typ === "freitext") {
      var t = e.text || "";
      daten.platzhalter.forEach(function (p) { t = t.split("{" + p + "}").join(daten.beispiel[p] || ""); });
      return t || "Freier Text";
    }
    return daten.beispiel[e.typ] || daten.typen[e.typ].name;
  }

  function zeichnen() {
    var k = karte.clientWidth / M.b; // Pixel je Millimeter
    karte.innerHTML = "";
    var bild = seite === "vorne" ? daten.hintergrund : daten.hintergrund_hinten;
    karte.style.backgroundImage = bild ? "url('" + bild + "')" : "";
    seiten[seite].forEach(function (e, i) {
      var art = daten.typen[e.typ].art;
      var d = document.createElement("div");
      d.className = "ausweis-element art-" + art + (i === auswahl ? " gewaehlt" : "");
      stellen(d, e, k);
      d.title = daten.typen[e.typ].name;
      if (art === "text") {
        d.textContent = text(e);
        d.style.fontSize = e.groesse * PT_MM * k + "px";
        d.style.fontWeight = e.fett ? "700" : "400";
        d.style.color = e.farbe;
        d.style.justifyContent = { links: "flex-start", mitte: "center", rechts: "flex-end" }[e.ausrichtung];
      } else if (art === "flaeche") {
        d.style.background = e.farbe;
      } else if (art === "bild") {
        if (daten.logo) {
          var img = document.createElement("img");
          img.src = daten.logo;
          img.alt = "";
          d.appendChild(img);
          d.style.justifyContent = { links: "flex-start", mitte: "center", rechts: "flex-end" }[e.ausrichtung];
        } else {
          d.textContent = "Logo";
        }
      } else if (art === "barcode") {
        var balken = document.createElement("span");
        balken.className = "balken";
        d.appendChild(balken);
      }
      var griff = document.createElement("span");
      griff.className = "griff";
      d.appendChild(griff);
      ziehen(d, i, griff);
      karte.appendChild(d);
      if (art === "text") einpassen(d, e.groesse * PT_MM * k);
    });
    sichern();
  }

  // Wie im PDF: zu langen Text verkleinern, bis er in die Breite passt (höchstens bis 4 pt).
  function einpassen(d, px) {
    var kleinste = 4 * PT_MM * karte.clientWidth / M.b;
    while (d.scrollWidth > d.clientWidth + 1 && px > kleinste) {
      px *= 0.95;
      d.style.fontSize = px + "px";
    }
  }

  function stellen(d, e, k) {
    d.style.left = e.x * k + "px";
    d.style.top = e.y * k + "px";
    d.style.width = e.b * k + "px";
    d.style.height = e.h * k + "px";
  }

  function ziehen(d, i, griff) {
    d.addEventListener("pointerdown", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      var groesse = ev.target === griff;
      auswahl = i;
      karte.querySelectorAll(".gewaehlt").forEach(function (x) { x.classList.remove("gewaehlt"); });
      d.classList.add("gewaehlt");
      felderFuellen();
      var e = seiten[seite][i];
      var k = karte.clientWidth / M.b;
      var start = { x: ev.clientX, y: ev.clientY, ex: e.x, ey: e.y, eb: e.b, eh: e.h };
      d.setPointerCapture(ev.pointerId);
      function bewegen(m) {
        var dx = (m.clientX - start.x) / k, dy = (m.clientY - start.y) / k;
        if (groesse) { e.b = runden(start.eb + dx); e.h = runden(start.eh + dy); }
        else { e.x = runden(start.ex + dx); e.y = runden(start.ey + dy); }
        grenzen(e);
        stellen(d, e, k);
        felderFuellen();
      }
      function ende() {
        d.removeEventListener("pointermove", bewegen);
        d.removeEventListener("pointerup", ende);
        zeichnen();
        karte.focus();
      }
      d.addEventListener("pointermove", bewegen);
      d.addEventListener("pointerup", ende);
    });
  }

  function waehlen(i) {
    auswahl = i;
    zeichnen();
    felderFuellen();
  }

  function felderFuellen() {
    var e = auswahl === null ? null : seiten[seite][auswahl];
    eigFelder.hidden = !e;
    loeschen.hidden = !e || pflicht(e);
    if (!e) { eigTitel.textContent = "Element wählen"; return; }
    var art = daten.typen[e.typ].art;
    eigTitel.textContent = daten.typen[e.typ].name;
    eigFelder.querySelectorAll("[data-eig]").forEach(function (f) {
      var wert = e[f.dataset.eig];
      if (f.type === "checkbox") f.checked = !!wert;
      else if (document.activeElement !== f) f.value = wert === undefined ? "" : wert;
    });
    eigFelder.querySelectorAll(".nur-text").forEach(function (f) { f.hidden = art !== "text"; });
    eigFelder.querySelectorAll(".nur-farbe").forEach(function (f) { f.hidden = art !== "text" && art !== "flaeche"; });
    eigFelder.querySelectorAll(".nur-freitext").forEach(function (f) { f.hidden = e.typ !== "freitext"; });
    var ausrichtung = eigFelder.querySelector("#eig-ausrichtung").closest(".feld");
    ausrichtung.hidden = art === "flaeche";
  }

  eigFelder.addEventListener("input", function (ev) {
    var f = ev.target, e = seiten[seite][auswahl];
    if (!e || !f.dataset.eig) return;
    var name = f.dataset.eig;
    if (f.type === "checkbox") e[name] = f.checked;
    else if (f.type === "number") { if (f.value === "") return; e[name] = parseFloat(f.value); }
    else e[name] = f.value;
    if (name !== "groesse" && f.type === "number") grenzen(e);
    zeichnen();
  });

  karte.addEventListener("keydown", function (ev) {
    if (auswahl === null) return;
    var schritt = ev.shiftKey ? 5 : 0.5;
    var e = seiten[seite][auswahl];
    var wege = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[ev.key];
    if (!wege) return;
    ev.preventDefault();
    e.x += wege[0] * schritt;
    e.y += wege[1] * schritt;
    grenzen(e);
    zeichnen();
    felderFuellen();
  });
  karte.addEventListener("pointerdown", function (ev) {
    if (ev.target === karte) { auswahl = null; zeichnen(); felderFuellen(); }
  });

  function typenListe() {
    neuTyp.innerHTML = "";
    Object.keys(daten.typen).forEach(function (t) {
      var vorhanden = seiten[seite].some(function (e) { return e.typ === t; });
      if (daten.typen[t].pflicht && vorhanden) return; // Pflicht-Elemente gibt es nur einmal
      var o = document.createElement("option");
      o.value = t;
      o.textContent = daten.typen[t].name;
      neuTyp.appendChild(o);
    });
  }

  document.getElementById("neu-knopf").addEventListener("click", function () {
    var t = neuTyp.value;
    if (!t) return;
    var art = daten.typen[t].art;
    var e = { typ: t, x: 4, y: 4, b: art === "barcode" ? 50 : 30, h: art === "barcode" ? 12 : 5,
              ausrichtung: "links", farbe: art === "flaeche" ? "#e8710a" : "#000000" };
    if (art === "text") { e.groesse = 9; e.fett = false; }
    if (t === "freitext") e.text = "";
    grenzen(e);
    seiten[seite].push(e);
    typenListe();
    waehlen(seiten[seite].length - 1);
  });

  loeschen.addEventListener("click", function () {
    if (auswahl === null || pflicht(seiten[seite][auswahl])) return;
    seiten[seite].splice(auswahl, 1);
    auswahl = null;
    typenListe();
    zeichnen();
    felderFuellen();
  });

  document.querySelectorAll("[data-seite]").forEach(function (a) {
    a.addEventListener("click", function (ev) {
      ev.preventDefault();
      seite = a.dataset.seite;
      auswahl = null;
      document.querySelectorAll("[data-seite]").forEach(function (b) {
        if (b === a) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
      });
      document.getElementById("rueckseite-hinweis").hidden = seite !== "hinten";
      typenListe();
      zeichnen();
      felderFuellen();
    });
  });

  window.addEventListener("resize", zeichnen);
  typenListe();
  zeichnen();
  felderFuellen();
})();
