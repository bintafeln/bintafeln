// Zeichnet Pfeile und Rahmen in Tafel-Orange über die Seite (Koordinaten der ganzen Seite);
// benutzt von tests/e2e/test_hilfe_bilder.py.
([marken, farbe]) => {
  const ns = "http://www.w3.org/2000/svg";
  const ebene = document.createElement("div");
  ebene.id = "hilfe-marken";
  ebene.style.cssText = "position:absolute;left:0;top:0;width:0;height:0;z-index:99999;pointer-events:none";
  document.body.appendChild(ebene);
  function nummer(n, x, y) {
    const k = document.createElement("div");
    k.textContent = n;
    k.style.cssText = `position:absolute;left:${x - 16}px;top:${y - 16}px;width:32px;height:32px;
      border-radius:50%;background:${farbe};color:#fff;font:700 18px/32px system-ui,sans-serif;
      text-align:center;box-shadow:0 0 0 3px #fff,0 2px 6px rgba(0,0,0,.35)`;
    ebene.appendChild(k);
  }
  for (const m of marken) {
    const b = m.box, L = m.laenge, ab = 8;
    if (m.art === "rahmen") {
      const r = document.createElement("div");
      r.style.cssText = `position:absolute;left:${b.x - 6}px;top:${b.y - 6}px;width:${b.width + 12}px;
        height:${b.height + 12}px;border:4px solid ${farbe};border-radius:10px;box-sizing:border-box;
        box-shadow:0 0 0 2px #fff`;
      ebene.appendChild(r);
      if (m.nummer) nummer(m.nummer, b.x - 6, b.y - 6);
      continue;
    }
    const mx = b.x + b.width / 2, my = b.y + b.height / 2;
    const ziel = {links: [b.x - ab, my], rechts: [b.x + b.width + ab, my],
                  oben: [mx, b.y - ab], unten: [mx, b.y + b.height + ab]}[m.von];
    const richtung = {links: [-1, 0], rechts: [1, 0], oben: [0, -1], unten: [0, 1]}[m.von];
    const start = [ziel[0] + richtung[0] * L, ziel[1] + richtung[1] * L];
    const svg = document.createElementNS(ns, "svg");
    const x0 = Math.min(start[0], ziel[0]) - 20, y0 = Math.min(start[1], ziel[1]) - 20;
    svg.setAttribute("width", Math.abs(start[0] - ziel[0]) + 40);
    svg.setAttribute("height", Math.abs(start[1] - ziel[1]) + 40);
    svg.style.cssText = `position:absolute;left:${x0}px;top:${y0}px;overflow:visible`;
    const sx = start[0] - x0, sy = start[1] - y0, zx = ziel[0] - x0, zy = ziel[1] - y0;
    const winkel = Math.atan2(zy - sy, zx - sx), s = 18;
    const spitze = [[zx, zy],
      [zx - s * Math.cos(winkel - 0.5), zy - s * Math.sin(winkel - 0.5)],
      [zx - s * Math.cos(winkel + 0.5), zy - s * Math.sin(winkel + 0.5)]];
    const ende = [zx - 12 * Math.cos(winkel), zy - 12 * Math.sin(winkel)];
    svg.innerHTML = `
      <line x1="${sx}" y1="${sy}" x2="${ende[0]}" y2="${ende[1]}" stroke="#fff" stroke-width="10" stroke-linecap="round"/>
      <line x1="${sx}" y1="${sy}" x2="${ende[0]}" y2="${ende[1]}" stroke="${farbe}" stroke-width="6" stroke-linecap="round"/>
      <polygon points="${spitze.map(p => p.join(",")).join(" ")}" fill="${farbe}" stroke="#fff" stroke-width="2"/>`;
    ebene.appendChild(svg);
    if (m.nummer) nummer(m.nummer, start[0], start[1]);
  }
}
