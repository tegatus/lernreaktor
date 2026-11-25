// Editor für Aufgaben und Theoriekapitel: Werkzeugleiste, Formel-Assistent, Bilder einfügen/ziehen, Live-Vorschau
(() => {
  const form = document.getElementById('aufgabe-form') || document.getElementById('kapitel-form');
  if (!form) return;
  const feld = name => form.querySelector(`textarea[name=${name}]`);

  // ---------------------------------------------------------- Text-Hilfsfunktionen
  function umschliessen(ta, vor, nach, platzhalter) {
    const a = ta.selectionStart, e = ta.selectionEnd;
    const auswahl = ta.value.slice(a, e) || platzhalter;
    ta.setRangeText(vor + auswahl + nach, a, e, 'end');
    if (a === e) { ta.selectionStart = a + vor.length; ta.selectionEnd = ta.selectionStart + auswahl.length; }
    geaendert(ta);
  }
  function zeilenEinfuegen(ta, text) {           // als eigene Zeile(n) an der Cursorposition
    const pos = ta.selectionStart ?? ta.value.length;
    const vor = ta.value.slice(0, pos), nach = ta.value.slice(pos);
    const einf = (vor && !vor.endsWith('\n') ? '\n' : '') + text + (nach.startsWith('\n') ? '' : '\n');
    ta.setRangeText(einf, pos, pos, 'end');
    geaendert(ta);
  }
  function jedeZeile(ta, fn) {                   // Präfix für alle markierten Zeilen
    let a = ta.selectionStart, e = ta.selectionEnd;
    a = ta.value.lastIndexOf('\n', a - 1) + 1;
    const block = ta.value.slice(a, e) || '';
    const zeilen = (block || 'Text').split('\n').map(fn);
    ta.setRangeText(zeilen.join('\n'), a, Math.max(a, e), 'end');
    geaendert(ta);
  }
  function geaendert(ta) { ta.focus(); ta.dispatchEvent(new Event('input', { bubbles: true })); }

  // Chemische Formel: H2SO4 → H_{2}SO_{4}, Ca2+ → Ca^{2+}, NH4+ → NH_{4}^{+}, SO42- → SO_{4}^{2-}, 10^6 → 10^{6}
  // Ladung: bei zwei Ziffern vor dem Vorzeichen ist die letzte die Ladung (SO42-, PO43-);
  // bei einer Ziffer nur, wenn davor ein einzelnes Element steht (Ca2+, Fe3+, S2-), sonst Index (NH4+).
  function formel(s) {
    return s.split(/(\s+)/).map(wort => {
      if (/^\s*$/.test(wort)) return wort;
      let ladung = '';
      const m = wort.match(/^(.*[A-Za-z)\]])(\d*)([+\-−])$/);
      if (m) {
        let [, rumpf, ziffern, vz] = m;
        if (ziffern.length >= 2) { rumpf += ziffern.slice(0, -1); ladung = ziffern.slice(-1) + vz; }
        else if (ziffern.length === 1 && /^[A-Z][a-z]?$/.test(rumpf)) ladung = ziffern + vz;
        else { rumpf += ziffern; ladung = vz; }
        wort = rumpf; ladung = `^{${ladung}}`;
      }
      wort = wort.replace(/\^(\d+)/g, '^{$1}').replace(/([A-Za-z)\]])(\d+)/g, '$1_{$2}');
      return wort + ladung;
    }).join('');
  }
  window._formel = formel;  // für Tests

  // ---------------------------------------------------------- Werkzeugleisten
  form.querySelectorAll('.editor-leiste').forEach(leiste => {
    const ta = feld(leiste.dataset.ziel);
    leiste.addEventListener('click', ev => {
      const b = ev.target.closest('button');
      if (!b) return;
      if (b.dataset.zeichen) {
        ta.setRangeText(b.dataset.zeichen, ta.selectionStart, ta.selectionEnd, 'end');
        b.closest('details').open = false;
        return geaendert(ta);
      }
      switch (b.dataset.aktion) {
        case 'fett': return umschliessen(ta, '**', '**', 'fett');
        case 'kursiv': return umschliessen(ta, '*', '*', 'kursiv');
        case 'tief': return umschliessen(ta, '_{', '}', '2');
        case 'hoch': return umschliessen(ta, '^{', '}', '6');
        case 'formel': {
          const a = ta.selectionStart, e = ta.selectionEnd;
          if (a === e) { alert('Zuerst die Formel markieren, z. B. H2SO4 oder Ca2+.'); return; }
          ta.setRangeText(formel(ta.value.slice(a, e)), a, e, 'select');
          return geaendert(ta);
        }
        case 'liste': return jedeZeile(ta, z => z.startsWith('- ') ? z : '- ' + z);
        case 'teil': { let i = 0; return jedeZeile(ta, z => /^[a-z]\)\s/.test(z) ? z : `${String.fromCharCode(97 + i++)}) ${z}`); }
        case 'titel': return jedeZeile(ta, z => z.startsWith('## ') ? z : '## ' + z);
        case 'tabelle': return zeilenEinfuegen(ta, '| Probe | Wert | Einheit |\n| A | | |\n| B | | |');
        case 'bild': zielFeld = ta; return dateiwahl.click();
      }
    });
  });
  form.querySelectorAll('textarea.ablage').forEach(ta => ta.addEventListener('keydown', e => {
    if (!(e.ctrlKey || e.metaKey)) return;
    if (e.key === 'b') { e.preventDefault(); umschliessen(ta, '**', '**', 'fett'); }
    if (e.key === 'i') { e.preventDefault(); umschliessen(ta, '*', '*', 'kursiv'); }
  }));

  // Marker vorhandener Bilder einfügen / kopieren
  form.addEventListener('click', ev => {
    const b = ev.target.closest('.einfuegen');
    if (b) zeilenEinfuegen(feld(b.dataset.ziel), b.dataset.marker);
    const c = ev.target.closest('code.marker');
    if (c && !c.dataset.kopiert) {
      const m = c.textContent;
      navigator.clipboard?.writeText(m);
      c.dataset.kopiert = 1; c.textContent = 'kopiert ✓';
      setTimeout(() => { c.textContent = m; delete c.dataset.kopiert; }, 1200);
    }
  });

  // ---------------------------------------------------------- Neue Bilder (einfügen, ziehen, wählen)
  const eingabe = document.getElementById('bilder-neu');
  const dateiwahl = document.createElement('input');
  dateiwahl.type = 'file'; dateiwahl.accept = 'image/*,application/pdf'; dateiwahl.multiple = true;
  let zielFeld = null;                // Textfeld, in das der Platzhalter gesetzt wird (null = nur anhängen)
  const maxNr = +form.dataset.maxNr || 0;
  const neu = [];                     // [{datei, url}] – Reihenfolge = spätere Bildnummer (maxNr + i + 1)
  const nrVon = i => maxNr + i + 1;

  function dateienSynchronisieren() {
    const dt = new DataTransfer();
    neu.forEach(n => dt.items.add(n.datei));
    eingabe.files = dt.files;
    zeigeNeue();
    vorschauSpaeter();
  }
  function hinzufuegen(dateien, ta) {
    for (const d of dateien) {
      if (!(d.type.startsWith('image/') || d.type === 'application/pdf')) continue;
      neu.push({ datei: d, url: d.type.startsWith('image/') ? URL.createObjectURL(d) : null });
      if (ta) zeilenEinfuegen(ta, `[[bild:${nrVon(neu.length - 1)}]]`);
    }
    dateienSynchronisieren();
  }
  function entfernen(i) {
    const nr = nrVon(i);
    neu.splice(i, 1);
    // Platzhalter des entfernten Bildes löschen, spätere Nummern nachrücken
    form.querySelectorAll('textarea.ablage').forEach(ta => {
      ta.value = ta.value
        .replace(new RegExp(`[ \\t]*\\[\\[bild:${nr}(\\|\\w+)?\\]\\][ \\t]*\\n?`, 'g'), '')
        .replace(/\[\[bild:(\d+)((?:\|\w+)?)\]\]/g, (m, n, g) => +n > nr ? `[[bild:${+n - 1}${g}]]` : m);
    });
    dateienSynchronisieren();
  }
  function zeigeNeue() {
    const liste = document.getElementById('neue-bilder');
    liste.innerHTML = '';
    neu.forEach((n, i) => {
      const karte = document.createElement('div');
      karte.className = 'bildkarte neu';
      karte.innerHTML = `${n.url ? `<img src="${n.url}" alt="">` : '<div class="pdf-symbol">PDF</div>'}
        <div><div class="aktionen" style="margin:0 0 .3rem"><strong>Bild ${nrVon(i)}</strong> <span class="badge">neu</span>
          <code class="marker">[[bild:${nrVon(i)}]]</code></div>
          <div class="aktionen" style="margin:0">
            <button type="button" class="link einfuegen" data-marker="[[bild:${nrVon(i)}]]" data-ziel="text">in Aufgabe einfügen</button>
            ${feld('loesung') ? `<button type="button" class="link einfuegen" data-marker="[[bild:${nrVon(i)}]]" data-ziel="loesung">in Lösung einfügen</button>` : ''}
            <button type="button" class="link entfernen">entfernen</button></div></div>`;
      karte.querySelector('.entfernen').addEventListener('click', () => entfernen(i));
      liste.appendChild(karte);
    });
  }
  dateiwahl.addEventListener('change', () => { hinzufuegen(dateiwahl.files, zielFeld); dateiwahl.value = ''; zielFeld = null; });
  document.getElementById('bild-waehlen').addEventListener('click', () => { zielFeld = null; dateiwahl.click(); });

  form.querySelectorAll('textarea.ablage').forEach(ta => ta.addEventListener('paste', e => {
    const dateien = [...(e.clipboardData?.files || [])];
    if (dateien.length) { e.preventDefault(); hinzufuegen(dateien, ta); }
  }));
  form.querySelectorAll('.ablage').forEach(el => {
    el.addEventListener('dragover', e => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); el.classList.add('ziehen'); } });
    el.addEventListener('dragleave', () => el.classList.remove('ziehen'));
    el.addEventListener('drop', e => {
      if (!e.dataTransfer.files.length) return;
      e.preventDefault(); el.classList.remove('ziehen');
      hinzufuegen(e.dataTransfer.files, el.tagName === 'TEXTAREA' ? el : null);
    });
  });

  // ---------------------------------------------------------- Live-Vorschau
  const status = form.querySelector('.vorschau-status');
  const ziele = { aufgabe: document.getElementById('vorschau-aufgabe'), loesung: document.getElementById('vorschau-loesung') };
  form.querySelectorAll('.live-vorschau .tab').forEach(t => t.addEventListener('click', () => {
    form.querySelectorAll('.live-vorschau .tab').forEach(x => x.classList.toggle('aktiv', x === t));
    Object.entries(ziele).forEach(([k, el]) => { if (el) el.style.display = k === t.dataset.ansicht ? '' : 'none'; });
  }));
  let timer, laufend = 0;
  function vorschauSpaeter() { clearTimeout(timer); timer = setTimeout(vorschau, 350); }
  async function vorschau() {
    const nr = ++laufend;
    status.textContent = 'aktualisiere …';
    try {
      const daten = { aufgabe_id: form.dataset.aufgabeId, text: feld('text').value, loesung: feld('loesung')?.value ?? '',
                      ...(window.aufgabeTypDaten ? window.aufgabeTypDaten() : {}) };
      const r = await fetch(form.dataset.vorschauUrl, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': window.CSRF }, body: JSON.stringify(daten) });
      if (!r.ok) throw new Error(r.status);
      const res = await r.json();
      if (nr !== laufend) return;     // veraltete Antwort
      ziele.aufgabe.innerHTML = res.aufgabe || '<p class="muted">(leer)</p>';
      if (ziele.loesung) ziele.loesung.innerHTML = res.loesung || '<p class="muted">(keine Musterlösung)</p>';
      // Platzhalter für noch nicht gespeicherte Bilder durch die lokale Datei ersetzen
      form.querySelectorAll('.live-vorschau figure.platzhalter').forEach(f => {
        const n = neu[+f.dataset.nr - maxNr - 1];
        if (n && n.url) { f.classList.remove('platzhalter'); f.innerHTML = `<img src="${n.url}" alt="Bild ${f.dataset.nr}">`; }
        else if (!n) f.querySelector('div').textContent = `Bild ${f.dataset.nr} fehlt`;
      });
      status.textContent = res.hinweis || '';
    } catch (e) { status.textContent = 'Vorschau nicht verfügbar'; }
  }
  window.vorschauAktualisieren = vorschauSpaeter;
  form.addEventListener('input', e => { if (e.target.matches('textarea, [data-vorschau]')) vorschauSpaeter(); });
  vorschau();
})();
