// Editor für eigene HTML-Texte (Antragstexte): Reiter „Gestalten“ mit Knöpfen (fett, Überschrift,
// Ausrichtung, Liste, Text- und Markierfarbe, farbige Kästen, Link, Bild) und „HTML“ mit dem
// Quelltext. Beide zeigen denselben
// Text; gespeichert wird immer das Textfeld. Vor dem Anzeigen fallen Skripte und Ereignisse weg,
// beim Speichern bereinigt der Server ohnehin (apps.core.html).
(function () {
  "use strict";

  var VERBOTEN = ["SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "FORM", "INPUT", "BUTTON",
                  "TEXTAREA", "SELECT", "LINK", "META", "BASE"];
  // Gruppen der Werkzeugleiste: [Name, [[Befehl, Aufschrift, Erklärung], …]]
  var GRUPPEN = [
    ["Schrift", [["bold", "F", "Fett"], ["italic", "K", "Kursiv"], ["underline", "U", "Unterstrichen"],
                 ["h2", "Überschrift", "Überschrift"], ["p", "Absatz", "Normaler Absatz"]]],
    ["Ausrichtung", [["justifyLeft", "Links", "Linksbündig"], ["justifyCenter", "Mitte", "Zentriert"],
                     ["justifyRight", "Rechts", "Rechtsbündig"], ["justifyFull", "Blocksatz", "Blocksatz"]]],
    ["Liste", [["insertUnorderedList", "• Liste", "Aufzählung"],
               ["insertOrderedList", "1. Liste", "Nummerierung"]]],
    ["Farbe", [["farbe", "Text", "Textfarbe der Auswahl"], ["markieren", "Markieren", "Hintergrundfarbe der Auswahl"],
               ["kasten", "Kasten", "Farbiger Kasten: Auswahl (oder neuer Text) mit Hintergrundfarbe"]]],
    ["Einfügen", [["link", "Link", "Link"], ["bild", "Bild", "Bild (Adresse)"],
                  ["removeFormat", "Format weg", "Formatierung entfernen"]]],
  ];
  var FARBEN = {farbe: "#c1121f", markieren: "#fff3a3", kasten: "#fdf3d8"};
  var KASTEN = "padding:12px 16px;border-radius:8px;margin:8px 0;background-color:";

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

  function einrichten(feld) {
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

    GRUPPEN.forEach(function (g) {
      var gruppe = document.createElement("div");
      gruppe.className = "editor-gruppe";
      gruppe.setAttribute("role", "group");
      gruppe.setAttribute("aria-label", g[0]);
      g[1].forEach(function (b) {
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
      leiste.appendChild(gruppe);
    });

    function uebertragen() { feld.value = flaeche.innerHTML; }

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
      if (html) uebertragen();
      else flaeche.innerHTML = sauber(feld.value);
      feld.hidden = !html;
      flaeche.hidden = leiste.hidden = html;
      knoepfe.html.setAttribute("aria-selected", html ? "true" : "false");
      knoepfe.gestalten.setAttribute("aria-selected", html ? "false" : "true");
      rahmen.dataset.ansicht = art;
    }

    flaeche.addEventListener("input", uebertragen);
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

  document.querySelectorAll("textarea[data-editor]").forEach(einrichten);
})();
