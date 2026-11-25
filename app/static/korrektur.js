// Online-Korrektur: Annotationen auf hochgeladenen Seiten (Maus, Touch, Stift) + Punkte/Kommentare
(() => {
  const root = document.getElementById('korrektur');
  if (!root) return;

  let tool = 'stift';
  let farbe = '#d32f2f';
  const seiten = [];      // {id, canvas, ctx, img, items, geaendert}
  const verlauf = [];     // Undo-Stapel: {seite, item}

  // ---------------------------------------------------------- Werkzeugleiste
  const leiste = document.getElementById('werkzeuge');
  if (leiste) {
    leiste.querySelectorAll('[data-tool]').forEach(b => b.addEventListener('click', () => {
      leiste.querySelectorAll('[data-tool]').forEach(x => x.classList.remove('aktiv'));
      b.classList.add('aktiv'); tool = b.dataset.tool;
    }));
    leiste.querySelectorAll('[data-farbe]').forEach(b => b.addEventListener('click', () => {
      leiste.querySelectorAll('[data-farbe]').forEach(x => x.classList.remove('aktiv'));
      b.classList.add('aktiv'); farbe = b.dataset.farbe;
    }));
    document.getElementById('undo').addEventListener('click', undo);
  }
  document.addEventListener('keydown', e => {
    if (!leiste || e.target.matches('input, textarea')) return;
    if ((e.ctrlKey || e.metaKey) && e.key === 'z') { e.preventDefault(); undo(); return; }
    const map = { p: 'stift', m: 'marker', t: 'text', h: 'haken', x: 'kreuz', k: 'kreis' };
    const t = map[e.key.toLowerCase()];
    if (t) leiste.querySelector(`[data-tool="${t}"]`).click();
  });

  function undo() {
    const letzter = verlauf.pop();
    if (!letzter) return;
    const s = letzter.seite;
    s.items.splice(s.items.lastIndexOf(letzter.item), 1);
    s.geaendert = true;
    zeichne(s);
  }

  // ---------------------------------------------------------- Zeichnen
  const skala = s => s.canvas.width / 1000; // Strichstärken relativ zur Bildbreite

  function zeichneItem(ctx, it, k) {
    ctx.save();
    ctx.strokeStyle = ctx.fillStyle = it.farbe;
    ctx.lineCap = ctx.lineJoin = 'round';
    if (it.t === 'stift' || it.t === 'marker') {
      if (it.t === 'marker') { ctx.globalAlpha = 0.35; ctx.strokeStyle = '#ffeb3b'; ctx.lineWidth = 14 * k; }
      else ctx.lineWidth = 2.6 * k;
      ctx.beginPath();
      it.pts.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
      if (it.pts.length === 1) ctx.lineTo(it.pts[0][0] + 0.1, it.pts[0][1]);
      ctx.stroke();
    } else if (it.t === 'text') {
      ctx.font = `${Math.round(22 * k)}px sans-serif`;
      ctx.textBaseline = 'top';
      it.text.split('\n').forEach((z, i) => ctx.fillText(z, it.x, it.y + i * 26 * k));
    } else if (it.t === 'haken') {
      const g = 22 * k; ctx.lineWidth = 3.5 * k;
      ctx.beginPath(); ctx.moveTo(it.x - g * .6, it.y); ctx.lineTo(it.x - g * .1, it.y + g * .5); ctx.lineTo(it.x + g * .8, it.y - g * .6); ctx.stroke();
    } else if (it.t === 'kreuz') {
      const g = 16 * k; ctx.lineWidth = 3.5 * k;
      ctx.beginPath(); ctx.moveTo(it.x - g, it.y - g); ctx.lineTo(it.x + g, it.y + g);
      ctx.moveTo(it.x + g, it.y - g); ctx.lineTo(it.x - g, it.y + g); ctx.stroke();
    } else if (it.t === 'kreis') {
      ctx.lineWidth = 2.6 * k;
      ctx.beginPath();
      ctx.ellipse((it.x1 + it.x2) / 2, (it.y1 + it.y2) / 2, Math.abs(it.x2 - it.x1) / 2 || 1, Math.abs(it.y2 - it.y1) / 2 || 1, 0, 0, 2 * Math.PI);
      ctx.stroke();
    }
    ctx.restore();
  }

  function zeichne(s, temp) {
    const { ctx, canvas } = s;
    ctx.drawImage(s.img, 0, 0, canvas.width, canvas.height);
    const k = skala(s);
    s.items.forEach(it => zeichneItem(ctx, it, k));
    if (temp) zeichneItem(ctx, temp, k);
  }

  function punkt(s, e) {
    const r = s.canvas.getBoundingClientRect();
    return [Math.round((e.clientX - r.left) * s.canvas.width / r.width),
            Math.round((e.clientY - r.top) * s.canvas.height / r.height)];
  }

  function hinzufuegen(s, it) {
    s.items.push(it); verlauf.push({ seite: s, item: it }); s.geaendert = true; zeichne(s);
  }

  root.querySelectorAll('.seite').forEach(div => {
    const canvas = div.querySelector('canvas');
    const s = { id: +div.dataset.seite, canvas, ctx: canvas.getContext('2d'), img: new Image(), items: [], geaendert: false };
    try { s.items = JSON.parse(div.dataset.annotationen || '[]'); } catch (e) { s.items = []; }
    s.img.onload = () => { canvas.width = s.img.naturalWidth; canvas.height = s.img.naturalHeight; zeichne(s); };
    s.img.src = div.dataset.src;
    seiten.push(s);

    let aktuell = null;
    canvas.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      const [x, y] = punkt(s, e);
      if (tool === 'text') {
        const text = prompt('Text für die Anmerkung:');
        if (text && text.trim()) hinzufuegen(s, { t: 'text', x, y, text: text.trim(), farbe });
        return;
      }
      if (tool === 'haken' || tool === 'kreuz') { hinzufuegen(s, { t: tool, x, y, farbe }); return; }
      canvas.setPointerCapture(e.pointerId);
      aktuell = tool === 'kreis' ? { t: 'kreis', x1: x, y1: y, x2: x, y2: y, farbe } : { t: tool, pts: [[x, y]], farbe };
      e.preventDefault();
    });
    canvas.addEventListener('pointermove', e => {
      if (!aktuell) return;
      const [x, y] = punkt(s, e);
      if (aktuell.t === 'kreis') { aktuell.x2 = x; aktuell.y2 = y; } else aktuell.pts.push([x, y]);
      zeichne(s, aktuell);
    });
    const ende = () => { if (aktuell) { hinzufuegen(s, aktuell); aktuell = null; } };
    canvas.addEventListener('pointerup', ende);
    canvas.addEventListener('pointercancel', ende);
  });

  // ---------------------------------------------------------- Punkte & Speichern
  const liste = document.getElementById('aufgabenliste');
  const totalEl = document.getElementById('total');
  function total() {
    let sum = 0, any = false;
    liste.querySelectorAll('.punkte').forEach(inp => {
      const v = parseFloat(inp.value.replace(',', '.'));
      const max = parseFloat(inp.dataset.max);
      inp.style.borderColor = (!isNaN(v) && (v < 0 || v > max)) ? 'red' : '';
      if (!isNaN(v)) { sum += v; any = true; }
    });
    totalEl.textContent = any ? (Math.round(sum * 100) / 100) : '–';
  }
  liste.addEventListener('input', total); total();

  // Niveau: aus den Punkten vorschlagen, bis es von Hand gewählt wurde (Instruktor nur von Hand)
  const schwellen = liste.dataset.schwellen.split(',').map(Number);
  function niveauVorschlag(d) {
    const sel = d.querySelector('.niveau'), inp = d.querySelector('.punkte');
    if (sel.dataset.manuell) return;
    const v = parseFloat(inp.value.replace(',', '.')), max = parseFloat(inp.dataset.max);
    sel.value = (isNaN(v) || !max) ? '' : String(v / max < schwellen[0] ? 1 : v / max < schwellen[1] ? 2 : 3);
  }
  liste.querySelectorAll('.aufgabe').forEach(niveauVorschlag);
  liste.addEventListener('input', e => { if (e.target.classList.contains('punkte')) niveauVorschlag(e.target.closest('.aufgabe')); });
  liste.addEventListener('change', e => {
    if (e.target.classList.contains('niveau')) e.target.dataset.manuell = e.target.value ? '1' : '';
  });

  document.getElementById('loesung-anzeigen').addEventListener('change', e =>
    document.getElementById('bewertung').classList.toggle('zeige-loesung', e.target.checked));

  let ungespeichert = false;
  document.getElementById('bewertung').addEventListener('input', () => { ungespeichert = true; });
  window.addEventListener('beforeunload', e => {
    if (ungespeichert || seiten.some(s => s.geaendert)) { e.preventDefault(); e.returnValue = ''; }
  });

  async function speichern(abschliessen) {
    const meldung = document.getElementById('meldung');
    if (abschliessen) {
      const leer = [...liste.querySelectorAll('.punkte')].filter(i => i.value.trim() === '').length;
      if (leer && !confirm(`${leer} Aufgabe(n) ohne Punkte. Trotzdem abschliessen?`)) return;
    }
    meldung.textContent = 'Speichere …';
    const daten = {
      abschliessen,
      gesamtkommentar: document.getElementById('gesamtkommentar').value,
      loesung_freigeben: document.getElementById('loesung-freigeben').checked,
      aufgaben: [...liste.querySelectorAll('.aufgabe')].map(d => ({
        id: +d.dataset.id, punkte: d.querySelector('.punkte').value.trim(), kommentar: d.querySelector('.kommentar').value,
        niveau: d.querySelector('.niveau').value,
      })),
      seiten: seiten.filter(s => s.geaendert || abschliessen).map(s => {
        zeichne(s);
        return { id: s.id, annotationen: s.items, bild: s.items.length ? s.canvas.toDataURL('image/jpeg', 0.85) : null };
      }),
    };
    try {
      const r = await fetch(root.dataset.url, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': window.CSRF }, body: JSON.stringify(daten),
      });
      if (!r.ok) throw new Error(r.status);
      const res = await r.json();
      seiten.forEach(s => { s.geaendert = false; }); ungespeichert = false;
      meldung.textContent = abschliessen ? 'Korrektur abgeschlossen – die Lernenden sehen jetzt die Rückmeldung.' : 'Gespeichert.';
      if (abschliessen) setTimeout(() => location.reload(), 700);
    } catch (e) {
      meldung.textContent = 'Fehler beim Speichern (' + e.message + '). Bitte erneut versuchen.';
    }
  }
  document.getElementById('speichern').addEventListener('click', () => speichern(false));
  document.getElementById('abschliessen').addEventListener('click', () => speichern(true));
})();
