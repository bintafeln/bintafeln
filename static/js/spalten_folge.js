// Reihenfolge der Spalten im Menü „Spalten wählen“: Neben jeder Spalte sitzen zwei Pfeile, die
// sie um einen Platz nach vorn oder hinten schieben. Gespeichert wird beim „Übernehmen“ – jede
// Spalte schickt ihr verstecktes Feld „folge“ in der Reihenfolge der Seite mit
// (apps/core/listen.spalten_aus_post). Ohne JavaScript bleibt die Reihenfolge, wie sie ist.
(function () {
  "use strict";

  function knopf(zeichen, titel, schieben) {
    var k = document.createElement("button");
    k.type = "button";
    k.className = "spalten-pfeil";
    k.textContent = zeichen;
    k.title = titel;
    k.setAttribute("aria-label", titel);
    k.addEventListener("click", function (ereignis) {
      ereignis.preventDefault();  // der Knopf steht im <label>: kein Häkchen umschalten
      schieben(k.closest("label"));
      k.focus();
    });
    return k;
  }

  function einrichten(kasten) {
    if (kasten.dataset.folgeBereit) return;
    kasten.dataset.folgeBereit = "1";
    Array.prototype.forEach.call(kasten.querySelectorAll("label"), function (eintrag) {
      var name = eintrag.textContent.trim();
      eintrag.appendChild(knopf("◀", name + " nach vorn", function (e) {
        if (e.previousElementSibling) kasten.insertBefore(e, e.previousElementSibling);
      }));
      eintrag.appendChild(knopf("▶", name + " nach hinten", function (e) {
        if (e.nextElementSibling) kasten.insertBefore(e.nextElementSibling, e);
      }));
    });
    var hinweis = kasten.parentNode.querySelector(".spalten-folge-hinweis");
    if (hinweis) hinweis.hidden = false;
  }

  function alle(wurzel) {
    Array.prototype.forEach.call(
      (wurzel || document).querySelectorAll("[data-spalten-folge]"), einrichten);
  }

  document.addEventListener("DOMContentLoaded", function () { alle(); });
  document.addEventListener("htmx:afterSwap", function (e) { alle(e.target); });
}());
