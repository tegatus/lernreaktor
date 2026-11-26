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
    const alleAn = boxes.every(c => c.checked && !istAuto(c));
    boxes.forEach(c => { c.checked = !alleAn; setzeAuto(c, false); });
    if (boxes.some(c => c.dataset.bivo !== undefined)) bivoAbgleichen(box, boxes, beidseitig);
    if (beidseitig && boxes.some(c => c.name === 'bivo')) lernzieleAbgleichen(box, boxes);
    box.dispatchEvent(new Event('change', { bubbles: true }));
  }));

  // Lernziele (data-bivo) kreuzen ihre BiVo-Kompetenzziele mit an bzw. ab (Aufgabenformular: nur diese Richtung)
  const beidseitig = box.dataset.verknuepfen === 'beidseitig';
  const lzBoxen = [...box.querySelectorAll('input[name=lernziel][data-bivo]')];
  if (lzBoxen.length) {
    lzBoxen.forEach(c => c.addEventListener('change', () => { direkt(c); bivoAbgleichen(box, [c], beidseitig); }));
    bivoAbgleichen(box, lzBoxen.filter(c => c.checked), beidseitig);  // Vorauswahl (z. B. «+ Aufgabe» beim Lernziel)
    // Übungsblatt/Prüfung: ein Kompetenzziel kreuzt auch die Lernziele an, die darauf beruhen (ohne Kettenreaktion).
    // Mitangekreuzte Partner sind nur Anzeige (data-auto): Sie zählen weder für Trefferzahl noch Suche/Prüfung.
    if (beidseitig) box.querySelectorAll('input[name=bivo]').forEach(c =>
      c.addEventListener('change', () => { direkt(c); lernzieleAbgleichen(box, [c]); }));
  }
});

const istAuto = c => c.dataset.auto !== undefined;

function setzeAuto(c, an) {
  // Ein Feld mit form="nicht-senden" gehört zu keinem Formular und wird weder gezählt noch abgeschickt
  if (an) { c.dataset.auto = ''; c.setAttribute('form', 'nicht-senden'); }
  else { delete c.dataset.auto; c.removeAttribute('form'); }
}

// Klick auf ein mitangekreuztes Feld macht es zur eigenen Wahl (bleibt angekreuzt)
function direkt(c) {
  if (istAuto(c) && !c.checked) c.checked = true;
  setzeAuto(c, false);
}

function mitAnkreuzen(ziel, an, nochGetragen, auto) {
  if (an) {
    if (!ziel.checked) { ziel.checked = true; if (auto) setzeAuto(ziel, true); }
  } else if (!nochGetragen && (!auto || istAuto(ziel))) {
    ziel.checked = false;
    setzeAuto(ziel, false);
  }
}

function lernzieleAbgleichen(box, codesGeaendert) {
  const lzCodes = lz => lz.dataset.bivo.split(' ').filter(Boolean);
  const gewaehlt = new Set([...box.querySelectorAll('input[name=bivo]:checked')].map(c => c.value));
  codesGeaendert.forEach(code => box.querySelectorAll('input[name=lernziel][data-bivo]').forEach(lz => {
    if (lzCodes(lz).includes(code.value))
      mitAnkreuzen(lz, code.checked, lzCodes(lz).some(c => c !== code.value && gewaehlt.has(c) &&
        !istAuto(box.querySelector(`input[name=bivo][value="${c}"]`))), true);
  }));
}

function bivoAbgleichen(box, geaendert, auto) {
  const codes = c => c.dataset.bivo.split(' ').filter(Boolean);
  const nochGewaehlt = new Set([...box.querySelectorAll('input[name=lernziel][data-bivo]:checked')]
    .filter(c => !istAuto(c)).flatMap(codes));
  geaendert.forEach(lz => codes(lz).forEach(code => {
    const ziel = box.querySelector(`input[name=bivo][value="${code}"]`);
    if (ziel) mitAnkreuzen(ziel, lz.checked, nochGewaehlt.has(code), auto);
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
