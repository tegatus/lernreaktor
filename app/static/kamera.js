// Kamera-Upload: Seiten einzeln fotografieren, sammeln, ordnen und als eine Abgabe hochladen.
// Fotos werden im Browser verkleinert (schneller über mobile Daten); der Server normalisiert danach wie gewohnt.
(function () {
  var box = document.getElementById('kamera');
  if (!box) return;
  var eingabe = document.getElementById('kamera-eingabe');
  var liste = document.getElementById('kamera-seiten');
  var senden = document.getElementById('kamera-senden');
  var status = document.getElementById('kamera-status');
  var MAX_KANTE = 2400;
  var seiten = [];  // {blob, url}

  function verkleinern(datei) {
    return new Promise(function (ok, fehler) {
      var bild = new Image(), url = URL.createObjectURL(datei);
      bild.onload = function () {
        var f = Math.min(1, MAX_KANTE / Math.max(bild.naturalWidth, bild.naturalHeight));
        var c = document.createElement('canvas');
        c.width = Math.round(bild.naturalWidth * f); c.height = Math.round(bild.naturalHeight * f);
        c.getContext('2d').drawImage(bild, 0, 0, c.width, c.height);  // Browser wenden die EXIF-Drehung an
        URL.revokeObjectURL(url);
        c.toBlob(function (b) { b ? ok(b) : fehler(new Error('Bild konnte nicht verarbeitet werden.')); }, 'image/jpeg', 0.85);
      };
      bild.onerror = function () { URL.revokeObjectURL(url); ok(datei); };  // unbekanntes Format: Original senden
      bild.src = url;
    });
  }

  function knopf(text, titel, aktion) {
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'symbolknopf klein'; b.textContent = text;
    b.title = titel; b.setAttribute('aria-label', titel);
    b.addEventListener('click', aktion);
    return b;
  }

  function zeichnen() {
    liste.innerHTML = '';
    seiten.forEach(function (s, i) {
      var li = document.createElement('li');
      var img = document.createElement('img');
      img.src = s.url; img.alt = 'Seite ' + (i + 1);
      var label = document.createElement('span');
      label.textContent = 'Seite ' + (i + 1);
      var aktionen = document.createElement('span');
      aktionen.className = 'kamera-aktionen';
      if (i > 0) aktionen.appendChild(knopf('↑', 'Seite ' + (i + 1) + ' nach oben', function () {
        seiten.splice(i - 1, 0, seiten.splice(i, 1)[0]); zeichnen();
      }));
      if (i < seiten.length - 1) aktionen.appendChild(knopf('↓', 'Seite ' + (i + 1) + ' nach unten', function () {
        seiten.splice(i + 1, 0, seiten.splice(i, 1)[0]); zeichnen();
      }));
      aktionen.appendChild(knopf('✕', 'Seite ' + (i + 1) + ' entfernen', function () {
        URL.revokeObjectURL(s.url); seiten.splice(i, 1); zeichnen();
      }));
      li.append(img, label, aktionen);
      liste.appendChild(li);
    });
    senden.hidden = seiten.length === 0;
    senden.textContent = seiten.length === 1 ? '1 Seite abgeben' : seiten.length + ' Seiten abgeben';
    box.querySelector('.kamera-knopf').firstChild.textContent =
      seiten.length ? 'Nächste Seite fotografieren' : 'Seite fotografieren';
  }

  eingabe.addEventListener('change', function () {
    var datei = eingabe.files[0];
    eingabe.value = '';
    if (!datei) return;
    status.textContent = 'Foto wird vorbereitet …';
    verkleinern(datei).then(function (blob) {
      seiten.push({ blob: blob, url: URL.createObjectURL(blob) });
      status.textContent = '';
      zeichnen();
    }).catch(function (e) { status.textContent = e.message; });
  });

  senden.addEventListener('click', function () {
    var fd = new FormData();
    seiten.forEach(function (s, i) { fd.append('dateien', s.blob, 'seite-' + (i + 1) + '.jpg'); });
    senden.disabled = true;
    status.textContent = 'Wird hochgeladen …';
    fetch(box.dataset.url, {
      method: 'POST', body: fd, headers: { 'X-CSRF-Token': window.CSRF, 'X-Requested-With': 'fetch' }
    }).then(function (r) {
      return r.json().catch(function () { return { ok: false, meldung: 'Hochladen fehlgeschlagen (' + r.status + ').' }; });
    }).then(function (d) {
      if (d.ok) { location.href = d.ziel; return; }
      status.textContent = d.meldung; senden.disabled = false;
    }).catch(function () {
      status.textContent = 'Keine Verbindung. Die Fotos bleiben hier – bitte erneut versuchen.';
      senden.disabled = false;
    });
  });
})();
