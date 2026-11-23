// Editor für eigene HTML-Texte (Antragstexte, Serienbrief-Vorlagen): Reiter „Gestalten“ mit Knöpfen
// (fett, Überschrift, Schriftgröße, Ausrichtung, Liste, Text- und Markierfarbe, farbige Kästen,
// Link, Bild) und „HTML“ mit dem Quelltext. Beide zeigen denselben Text; gespeichert wird immer
// das Textfeld. Vor dem Anzeigen fallen Skripte und Ereignisse weg, beim Speichern bereinigt der
// Server ohnehin (apps.core.html).
//
// Am Textfeld: data-editor-ohne="link bild" blendet Knöpfe aus. data-platzhalter='{"anrede":
// "Briefanrede", …}' zeigt {anrede} im Reiter „Gestalten“ als farbiges, nicht editierbares Feld;
// im Textfeld steht weiter {anrede}. Knöpfe mit data-platzhalter-karte="anrede" data-fuer="<id>"
// lassen sich in den Text ziehen oder antippen (fügt an der Schreibmarke ein, ADR 0088). Das × am
// Feld (oder Feld antippen und Entf/Rücktaste) entfernt es wieder.
(function () {
  "use strict";

  var VERBOTEN = ["SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "FORM", "INPUT", "BUTTON",
                  "TEXTAREA", "SELECT", "LINK", "META", "BASE"];
  // Gruppen der Werkzeugleiste: [Name, [[Befehl, Aufschrift, Erklärung], …], im Menü „Mehr“?]
  var GRUPPEN = [
    ["Schrift", [["bold", "F", "Fett"], ["italic", "K", "Kursiv"], ["underline", "U", "Unterstrichen"],
                 ["h2", "Überschrift", "Überschrift"], ["p", "Absatz", "Normaler Absatz"]]],
    ["Ausrichtung", [["justifyLeft", "Links", "Linksbündig"], ["justifyCenter", "Mitte", "Zentriert"],
                     ["justifyRight", "Rechts", "Rechtsbündig"], ["justifyFull", "Blocksatz", "Blocksatz"]]],
    ["Liste", [["insertUnorderedList", "• Liste", "Aufzählung"],
               ["insertOrderedList", "1. Liste", "Nummerierung"]]],
    ["Farbe", [["farbe", "Text", "Textfarbe der Auswahl"], ["markieren", "Markieren", "Hintergrundfarbe der Auswahl"],
               ["kasten", "Kasten", "Farbiger Kasten: Auswahl (oder neuer Text) mit Hintergrundfarbe"]], true],
    ["Einfügen", [["link", "Link", "Link"], ["bild", "Bild", "Bild (Adresse)"]]],
    ["Format", [["removeFormat", "Format weg", "Formatierung entfernen"]], true],
  ];
  var FARBEN = {farbe: "#c1121f", markieren: "#fff3a3", kasten: "#fdf3d8"};
  var KASTEN = "padding:12px 16px;border-radius:8px;margin:8px 0;background-color:";
  // Schriftgröße als Auswahl in der Leiste: [Stufe für execCommand, Aufschrift]; mit styleWithCSS
  // wird daraus font-size: x-small … xx-large (so versteht es auch der PDF-Druck)
  var GROESSEN = [["1", "sehr klein"], ["2", "klein"], ["3", "normal"], ["4", "etwas größer"],
                  ["5", "groß"], ["6", "sehr groß"]];
  var BLOCK = "p, div, li, h1, h2, h3, h4, blockquote, td, th";
  var TYP = "application/x-bintafeln-platzhalter";
  var editoren = {}; // id des Textfelds -> Funktion, die einen Platzhalter einfügt

  function sauber(html) {
    var doc = new DOMParser().parseFromString("<body>" + html + "</body>", "text/html");
    doc.body.querySelectorAll("*").forEach(function (el) {
      if (VERBOTEN.indexOf(el.tagName) >= 0) { el.remove(); return; }
      Array.prototype.slice.call(el.attributes).forEach(function (a) {
        var wert = a.value.replace(/\s/g, "").toLowerCase();
        if (a.name.indexOf("on") === 0 || wert.indexOf("javascript:") === 0) el.removeAttribute(a.name);
      });
    });
    return doc.body.innerHTML;
  }

  function hatHtml(text) { return /<[a-zA-Z\/][^>]*>/.test(text); }

  function textEinfuegen(el, text) {
    var a = el.selectionStart == null ? el.value.length : el.selectionStart;
    var b = el.selectionEnd == null ? a : el.selectionEnd;
    el.focus();
    el.setRangeText(text, a, b, "end");
    el.dispatchEvent(new Event("input", {bubbles: true}));
  }

  function stelle(x, y) { // Einfügestelle unter dem Mauszeiger bzw. Finger
    if (document.caretRangeFromPoint) return document.caretRangeFromPoint(x, y);
    if (document.caretPositionFromPoint) {
      var p = document.caretPositionFromPoint(x, y);
      if (!p) return null;
      var r = document.createRange();
      r.setStart(p.offsetNode, p.offset);
      r.collapse(true);
      return r;
    }
    return null;
  }

  function einrichten(feld) {
    var ohne = (feld.dataset.editorOhne || "").split(/\s+/);
    var namen = null;
    try { namen = feld.dataset.platzhalter ? JSON.parse(feld.dataset.platzhalter) : null; } catch (e) { namen = null; }
    var rahmen = document.createElement("div");
    rahmen.className = "editor";
    var reiter = document.createElement("div");
    reiter.className = "editor-reiter";
    reiter.setAttribute("role", "tablist");
    var leiste = document.createElement("div");
    leiste.className = "editor-leiste";
    var flaeche = document.createElement("div");
    flaeche.className = "editor-flaeche";
    flaeche.contentEditable = "true";
    flaeche.setAttribute("role", "textbox");
    flaeche.setAttribute("aria-multiline", "true");
    flaeche.setAttribute("aria-label", (feld.labels && feld.labels[0] ? feld.labels[0].textContent : "Text") + " gestalten");
    flaeche.dir = feld.dir || "auto";
    var knoepfe = {};
    ["gestalten", "html"].forEach(function (art) {
      var k = document.createElement("button");
      k.type = "button";
      k.textContent = art === "gestalten" ? "Gestalten" : "HTML";
      k.setAttribute("role", "tab");
      k.addEventListener("click", function () { zeigen(art); });
      reiter.appendChild(k);
      knoepfe[art] = k;
    });

    var gemerkt = null; // Auswahl, solange ein Farbfeld offen ist

    function merken() {
      var s = window.getSelection();
      if (s.rangeCount && flaeche.contains(s.anchorNode)) gemerkt = s.getRangeAt(0).cloneRange();
    }

    function zurueck() {
      if (!gemerkt) return;
      var s = window.getSelection();
      s.removeAllRanges();
      s.addRange(gemerkt);
    }

    // Seltenes (Farben, Format weg) im aufklappbaren Menü „Mehr“, damit die Leiste ruhig bleibt
    var mehr = document.createElement("details");
    mehr.className = "editor-mehr";
    var mehrTitel = document.createElement("summary");
    mehrTitel.textContent = "Mehr";
    mehrTitel.title = "Farben, Kasten, Format entfernen";
    mehrTitel.addEventListener("mousedown", function (e) { e.preventDefault(); }); // Auswahl behalten
    var mehrInhalt = document.createElement("div");
    mehrInhalt.className = "editor-mehr-inhalt";
    mehr.appendChild(mehrTitel);
    mehr.appendChild(mehrInhalt);
    document.addEventListener("click", function (e) { if (mehr.open && !mehr.contains(e.target)) mehr.open = false; });

    GRUPPEN.forEach(function (g) {
      var gruppe = document.createElement("div");
      gruppe.className = "editor-gruppe";
      gruppe.setAttribute("role", "group");
      gruppe.setAttribute("aria-label", g[0]);
      g[1].forEach(function (b) {
        if (ohne.indexOf(b[0]) >= 0) return;
        var k = document.createElement("button");
        k.type = "button";
        k.textContent = b[1];
        k.title = b[2];
        if (b[1].length === 1) k.setAttribute("aria-label", b[2]); // F, K, U vorlesbar
        k.dataset.befehl = b[0];
        k.addEventListener("mousedown", function (e) { e.preventDefault(); }); // Auswahl behalten
        if (FARBEN[b[0]]) {
          // Farbknopf: Klick wendet die Farbe an, das Feld daneben wählt sie
          var wahl = document.createElement("input");
          wahl.type = "color";
          wahl.value = FARBEN[b[0]];
          wahl.title = b[2] + ": Farbe wählen";
          wahl.setAttribute("aria-label", b[2] + ": Farbe wählen");
          wahl.addEventListener("pointerdown", merken);
          wahl.addEventListener("focus", merken);
          wahl.addEventListener("change", function () {
            FARBEN[b[0]] = wahl.value;
            k.style.setProperty("--farbe", wahl.value);
            zurueck();
            knopf(b[0], true);
          });
          k.style.setProperty("--farbe", wahl.value);
          k.classList.add("editor-farbknopf");
          k.addEventListener("click", function () { knopf(b[0]); });
          var paar = document.createElement("span");
          paar.className = "editor-farbpaar";
          paar.appendChild(k);
          paar.appendChild(wahl);
          gruppe.appendChild(paar);
          return;
        }
        k.addEventListener("click", function () { knopf(b[0]); });
        gruppe.appendChild(k);
      });
      if (!gruppe.children.length) return; // alle Knöpfe ausgeblendet
      (g[2] ? mehrInhalt : leiste).appendChild(gruppe);
    });
    // Schriftgröße: Auswahl gleich neben „Schrift“. Mit markiertem Text gilt sie für die
    // Markierung, ohne Markierung für die ganze Zeile, in der die Schreibmarke steht.
    if (ohne.indexOf("groesse") < 0) {
      var groesse = document.createElement("div");
      groesse.className = "editor-gruppe";
      groesse.setAttribute("role", "group");
      groesse.setAttribute("aria-label", "Größe");
      var wahlGroesse = document.createElement("select");
      wahlGroesse.className = "editor-groesse";
      wahlGroesse.title = "Schriftgröße der Markierung – ohne Markierung der ganzen Zeile";
      wahlGroesse.setAttribute("aria-label", "Schriftgröße");
      var leer = document.createElement("option");
      leer.value = "";
      leer.textContent = "Schriftgröße";
      wahlGroesse.appendChild(leer);
      GROESSEN.forEach(function (g) {
        var o = document.createElement("option");
        o.value = g[0];
        o.textContent = g[1];
        wahlGroesse.appendChild(o);
      });
      wahlGroesse.addEventListener("pointerdown", merken);
      wahlGroesse.addEventListener("focus", merken);
      wahlGroesse.addEventListener("change", function () {
        var stufe = wahlGroesse.value;
        wahlGroesse.value = "";  // zeigt wieder „Schriftgröße“: die Auswahl ist ein Befehl
        if (!stufe) return;
        zurueck();
        zeileWaehlen();
        befehl("fontSize", stufe);
      });
      groesse.appendChild(wahlGroesse);
      var nachSchrift = leiste.querySelector('.editor-gruppe[aria-label="Schrift"]');
      leiste.insertBefore(groesse, nachSchrift ? nachSchrift.nextSibling : leiste.firstChild);
    }
    if (mehrInhalt.children.length) leiste.appendChild(mehr);

    // Knopf „Grafik“ (ADR 0138): eigene Bilder auswählen oder hochladen, Größe wählen, entfernen.
    // data-editor-grafiken="<Adresse>": GET liefert die Liste, POST (Feld „datei“) lädt hoch.
    if (feld.dataset.editorGrafiken) grafikenEinrichten(feld.dataset.editorGrafiken);

    function grafikenEinrichten(liste) {
      var GROESSE = {klein: "25%", mittel: "50%", gross: "100%"};
      var stelleVorher = null, gewaehlt = null;
      var gruppe = document.createElement("div");
      gruppe.className = "editor-gruppe";
      var k = document.createElement("button");
      k.type = "button";
      k.textContent = "Grafik";
      k.title = "Grafik oder Bild in den Text einfügen";
      k.addEventListener("mousedown", function (e) { e.preventDefault(); });
      gruppe.appendChild(k);
      leiste.insertBefore(gruppe, leiste.querySelector(".editor-mehr"));

      var dialog = document.createElement("dialog");
      dialog.className = "grafik-dialog";
      dialog.innerHTML =
        '<form method="dialog"><h2></h2>' +
        '<fieldset class="grafik-groesse"><legend>Größe</legend>' +
        '<label><input type="radio" name="groesse" value="klein"> klein</label>' +
        '<label><input type="radio" name="groesse" value="mittel" checked> mittel</label>' +
        '<label><input type="radio" name="groesse" value="gross"> ganze Breite</label></fieldset>' +
        '<p class="hinweis grafik-ausrichtung">Ausrichten wie Text: Grafik antippen, dann „Links“, „Mitte“ oder „Rechts“.</p>' +
        '<div class="grafik-auswahl"><p class="hinweis">Antippen fügt die Grafik an der Schreibmarke ein.</p>' +
        '<ul class="grafik-liste"></ul>' +
        '<label class="knopf knopf-zweitrangig grafik-hochladen">Neue Grafik hochladen …' +
        '<input type="file" accept="image/png,image/jpeg,application/pdf" hidden></label>' +
        '<label class="grafik-freistellen"><input type="checkbox"> Hintergrund durchsichtig machen (Unterschrift, Stempel)</label>' +
        '<p class="hinweis">PNG, JPG oder PDF (davon die erste Seite).</p></div>' +
        '<p class="fehler grafik-fehler" role="alert" hidden></p>' +
        '<div class="aktionsleiste"><button type="button" class="knopf knopf-gefahr grafik-entfernen">Grafik entfernen</button>' +
        '<button value="zu" class="knopf knopf-abbrechen">Schließen</button></div></form>';
      document.body.appendChild(dialog); // nicht ins Formular der Seite (keine verschachtelten Formulare)
      var titel = dialog.querySelector("h2"), ul = dialog.querySelector(".grafik-liste");
      var fehler = dialog.querySelector(".grafik-fehler"), datei = dialog.querySelector("input[type=file]");
      var entfernen = dialog.querySelector(".grafik-entfernen"), auswahl = dialog.querySelector(".grafik-auswahl");
      var token = feld.form && feld.form.querySelector("[name=csrfmiddlewaretoken]");

      function groesse() { return GROESSE[dialog.querySelector("[name=groesse]:checked").value]; }
      function melden(text) { fehler.textContent = text || ""; fehler.hidden = !text; }

      function einfuegen(g) {
        var img = document.createElement("img");
        img.src = g.adresse;
        img.alt = g.name;
        img.setAttribute("width", groesse());
        var r = stelleVorher;
        if (!r || !flaeche.contains(r.startContainer)) {
          r = document.createRange();
          r.selectNodeContents(flaeche);
          r.collapse(false);
        }
        r.deleteContents();
        r.insertNode(img);
        r.setStartAfter(img);
        r.collapse(true);
        var s = window.getSelection();
        s.removeAllRanges();
        s.addRange(r);
        uebertragen();
        dialog.close();
      }

      function eintrag(g) {
        var li = document.createElement("li");
        var wahl = document.createElement("button");
        wahl.type = "button";
        wahl.className = "grafik-wahl";
        wahl.title = g.name + " einfügen";
        var bild = document.createElement("img");
        bild.src = g.adresse;
        bild.alt = g.name;
        bild.loading = "lazy";
        wahl.appendChild(bild);
        wahl.addEventListener("click", function () { einfuegen(g); });
        var weg = document.createElement("button");
        weg.type = "button";
        weg.className = "grafik-weg";
        weg.textContent = "×";
        weg.title = g.name + " löschen (in den Papierkorb)";
        weg.setAttribute("aria-label", weg.title);
        weg.addEventListener("click", function () {
          if (!window.confirm("Grafik „" + g.name + "“ löschen? Vorlagen, die sie zeigen, lassen die Stelle dann leer.")) return;
          var daten = new FormData();
          if (token) daten.append("csrfmiddlewaretoken", token.value);
          fetch(g.loeschen, {method: "POST", body: daten, credentials: "same-origin"}).then(function (a) {
            if (a.ok) li.remove(); else melden("Löschen ging nicht.");
          });
        });
        li.appendChild(wahl);
        li.appendChild(weg);
        return li;
      }

      function laden() {
        ul.textContent = "";
        fetch(liste, {credentials: "same-origin"}).then(function (a) { return a.json(); }).then(function (d) {
          d.grafiken.forEach(function (g) { ul.appendChild(eintrag(g)); });
        }).catch(function () { melden("Die Grafiken konnten nicht geladen werden."); });
      }

      datei.addEventListener("change", function () {
        if (!datei.files.length) return;
        var daten = new FormData();
        daten.append("datei", datei.files[0]);
        if (dialog.querySelector(".grafik-freistellen input").checked) daten.append("freistellen", "1");
        if (token) daten.append("csrfmiddlewaretoken", token.value);
        melden("");
        fetch(liste, {method: "POST", body: daten, credentials: "same-origin"})
          .then(function (a) { return a.json().then(function (d) { return {ok: a.ok, d: d}; }); })
          .then(function (x) {
            datei.value = "";
            if (!x.ok) return melden(x.d.fehler || "Hochladen ging nicht.");
            einfuegen(x.d);
          })
          .catch(function () { melden("Hochladen ging nicht."); });
      });

      dialog.querySelectorAll("[name=groesse]").forEach(function (r) {
        r.addEventListener("change", function () {
          if (!gewaehlt) return;
          gewaehlt.setAttribute("width", groesse());
          uebertragen();
        });
      });
      entfernen.addEventListener("click", function () {
        if (gewaehlt) { gewaehlt.remove(); uebertragen(); }
        dialog.close();
      });
      dialog.addEventListener("close", function () { gewaehlt = null; });

      function oeffnen(img) {
        gewaehlt = img || null;
        melden("");
        titel.textContent = img ? "Grafik ändern" : "Grafik einfügen";
        auswahl.hidden = !!img;
        entfernen.hidden = !img;
        var jetzt = img ? (img.getAttribute("width") || "50%") : "50%";
        Object.keys(GROESSE).forEach(function (n) {
          dialog.querySelector("[name=groesse][value=" + n + "]").checked = GROESSE[n] === jetzt;
        });
        if (!img) laden();
        dialog.showModal();
      }

      k.addEventListener("click", function () {
        var s = window.getSelection();
        stelleVorher = s.rangeCount && flaeche.contains(s.anchorNode) ? s.getRangeAt(0).cloneRange() : null;
        oeffnen(null);
      });
      flaeche.addEventListener("dblclick", function (e) {
        if (e.target.tagName === "IMG") oeffnen(e.target);
      });
      flaeche.addEventListener("click", function (e) {
        if (e.target.tagName !== "IMG") return;
        var r = document.createRange(); // Grafik antippen: Schreibmarke dahinter (zum Ausrichten)
        r.setStartAfter(e.target);
        r.collapse(true);
        var s = window.getSelection();
        s.removeAllRanges();
        s.addRange(r);
        if (e.detail === 1) window.setTimeout(function () { if (!dialog.open) oeffnenFrage(e.target); }, 0);
      });
      function oeffnenFrage(img) { // kleiner Knopf an der Grafik: „Ändern“
        var alt = rahmen.querySelector(".grafik-aendern");
        if (alt) alt.remove();
        var b = document.createElement("button");
        b.type = "button";
        b.className = "knopf grafik-aendern";
        b.textContent = "Grafik ändern";
        var r1 = img.getBoundingClientRect(), r2 = rahmen.getBoundingClientRect();
        b.style.top = (r1.top - r2.top + 6) + "px";
        b.style.left = (r1.left - r2.left + 6) + "px";
        b.addEventListener("mousedown", function (e) { e.preventDefault(); });
        b.addEventListener("click", function () { b.remove(); oeffnen(img); });
        rahmen.appendChild(b);
        var weg = function (e) {
          if (e.target === b) return;
          b.remove();
          document.removeEventListener("pointerdown", weg, true);
        };
        document.addEventListener("pointerdown", weg, true);
      }
    }

    // „Standard"-Knopf: setzt den Text auf die mitgelieferte Vorgabe zurück (nur wenn eine
    // Vorgabe über data-standard hinterlegt ist).
    if (feld.dataset.standard != null) {
      var gstd = document.createElement("div");
      gstd.className = "editor-gruppe";
      var std = document.createElement("button");
      std.type = "button";
      std.textContent = "Standard";
      std.title = "Diesen Text auf die mitgelieferte Vorgabe zurücksetzen";
      std.addEventListener("mousedown", function (e) { e.preventDefault(); });
      std.addEventListener("click", function () {
        if (!window.confirm("Diesen Text auf die Vorgabe zurücksetzen? Ihre Änderung geht verloren.")) return;
        feld.value = feld.dataset.standard;
        if (rahmen.dataset.ansicht === "gestalten") { flaeche.innerHTML = sauber(feld.value); felderZeigen(); }
        feld.dispatchEvent(new Event("input", {bubbles: true})); // Autosave speichert
      });
      gstd.appendChild(std);
      leiste.appendChild(gstd);
    }

    function platzhalterFeld(name) {
      var s = document.createElement("span");
      s.className = "platzhalter";
      s.contentEditable = "false";
      s.dataset.platzhalter = name;
      s.textContent = namen[name] || name;
      return s;
    }

    function felderZeigen() { // {anrede} im Text -> farbiges Feld (nur bekannte Platzhalter)
      if (!namen) return;
      var gang = document.createTreeWalker(flaeche, NodeFilter.SHOW_TEXT), liste = [], n;
      while ((n = gang.nextNode())) if (/\{\w+\}/.test(n.nodeValue)) liste.push(n);
      liste.forEach(function (t) {
        var stueck = document.createDocumentFragment();
        t.nodeValue.split(/(\{\w+\})/).forEach(function (teil) {
          var m = /^\{(\w+)\}$/.exec(teil);
          if (m && Object.prototype.hasOwnProperty.call(namen, m[1])) stueck.appendChild(platzhalterFeld(m[1]));
          else if (teil) stueck.appendChild(document.createTextNode(teil));
        });
        t.parentNode.replaceChild(stueck, t);
      });
    }

    function uebertragen() {
      var vorher = feld.value;
      if (!namen) {
        feld.value = flaeche.innerHTML;
      } else {
        var kopie = flaeche.cloneNode(true); // Felder wieder als {anrede}
        kopie.querySelectorAll("[data-platzhalter]").forEach(function (s) {
          s.parentNode.replaceChild(document.createTextNode("{" + s.dataset.platzhalter + "}"), s);
        });
        feld.value = kopie.innerHTML;
      }
      // Dem Formular Bescheid geben: Seiten ohne Speichern-Knopf speichern dann von selbst
      // (autosave.js hört auf das Textfeld, nicht auf die Gestalten-Fläche)
      if (feld.value !== vorher) feld.dispatchEvent(new Event("input", {bubbles: true}));
    }

    // Ohne Markierung die Zeile (den Absatz) wählen, in der die Schreibmarke steht
    function zeileWaehlen() {
      var s = window.getSelection();
      if (!s.rangeCount || !s.isCollapsed || !flaeche.contains(s.anchorNode)) return;
      var knoten = s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement;
      var zeile = knoten && knoten.closest(BLOCK);
      if (!zeile || !flaeche.contains(zeile) || zeile === flaeche) zeile = flaeche;
      var bereich = document.createRange();
      bereich.selectNodeContents(zeile);
      s.removeAllRanges();
      s.addRange(bereich);
    }

    function befehl(name, wert) {
      flaeche.focus();
      document.execCommand("styleWithCSS", false, true);
      document.execCommand(name, false, wert);
      uebertragen();
    }

    function kastenHier() {
      var s = window.getSelection();
      var knoten = s.rangeCount ? s.getRangeAt(0).commonAncestorContainer : null;
      var el = knoten && (knoten.nodeType === 1 ? knoten : knoten.parentElement);
      var kasten = el && el.closest(".kasten");
      return kasten && flaeche.contains(kasten) ? kasten : null;
    }

    function kasten(nurUmfaerben) {
      var drin = kastenHier();
      if (drin) { // Kasten umfärben
        drin.style.backgroundColor = FARBEN.kasten;
        uebertragen();
        return;
      }
      if (nurUmfaerben) return;
      var s = window.getSelection();
      var inhalt = "<p>Text im Kasten</p>";
      if (s.rangeCount && !s.isCollapsed && flaeche.contains(s.anchorNode)) {
        var hilfe = document.createElement("div");
        hilfe.appendChild(s.getRangeAt(0).cloneContents());
        inhalt = hilfe.innerHTML;
      }
      befehl("insertHTML", '<div class="kasten" style="' + KASTEN + FARBEN.kasten + '">' + inhalt + "</div><p><br></p>");
    }

    function knopf(name, ausFarbfeld) {
      if (name === "farbe") return befehl("foreColor", FARBEN.farbe);
      if (name === "markieren") return befehl("hiliteColor", FARBEN.markieren);
      if (name === "kasten") return kasten(ausFarbfeld);
      if (name === "h2" || name === "p") return befehl("formatBlock", "<" + name + ">");
      if (name === "link") {
        var url = window.prompt("Adresse des Links (https://…)", "https://");
        if (url && /^(https?:|mailto:|tel:)/i.test(url)) befehl("createLink", url);
        return;
      }
      if (name === "bild") {
        var bild = window.prompt("Adresse des Bildes (https://…)", "https://");
        if (bild && /^https?:/i.test(bild)) befehl("insertImage", bild);
        return;
      }
      befehl(name);
    }

    function zeigen(art) {
      var html = art === "html";
      // Nur aus einer schon bestückten „Gestalten"-Ansicht ins Textfeld übertragen – beim ersten
      // Aufruf ist die Fläche noch leer und würde sonst den gespeicherten Text löschen.
      if (html) { if (rahmen.dataset.ansicht === "gestalten") uebertragen(); }
      else { flaeche.innerHTML = sauber(feld.value); felderZeigen(); }
      feld.hidden = !html;
      flaeche.hidden = leiste.hidden = html;
      knoepfe.html.setAttribute("aria-selected", html ? "true" : "false");
      knoepfe.gestalten.setAttribute("aria-selected", html ? "false" : "true");
      rahmen.dataset.ansicht = art;
    }

    flaeche.addEventListener("input", uebertragen);

    if (namen) {
      var marke = null; // letzte Schreibmarke in der Fläche (beim Antippen einer Karte weg)
      document.addEventListener("selectionchange", function () {
        var s = window.getSelection();
        if (s.rangeCount && flaeche.contains(s.anchorNode)) marke = s.getRangeAt(0).cloneRange();
      });

      var einfuegen = function (name, stelleHier) {
        if (rahmen.dataset.ansicht === "html") return textEinfuegen(feld, "{" + name + "}");
        var r = stelleHier || (marke && flaeche.contains(marke.startContainer) ? marke : null);
        if (!r) { // noch nie hineingeklickt: ans Ende des letzten Absatzes
          r = document.createRange();
          var letzter = flaeche.lastElementChild;
          r.selectNodeContents(letzter && /^(P|DIV|H[1-4])$/.test(letzter.tagName) ? letzter : flaeche);
          r.collapse(false);
        }
        var start = r.startContainer.nodeType === 1 ? r.startContainer : r.startContainer.parentElement;
        var drin = start && start.closest(".platzhalter");
        if (drin && flaeche.contains(drin)) { r = document.createRange(); r.setStartAfter(drin); r.collapse(true); }
        var span = platzhalterFeld(name);
        r.deleteContents();
        r.insertNode(span);
        if (!span.nextSibling) span.parentNode.insertBefore(document.createTextNode(" "), span.nextSibling);
        flaeche.focus({preventScroll: true});
        var danach = document.createRange();
        danach.setStartAfter(span);
        danach.collapse(true);
        var s = window.getSelection();
        s.removeAllRanges();
        s.addRange(danach);
        marke = danach.cloneRange();
        uebertragen();
      };
      if (feld.id) editoren[feld.id] = einfuegen;

      // Entfernen: das × am Feld antippen, oder Feld antippen (markiert es) und Entf/Rücktaste
      var entfernen = function (span) {
        var r = document.createRange();
        r.setStartBefore(span);
        r.collapse(true);
        span.remove();
        var s = window.getSelection();
        s.removeAllRanges();
        s.addRange(r);
        marke = r.cloneRange();
        uebertragen();
      };
      flaeche.addEventListener("click", function (e) {
        var span = e.target.closest && e.target.closest(".platzhalter");
        if (!span || !flaeche.contains(span)) return;
        if (e.clientX >= span.getBoundingClientRect().right - 22) { e.preventDefault(); entfernen(span); }
      });
      flaeche.addEventListener("keydown", function (e) {
        if (e.key !== "Backspace" && e.key !== "Delete") return;
        var s = window.getSelection();
        if (!s.rangeCount || s.isCollapsed) return;
        var r = s.getRangeAt(0);
        var start = r.startContainer.nodeType === 1 ? r.startContainer : r.startContainer.parentElement;
        var span = start && start.closest(".platzhalter");
        if (!span) { // ganzes Feld markiert: Bereich umschließt genau ein Feld
          var felder = Array.prototype.filter.call(flaeche.querySelectorAll(".platzhalter"),
            function (f) { return r.intersectsNode(f); });
          if (felder.length !== 1 || r.toString().trim() !== felder[0].textContent.trim()) return;
          span = felder[0];
        }
        e.preventDefault();
        entfernen(span);
      });

      var gezogen = function (e) {
        return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types, TYP) >= 0;
      };
      flaeche.addEventListener("dragover", function (e) {
        if (!gezogen(e)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
      });
      flaeche.addEventListener("drop", function (e) {
        if (!gezogen(e)) return; // anderes Ziehen (z. B. markierter Text) macht der Browser
        var name = e.dataTransfer.getData(TYP);
        e.preventDefault();
        if (!Object.prototype.hasOwnProperty.call(namen, name)) return;
        var r = stelle(e.clientX, e.clientY);
        einfuegen(name, r && flaeche.contains(r.startContainer) ? r : null);
      });
    }
    feld.parentNode.insertBefore(rahmen, feld);
    rahmen.appendChild(reiter);
    rahmen.appendChild(leiste);
    rahmen.appendChild(flaeche);
    rahmen.appendChild(feld);
    if (feld.form) feld.form.addEventListener("submit", function () {
      if (rahmen.dataset.ansicht === "gestalten") uebertragen();
    });
    // Reiner Text ohne HTML (Zeilenumbrüche zählen) bleibt zunächst im HTML-Reiter
    zeigen(!feld.value.trim() || hatHtml(feld.value) ? "gestalten" : "html");
  }

  try { document.execCommand("defaultParagraphSeparator", false, "p"); } catch (e) { /* ältere Browser */ }
  document.querySelectorAll("textarea[data-editor]").forEach(einrichten);

  // Platzhalter-Karten: ziehen oder antippen. Zuletzt im Betreff (data-platzhalter-ziel) oder im
  // HTML-Reiter gewesen? Dann dort einfügen, sonst im Editor an der Schreibmarke.
  var letztesZiel = null;
  document.addEventListener("focusin", function (e) {
    var t = e.target;
    if (!t || !t.matches) return;
    if (t.matches("input[data-platzhalter-ziel], textarea[data-platzhalter]")) letztesZiel = t;
    else if (t.closest(".editor-flaeche")) letztesZiel = null;
  });
  document.querySelectorAll("[data-platzhalter-karte]").forEach(function (karte) {
    var name = karte.dataset.platzhalterKarte;
    karte.addEventListener("click", function () {
      if (letztesZiel && letztesZiel.tagName === "INPUT") return textEinfuegen(letztesZiel, "{" + name + "}");
      var einfuegen = editoren[karte.dataset.fuer];
      if (einfuegen) einfuegen(name);
    });
    karte.addEventListener("dragstart", function (e) {
      e.dataTransfer.setData(TYP, name);
      e.dataTransfer.setData("text/plain", "{" + name + "}"); // für Betreff und HTML-Reiter
      e.dataTransfer.effectAllowed = "copy";
    });
  });
})();
