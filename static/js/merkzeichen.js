// Antragsformular: Die Merkzeichen (G, aG, H, B …) erscheinen erst, wenn bei derselben Person
// ein Grad der Behinderung gewählt ist. Ohne JavaScript bleiben sie immer sichtbar.
(function () {
  "use strict";

  document.querySelectorAll("[data-merkzeichen-fuer]").forEach(function (block) {
    var gdb = document.getElementById(block.dataset.merkzeichenFuer);
    if (!gdb) return;
    function zeigen() {
      var an = parseInt(gdb.value, 10) > 0;
      block.hidden = !an;
      if (!an) block.querySelectorAll("input[type=checkbox]").forEach(function (k) { k.checked = false; });
    }
    gdb.addEventListener("change", zeigen);
    zeigen();
  });
})();
