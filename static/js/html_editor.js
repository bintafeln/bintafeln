// Editor für eigene HTML-Texte (Antragstexte, Serienbrief-Vorlagen): Reiter „Gestalten“ mit Knöpfen
// (fett, Überschrift, Schriftgröße, Ausrichtung, Liste, Text- und Markierfarbe, farbige Kästen,
// Link, Bild) und „HTML“ mit dem Quelltext. Beide zeigen denselben Text; gespeichert wird immer
// das Textfeld. Vor dem Anzeigen fallen Skripte und Ereignisse weg, beim Speichern bereinigt der
// Server ohnehin (apps.core.html).
//
// Am Textfeld: data-editor-ohne="link bild" blendet Knöpfe aus. data-platzhalter='{"anrede":
// "Briefanrede", …}' zeigt {anrede} im Reiter „Gestalten“ als farbiges, nicht editierbares Feld;
// im Textfeld steht weiter {anrede}. Knöpfe mit data-platzhalter-karte="anrede" data-fuer="<id>"
// lassen sich in den Text ziehen oder antippen (fügt an der Schreibmarke ein, ADR 0088).
(function () {
  "use strict";

  var VERBOTEN = ["SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "FORM", "INPUT", "BUTTON",
                  "TEXTAREA", "SELECT", "LINK", "META", "BASE"];
  // Gruppen der Werkzeugleiste: [Name, [[Befehl, Aufschrift, Erklärung], …]]
  var GRUPPEN = [
    ["Schrift", [["bold", "F", "Fett"], ["italic", "K", "Kursiv"], ["underline", "U", "Unterstrichen"],
                 ["h2", "Überschrift", "Überschrift"], ["p", "Absatz", "Normaler Absatz"]]],
    ["Größe", [["klein", "klein", "Kleine Schrift"], ["normal", "normal", "Normale Schrift"],
               ["gross", "groß", "Große Schrift"]]],
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
  var GROESSEN = {klein: "2", normal: "3", gross: "5"}; // execCommand: small, medium, x-large
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
      leiste.appendChild(gruppe);
    });

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
      if (!namen) { feld.value = flaeche.innerHTML; return; }
      var kopie = flaeche.cloneNode(true); // Felder wieder als {anrede}
      kopie.querySelectorAll("[data-platzhalter]").forEach(function (s) {
        s.parentNode.replaceChild(document.createTextNode("{" + s.dataset.platzhalter + "}"), s);
      });
      feld.value = kopie.innerHTML;
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
      if (GROESSEN[name]) return befehl("fontSize", GROESSEN[name]);
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
