"""Die einfache Aufgaben-Auszeichnung (siehe pdfgen) als HTML für die Weboberfläche."""
import html
import re

from markupsafe import Markup

# Grafik-Marker: [[bild:2]] oder [[bild:2|halb]]
RE_BILD = re.compile(r"\[\[\s*bild\s*:\s*(\d+)\s*(?:\|\s*(\w+)\s*)?\]\]", re.I)


def referenzierte_bilder(text):
    """Nummern aller Bilder, die im Text mit [[bild:NR]] platziert sind."""
    return {int(m[1]) for m in RE_BILD.finditer(text or "")}


def sichtbare_bilder(aufgabe, kontext):
    """Bilder, die im Kontext 'aufgabe' (Aufgabenblatt) bzw. 'loesung' (Lösungsteil) gezeigt werden dürfen."""
    return {b.nr: b for b in aufgabe.bilder if kontext == "loesung" or not b.nur_loesung}


def angehaengte_bilder(aufgabe):
    """Nicht platzierte Bilder: (für Aufgabentext, für Lösung) – werden am Ende angehängt."""
    ref = referenzierte_bilder(aufgabe.text) | referenzierte_bilder(aufgabe.loesung)
    frei = [b for b in aufgabe.bilder if b.nr not in ref]
    return [b for b in frei if not b.nur_loesung], [b for b in frei if b.nur_loesung]


def bild_warnungen(aufgabe):
    """Hinweise für die Lehrperson beim Speichern einer Aufgabe."""
    nrn = {b.nr for b in aufgabe.bilder}
    w = []
    for feld, text in (("Aufgabentext", aufgabe.text), ("Lösung", aufgabe.loesung)):
        for nr in sorted(referenzierte_bilder(text) - nrn):
            w.append(f"{feld}: [[bild:{nr}]] verweist auf ein Bild, das es nicht gibt.")
    for b in aufgabe.bilder:
        if b.nur_loesung and b.nr in referenzierte_bilder(aufgabe.text):
            w.append(f"Bild {b.nr} ist «nur in der Lösung», steht aber im Aufgabentext – "
                     "auf dem Aufgabenblatt wird es weggelassen.")
    for m in RE_BILD.finditer((aufgabe.text or "") + (aufgabe.loesung or "")):
        if m[2] and m[2].lower() not in ("voll", "zweidrittel", "halb", "drittel", "viertel"):
            w.append(f"Unbekannte Grösse «{m[2]}» in {m[0]} (erlaubt: voll, zweidrittel, halb, drittel, viertel).")
    return w


def tabellen_abtrennen(text):
    """Leerzeile zwischen Tabellen- und Textzeilen einfügen, damit Tabellen eigene Blöcke bilden."""
    text = (text or "").replace("\r\n", "\n")
    text = re.sub(r"(?m)^([ \t]*[^|\s].*)\n(?=[ \t]*\|)", r"\1\n\n", text)
    return re.sub(r"(?m)^([ \t]*\|.*)\n(?=[ \t]*[^|\s])", r"\1\n\n", text)


def _inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"_\{(.+?)\}", r"<sub>\1</sub>", t)
    t = re.sub(r"\^\{(.+?)\}", r"<sup>\1</sup>", t)
    return t


def _bilder_html(treffer, bilder, bild_url):
    from .models import BILDGROESSEN
    teile = []
    for nr, groesse in treffer:
        b = bilder.get(nr)
        if not b:
            # noch nicht gespeichertes Bild (eingefügt/gezogen) – der Editor ersetzt den Platzhalter
            anteil = BILDGROESSEN.get(groesse or "", BILDGROESSEN["voll"])[1]
            teile.append(f'<figure class="platzhalter" data-nr="{nr}" style="width:{anteil * 100:.0f}%">'
                         f'<div>Bild {nr}</div></figure>')
            continue
        anteil = BILDGROESSEN.get(groesse or b.groesse, BILDGROESSEN["voll"])[1]
        cap = f"<figcaption>{html.escape(b.beschriftung)}</figcaption>" if b.beschriftung else ""
        teile.append(f'<figure style="width:{anteil * 100:.0f}%"><img src="{html.escape(bild_url(b))}" '
                     f'alt="Bild {nr}">{cap}</figure>')
    return f'<div class="bildzeile">{"".join(teile)}</div>' if teile else ""


def markup_html(text, bilder=None, bild_url=None, anhaengen=(), zwischentitel=False):
    """bilder: {nr: AufgabeBild} (sichtbare Bilder), bild_url: Funktion AufgabeBild -> URL.

    zwischentitel=True (Theorie): Zeilen mit «## Titel» werden zu Zwischentiteln."""
    bilder = bilder or {}
    out = []
    for block in re.split(r"\n\s*\n", tabellen_abtrennen(text).strip()):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        if all(l.startswith("|") for l in lines):
            rows = [[z.strip() for z in l.strip("|").split("|")] for l in lines]
            rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", z) for z in r if z)]
            body = "".join("<tr>" + "".join(f"<{'th' if i == 0 else 'td'}>{_inline(z)}</{'th' if i == 0 else 'td'}>"
                                            for z in r) + "</tr>" for i, r in enumerate(rows))
            out.append(f'<table class="mini">{body}</table>')
            continue
        teile, liste = [], []
        for l in lines:
            if zwischentitel and l.startswith("## "):
                if liste:
                    teile.append("<ul>" + "".join(liste) + "</ul>")
                    liste = []
                teile.append(f"<h3>{_inline(l[3:].strip())}</h3>")
                continue
            treffer = [(int(m[1]), (m[2] or "").lower() or None) for m in RE_BILD.finditer(l)]
            if treffer:
                l = RE_BILD.sub("", l).strip()
                if liste:
                    teile.append("<ul>" + "".join(liste) + "</ul>")
                    liste = []
                if l:
                    teile.append(_inline(l) + "<br>")
                if bild_url:
                    teile.append(_bilder_html(treffer, bilder, bild_url))
                continue
            if re.match(r"^[-•]\s+", l):
                liste.append(f"<li>{_inline(re.sub(r'^[-•]\s+', '', l))}</li>")
            else:
                if liste:
                    teile.append("<ul>" + "".join(liste) + "</ul>")
                    liste = []
                teile.append(_inline(l) + "<br>")
        if liste:
            teile.append("<ul>" + "".join(liste) + "</ul>")
        out.append("<div class=\"absatz\">" + "".join(teile).removesuffix("<br>") + "</div>")
    if anhaengen and bild_url:
        for b in anhaengen:
            out.append(_bilder_html([(b.nr, None)], {b.nr: b}, bild_url))
    return Markup("".join(out))
