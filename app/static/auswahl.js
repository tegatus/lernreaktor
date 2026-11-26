// Tabs, "alle"-Knöpfe und Live-Trefferzahl für das Auswahl-Widget
document.querySelectorAll('.auswahl').forEach(box => {
  box.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => {
    box.querySelectorAll('.tab, .tabpanel').forEach(e => e.classList.remove('aktiv'));
    tab.classList.add('aktiv');
    box.querySelector('#' + tab.dataset.tab).classList.add('aktiv');
  }));
  box.querySelectorAll('button.alle').forEach(b => b.addEventListener('click', ev => {
    ev.preventDefault();
    const boxes = [...document.getElementById(b.dataset.scope).querySelectorAll('input[type=checkbox]')];
    const alleAn = boxes.every(c => c.checked);
    boxes.forEach(c => { c.checked = !alleAn; });
    if (boxes.some(c => c.dataset.bivo !== undefined)) bivoAbgleichen(box, boxes);
    if (beidseitig && boxes.some(c => c.name === 'bivo')) lernzieleAbgleichen(box, boxes);
    box.dispatchEvent(new Event('change', { bubbles: true }));
  }));

  // Lernziele (data-bivo) kreuzen ihre BiVo-Kompetenzziele mit an bzw. ab (Aufgabenformular: nur diese Richtung)
  const beidseitig = box.dataset.verknuepfen === 'beidseitig';
  const lzBoxen = [...box.querySelectorAll('input[name=lernziel][data-bivo]')];
  if (lzBoxen.length) {
    lzBoxen.forEach(c => c.addEventListener('change', () => bivoAbgleichen(box, [c])));
    bivoAbgleichen(box, lzBoxen.filter(c => c.checked));  // Vorauswahl (z. B. «+ Aufgabe» beim Lernziel)
    // Übungsblatt/Prüfung: ein Kompetenzziel kreuzt auch die Lernziele an, die darauf beruhen (ohne Kettenreaktion)
    if (beidseitig) box.querySelectorAll('input[name=bivo]').forEach(c =>
      c.addEventListener('change', () => lernzieleAbgleichen(box, [c])));
  }
});

function lernzieleAbgleichen(box, codesGeaendert) {
  codesGeaendert.forEach(code => box.querySelectorAll('input[name=lernziel][data-bivo]').forEach(lz => {
    if (lz.dataset.bivo.split(' ').includes(code.value)) lz.checked = code.checked;
  }));
}

function bivoAbgleichen(box, geaendert) {
  const codes = c => c.dataset.bivo.split(' ').filter(Boolean);
  const nochGewaehlt = new Set([...box.querySelectorAll('input[name=lernziel][data-bivo]:checked')].flatMap(codes));
  geaendert.forEach(lz => codes(lz).forEach(code => {
    const ziel = box.querySelector(`input[name=bivo][value="${code}"]`);
    if (!ziel) return;
    if (lz.checked) ziel.checked = true;
    else if (!nochGewaehlt.has(code)) ziel.checked = false;
  }));
}

const ziel = document.querySelector('[data-trefferzahl]');
if (ziel) {
  const form = ziel.closest('form');
  let timer;
  const update = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const p = new URLSearchParams();
      for (const [k, v] of new FormData(form)) if (['thema', 'lernziel', 'bivo', 'k'].includes(k)) p.append(k, v);
      if (ziel.dataset.pruefung) p.append('pruefung', '1');
      const r = await fetch(ziel.dataset.trefferzahl + '?' + p);
      const n = (await r.json()).anzahl;
      ziel.textContent = n === 0 ? 'Keine passenden Aufgaben' : `${n} passende Aufgabe${n === 1 ? '' : 'n'} in der Datenbank`;
    }, 200);
  };
  form.addEventListener('change', update);
  update();
}
