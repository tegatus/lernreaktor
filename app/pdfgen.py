"""PDF-Erzeugung: Übungsblätter, Lösungsblätter, Prüfungen und Korrektur-Rückmeldungen.

Auszeichnung in Aufgaben- und Lösungstexten (bewusst einfach gehalten):
  Leerzeile            neuer Absatz
  - Punkt              Aufzählung
  1) Punkt / a) Punkt  nummerierte Teilaufgabe (bleibt so stehen, mit Einzug)
  | A | B |            Tabellenzeile (erste Zeile = Kopfzeile)
  **fett**  *kursiv*   Hervorhebung
  H_{2}O  10^{6}       tief-/hochgestellt
"""
import html
import io
import os
import re
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (CondPageBreak, Flowable, Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from .aufgabentypen import rendern
from .markup import RE_BILD, angehaengte_bilder, sichtbare_bilder, tabellen_abtrennen

FONT_DIR = os.path.join(os.path.dirname(__file__), "static", "fonts")
_fonts_ok = False


def _register_fonts():
    global _fonts_ok
    if _fonts_ok:
        return
    for name, datei in [("LS", "LiberationSans-Regular.ttf"), ("LS-B", "LiberationSans-Bold.ttf"),
                        ("LS-I", "LiberationSans-Italic.ttf"), ("LS-BI", "LiberationSans-BoldItalic.ttf")]:
        pdfmetrics.registerFont(TTFont(name, os.path.join(FONT_DIR, datei)))
    pdfmetrics.registerFontFamily("LS", normal="LS", bold="LS-B", italic="LS-I", boldItalic="LS-BI")
    # Ersatzschrift für Zeichen, die Liberation Sans nicht kennt (z. B. ≙ ✓ ⇌)
    pdfmetrics.registerFont(TTFont("DV", os.path.join(FONT_DIR, "DejaVuSans.ttf")))
    _GLYPHEN.update(pdfmetrics.getFont("LS").face.charToGlyph.keys())
    _fonts_ok = True


_GLYPHEN = set()


def _ersatzschrift(t):
    """Umhüllt Zeichen ohne Glyphe in der Hauptschrift mit der Ersatzschrift."""
    return "".join(c if (ord(c) in _GLYPHEN or c in "\n\t") else f'<font name="DV">{c}</font>' for c in t)


GRAU = colors.HexColor("#666666")
HELLGRAU = colors.HexColor("#c8c8c8")
AKZENT = colors.HexColor("#1f5f8b")
LOESUNG_BG = colors.HexColor("#eef6ee")

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm
CONTENT_W = PAGE_W - 2 * MARGIN - 12  # Frame hat links/rechts je 6 pt Innenabstand


def _styles():
    _register_fonts()
    base = ParagraphStyle("base", fontName="LS", fontSize=10.5, leading=14.5)
    return {
        "base": base,
        "titel": ParagraphStyle("titel", parent=base, fontName="LS-B", fontSize=17, leading=21, textColor=AKZENT,
                                spaceAfter=4),
        "untertitel": ParagraphStyle("ut", parent=base, fontSize=9, leading=12, textColor=GRAU),
        "aufg_kopf": ParagraphStyle("ak", parent=base, fontName="LS-B", fontSize=11.5, leading=15),
        "aufg_punkte": ParagraphStyle("ap", parent=base, fontName="LS-B", fontSize=11, alignment=TA_RIGHT),
        "meta": ParagraphStyle("meta", parent=base, fontSize=8, leading=10, textColor=GRAU),
        "text": ParagraphStyle("text", parent=base, spaceAfter=4),
        "liste": ParagraphStyle("liste", parent=base, leftIndent=14, bulletIndent=3, spaceAfter=1),
        "teil": ParagraphStyle("teil", parent=base, leftIndent=18, firstLineIndent=-18, spaceAfter=2),
        "zelle": ParagraphStyle("zelle", parent=base, fontSize=9.5, leading=12),
        "zelle_b": ParagraphStyle("zelleb", parent=base, fontName="LS-B", fontSize=9.5, leading=12),
        "klein": ParagraphStyle("klein", parent=base, fontSize=9, leading=12),
        "bildtext": ParagraphStyle("bildtext", parent=base, fontName="LS-I", fontSize=8.5, leading=11,
                                   textColor=GRAU, spaceBefore=2),
    }


# ---------------------------------------------------------------- Auszeichnung → Flowables

def inline(text):
    _register_fonts()
    t = _ersatzschrift(html.escape(text, quote=False))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"_\{(.+?)\}", r"<sub>\1</sub>", t)
    t = re.sub(r"\^\{(.+?)\}", r"<super>\1</super>", t)
    return t


def markup_flowables(text, st, width=CONTENT_W, bilder=None, bild_pfad=None):
    """Wandelt die einfache Auszeichnung in eine Liste von Flowables um.

    bilder: {nr: AufgabeBild} der in diesem Kontext sichtbaren Bilder; bild_pfad: AufgabeBild -> Dateipfad.
    Marker [[bild:NR]] / [[bild:NR|halb]] werden durch die Grafik ersetzt; mehrere Marker auf einer
    Zeile stehen nebeneinander.
    """
    bilder = bilder or {}
    out = []
    blocks = re.split(r"\n\s*\n", tabellen_abtrennen(text).strip())
    for block in blocks:
        lines = [l.rstrip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        if all(l.lstrip().startswith("|") for l in lines):
            out.append(_tabelle(lines, st, width))
            out.append(Spacer(1, 4))
            continue
        absatz = []

        def flush():
            if absatz:
                out.append(Paragraph(inline(" ".join(absatz)), st["text"]))
                absatz.clear()

        for l in lines:
            s = l.strip()
            treffer = [(int(m[1]), (m[2] or "").lower() or None) for m in RE_BILD.finditer(s)]
            if treffer:
                s = RE_BILD.sub("", s).strip()
                if s:
                    absatz.append(s)
                flush()
                zeile = _bildzeile([(bilder[nr], g) for nr, g in treffer if nr in bilder], st, width, bild_pfad)
                if zeile:
                    out += [Spacer(1, 3), zeile, Spacer(1, 5)]
                continue
            if re.match(r"^[-•]\s+", s):
                flush()
                out.append(Paragraph(inline(re.sub(r"^[-•]\s+", "", s)), st["liste"], bulletText="•"))
            elif re.match(r"^(\d+|[a-z])\)\s+", s) or s[:1] in "☐☑":
                flush()
                out.append(Paragraph(inline(s), st["teil"]))
            elif s.startswith("|"):
                flush()
                out.append(_tabelle([s], st, width))
            else:
                absatz.append(s)
        flush()
    return out


def _tabelle(lines, st, width):
    rows = []
    for l in lines:
        zellen = [z.strip() for z in l.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", z) for z in zellen if z):  # Markdown-Trennzeile ignorieren
            continue
        rows.append(zellen)
    ncol = max(len(r) for r in rows)
    data = [[Paragraph(inline(z), st["zelle_b"] if i == 0 else st["zelle"]) for z in r + [""] * (ncol - len(r))]
            for i, r in enumerate(rows)]
    # Spaltenbreite nach Inhalt (längster Eintrag, begrenzt), damit lange Beschreibungen Platz bekommen
    gewichte = [min(max([len(re.sub(r"[*_^{}]", "", r[i])) if i < len(r) else 0 for r in rows] + [2]), 45) + 2
                for i in range(ncol)]
    gesamt = min(width, sum(g * 0.21 * cm for g in gewichte))
    t = Table(data, colWidths=[gesamt * g / sum(gewichte) for g in gewichte], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


class Antwortfeld(Flowable):
    """Leerraum zum Beantworten: Linien, Karo oder leeres Feld."""

    def __init__(self, hoehe_cm, art="linien", width=CONTENT_W):
        super().__init__()
        self.h = max(0.0, float(hoehe_cm or 0)) * cm
        self.art = art
        self.w = width

    def wrap(self, aw, ah):
        return self.w, self.h + 4

    def draw(self):
        c = self.canv
        w, h = self.w, self.h
        if h <= 0 or self.art == "keins":
            return
        c.saveState()
        if self.art == "karo":
            step = 0.5 * cm
            c.setStrokeColor(colors.HexColor("#d9d9d9"))
            c.setLineWidth(0.35)
            x = 0
            while x <= w + 0.1:
                c.line(x, 0, x, h)
                x += step
            y = h
            while y >= -0.1:
                c.line(0, y, w, y)
                y -= step
        elif self.art == "linien":
            step = 0.85 * cm
            c.setStrokeColor(HELLGRAU)
            c.setLineWidth(0.5)
            y = h - step
            while y >= 0:
                c.line(0, y, w, y)
                y -= step
        else:  # leer
            c.setStrokeColor(HELLGRAU)
            c.setLineWidth(0.6)
            c.rect(0, 0, w, h)
        c.restoreState()


def _bild_flowable(pfad, max_w=CONTENT_W, max_h=9 * cm):
    if not pfad or not os.path.exists(pfad):
        return None
    from PIL import Image as PILImage
    with PILImage.open(pfad) as im:
        w, h = im.size
    f = min(max_w / w, max_h / h)
    img = Image(pfad, width=w * f, height=h * f)
    img.hAlign = "LEFT"
    return img


BILD_MAX_H = 11 * cm
BILD_ABSTAND = 8


def _bildzeile(eintraege, st, width, bild_pfad, max_h=BILD_MAX_H):
    """Eine oder mehrere Grafiken nebeneinander. eintraege: [(AufgabeBild, groesse_override|None)]."""
    from PIL import Image as PILImage
    from .models import BILDGROESSEN
    elemente = []
    for b, groesse in eintraege:
        pfad = bild_pfad(b) if bild_pfad else None
        if not pfad or not os.path.exists(pfad):
            continue
        with PILImage.open(pfad) as im:
            w, h = im.size
        anteil = BILDGROESSEN.get(groesse or b.groesse, BILDGROESSEN["voll"])[1]
        elemente.append((b, pfad, w, h, anteil))
    if not elemente:
        return None
    platz = width - BILD_ABSTAND * (len(elemente) - 1)
    summe = sum(e[4] for e in elemente)
    faktor = min(1.0, platz / (summe * width)) if summe else 1.0
    zellen, breiten = [], []
    for i, (b, pfad, w, h, anteil) in enumerate(elemente):
        ziel_w = anteil * width * faktor
        f = min(ziel_w / w, max_h / h)
        img = Image(pfad, width=w * f, height=h * f)
        inhalt = [img]
        if b.beschriftung:
            inhalt.append(Paragraph(inline(b.beschriftung), st["bildtext"]))
        zellen.append(inhalt)
        breiten.append(ziel_w + (BILD_ABSTAND if i < len(elemente) - 1 else 0))
    t = Table([zellen], colWidths=breiten, hAlign="LEFT")
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                           ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    return t


def _angehaengt(liste, st, width, bild_pfad):
    out = []
    for b in liste:
        z = _bildzeile([(b, None)], st, width, bild_pfad)
        if z:
            out += [Spacer(1, 4), z]
    return out


def _punkte_str(p):
    return f"{p:g} P." if p is not None else ""


# ---------------------------------------------------------------- Seitenrahmen

def _seitenrahmen_factory(kopf_links, kopf_rechts):
    class Rahmen(rl_canvas.Canvas):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._seiten = []

        def showPage(self):
            self._seiten.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            n = len(self._seiten)
            for state in self._seiten:
                self.__dict__.update(state)
                self._zeichne(n)
                super().showPage()
            super().save()

        def _zeichne(self, n):
            _register_fonts()
            self.saveState()
            self.setFont("LS", 8)
            self.setFillColor(GRAU)
            self.drawString(MARGIN, PAGE_H - 1.2 * cm, kopf_links)
            self.drawRightString(PAGE_W - MARGIN, PAGE_H - 1.2 * cm, kopf_rechts)
            self.setStrokeColor(HELLGRAU)
            self.line(MARGIN, PAGE_H - 1.35 * cm, PAGE_W - MARGIN, PAGE_H - 1.35 * cm)
            self.drawRightString(PAGE_W - MARGIN, 1.1 * cm, f"Seite {self._pageNumber} / {n}")
            self.drawString(MARGIN, 1.1 * cm, kopf_rechts)
            self.restoreState()

    return Rahmen


class _Doc(SimpleDocTemplate):
    """Entfernt Abstände am Dokumentende (sonst entsteht ggf. eine leere letzte Seite)."""

    def build(self, story, **kw):
        while story and isinstance(story[-1], (Spacer, CondPageBreak)):
            story.pop()
        return super().build(story, **kw)


def _doc(buf, titel):
    return _Doc(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                             topMargin=1.8 * cm, bottomMargin=1.7 * cm, title=titel, author="LernReaktor")


def _kopfblock(st, titel, felder, untertitel=None):
    """Titel + Tabelle mit Name/Datum/Punkte usw. (felder: Liste von (Label, Wert))."""
    out = [Paragraph(html.escape(titel), st["titel"])]
    if untertitel:
        out.append(Paragraph(untertitel, st["untertitel"]))
    out.append(Spacer(1, 6))
    data, row = [], []
    for label, wert in felder:
        row += [Paragraph(f"<b>{html.escape(label)}</b>", st["klein"]),
                Paragraph(html.escape(wert or ""), st["klein"])]
        if len(row) == 4:
            data.append(row)
            row = []
    if row:
        data.append(row + [""] * (4 - len(row)))
    t = Table(data, colWidths=[2.6 * cm, 5.9 * cm, 2.6 * cm, 5.9 * cm], rowHeights=0.85 * cm)
    t.setStyle(TableStyle([
        ("LINEBELOW", (1, 0), (1, -1), 0.5, GRAU), ("LINEBELOW", (3, 0), (3, -1), 0.5, GRAU),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
    ]))
    out += [t, Spacer(1, 14)]
    return out


def _aufgaben_kopf(st, nr, aufgabe, zusatz_meta=True):
    kopf = Table([[Paragraph(f"Aufgabe {nr}&nbsp;&nbsp;<font color='#1f5f8b'>{html.escape(aufgabe.titel)}</font>",
                             st["aufg_kopf"]),
                   Paragraph(_punkte_str(aufgabe.punkte), st["aufg_punkte"])]],
                 colWidths=[CONTENT_W - 2.2 * cm, 2.2 * cm])
    kopf.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.8, AKZENT),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    out = [kopf, Spacer(1, 3)]
    if zusatz_meta:
        teile = []
        if aufgabe.k_stufe:
            teile.append(f"K{aufgabe.k_stufe}")
        if aufgabe.lernziele:
            teile.append("Lernziele: " + ", ".join(l.label for l in aufgabe.lernziele))
        elif aufgabe.leistungsziele:
            teile.append("BiVo: " + ", ".join(l.code for l in aufgabe.leistungsziele))
        if teile:
            out.append(Paragraph(html.escape(" · ".join(teile)), st["meta"]))
            out.append(Spacer(1, 3))
    return out


def _aufgaben_story(st, eintraege, bild_pfad, mit_meta=True):
    """eintraege: [(Aufgabe, seed)] – der Seed bestimmt Zufallszahlen und Reihenfolgen (siehe aufgabentypen)."""
    story = []
    for nr, (a, seed) in enumerate(eintraege, 1):
        g = rendern(a, seed)
        teile = _aufgaben_kopf(st, nr, a, mit_meta)
        teile += markup_flowables(g.text, st, CONTENT_W, sichtbare_bilder(a, "aufgabe"), bild_pfad)
        teile += _angehaengt(angehaengte_bilder(a)[0], st, CONTENT_W, bild_pfad)
        if a.antwortformat != "keins" and a.antwortraum_cm:
            teile += [Spacer(1, 6), Antwortfeld(a.antwortraum_cm, a.antwortformat)]
        # Aufgabe möglichst nicht über einen Seitenumbruch verteilen
        story.append(KeepTogether(teile))
        story.append(Spacer(1, 16))
    return story


def _loesungs_story(st, eintraege, bild_pfad):
    story = []
    for nr, (a, seed) in enumerate(eintraege, 1):
        g = rendern(a, seed)
        teile = _aufgaben_kopf(st, nr, a, True)
        teile += markup_flowables(g.text, st, CONTENT_W, sichtbare_bilder(a, "aufgabe"), bild_pfad)
        fuer_aufgabe, fuer_loesung = angehaengte_bilder(a)
        teile += _angehaengt(fuer_aufgabe, st, CONTENT_W, bild_pfad)
        lw = CONTENT_W - 0.6 * cm
        loes = markup_flowables(g.loesung or "(keine Musterlösung hinterlegt)", st, lw,
                                sichtbare_bilder(a, "loesung"), bild_pfad)
        loes += _angehaengt(fuer_loesung, st, lw, bild_pfad)
        while loes and isinstance(loes[-1], Spacer):  # kein leeres Box-Ende auf einer neuen Seite
            loes.pop()
        box = Table([[Paragraph("<b>Lösung</b>", st["klein"])]] + [[f] for f in loes], colWidths=[CONTENT_W])
        box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LOESUNG_BG),
                                 ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#7aa87a")),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 1),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        story.append(CondPageBreak(4 * cm))
        story += teile + [Spacer(1, 4), KeepTogether([box]), Spacer(1, 16)]
    return story


# ---------------------------------------------------------------- Öffentliche Funktionen

APP_NAME = "LernReaktor · Laborant/in EFZ Biologie"


def _qr(url, groesse=2.6 * cm):
    w = QrCodeWidget(url, barLevel="M")
    x1, y1, x2, y2 = w.getBounds()
    d = Drawing(groesse, groesse, transform=[groesse / (x2 - x1), 0, 0, groesse / (y2 - y1), 0, 0])
    d.add(w)
    return d


def uebungsblatt_pdf(blatt, bild_pfad, loesung=False, upload_url=None):
    """upload_url: Adresse der Upload-Seite – erscheint als QR-Code, damit das Handy direkt dorthin führt."""
    st = _styles()
    buf = io.BytesIO()
    aufgaben = [(ba.aufgabe, ba.seed) for ba in blatt.aufgaben]
    titel = ("Lösungen: " if loesung else "") + blatt.titel
    doc = _doc(buf, titel)
    lern = blatt.lernende
    felder = [("Name", lern.anzeigename), ("Klasse", lern.klasse.name if lern.klasse else ""),
              ("Datum", blatt.erstellt_am.strftime("%d.%m.%Y")),
              ("Punkte", f"_____ / {blatt.max_punkte:g}")]
    story = _kopfblock(st, titel, felder, html.escape(blatt.auswahl or ""))
    if loesung:
        story += _loesungs_story(st, aufgaben, bild_pfad)
    else:
        hinweis = Paragraph(
            "Löse die Aufgaben direkt auf diesem Blatt. Fotografiere danach jede Seite gut lesbar "
            "(gerade, ohne Schatten) und lade die Fotos in der App beim Übungsblatt "
            f"<b>{blatt.code}</b> hoch."
            + (" Am schnellsten: QR-Code mit dem Handy scannen." if upload_url else ""), st["klein"])
        if upload_url:
            t = Table([[hinweis, _qr(upload_url)]], colWidths=[CONTENT_W - 3 * cm, 3 * cm])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
            story.append(t)
        else:
            story.append(hinweis)
        story.append(Spacer(1, 12))
        story += _aufgaben_story(st, aufgaben, bild_pfad)
    doc.build(story, canvasmaker=_seitenrahmen_factory(APP_NAME, blatt.code + (" · LÖSUNG" if loesung else "")))
    return buf.getvalue()


def pruefung_pdf(pruefung, bild_pfad, loesung=False):
    st = _styles()
    buf = io.BytesIO()
    aufgaben = [(pa.aufgabe, pa.seed) for pa in pruefung.aufgaben]
    titel = ("Lösungen: " if loesung else "") + pruefung.titel
    doc = _doc(buf, titel)
    felder = [("Name", ""), ("Klasse", pruefung.klasse.name if pruefung.klasse else ""),
              ("Datum", pruefung.datum or ""), ("Punkte", f"_____ / {pruefung.max_punkte:g}"),
              ("Dauer", f"{pruefung.dauer_min} min" if pruefung.dauer_min else ""), ("Note", "")]
    story = _kopfblock(st, titel, felder)
    if pruefung.hinweise:
        story += markup_flowables(pruefung.hinweise, st) + [Spacer(1, 10)]
    if loesung:
        story += _loesungs_story(st, aufgaben, bild_pfad)
    else:
        story += _aufgaben_story(st, aufgaben, bild_pfad, mit_meta=False)
    code = f"PR-{pruefung.id:05d}"
    doc.build(story, canvasmaker=_seitenrahmen_factory(APP_NAME, code + (" · LÖSUNG" if loesung else "")))
    return buf.getvalue()


def aufgabe_vorschau_pdf(aufgabe, bild_pfad, seed=1):
    st = _styles()
    buf = io.BytesIO()
    doc = _doc(buf, aufgabe.titel)
    story = [Paragraph("Vorschau Aufgabe", st["titel"]), Spacer(1, 8)]
    story += _aufgaben_story(st, [(aufgabe, seed)], bild_pfad)
    story += [PageBreak()] + _loesungs_story(st, [(aufgabe, seed)], bild_pfad)
    doc.build(story, canvasmaker=_seitenrahmen_factory(APP_NAME, f"Aufgabe #{aufgabe.id}"))
    return buf.getvalue()


def rueckmeldung_pdf(blatt, seiten_pfade):
    """Korrigierte Seiten (Bilder mit Annotationen) + Übersicht der Punkte und Kommentare."""
    st = _styles()
    buf = io.BytesIO()
    doc = _doc(buf, f"Rückmeldung {blatt.code}")
    lern = blatt.lernende
    erreicht = blatt.erreichte_punkte
    felder = [("Name", lern.anzeigename), ("Blatt", blatt.code),
              ("Korrigiert", blatt.korrigiert_am.strftime("%d.%m.%Y") if blatt.korrigiert_am else ""),
              ("Punkte", f"{erreicht:g} / {blatt.max_punkte:g}" if erreicht is not None else "–")]
    story = _kopfblock(st, f"Rückmeldung: {blatt.titel}", felder)
    data = [[Paragraph("<b>Nr.</b>", st["zelle"]), Paragraph("<b>Aufgabe</b>", st["zelle"]),
             Paragraph("<b>Punkte</b>", st["zelle"]), Paragraph("<b>Kommentar</b>", st["zelle"])]]
    for ba in blatt.aufgaben:
        p = f"{ba.punkte_erreicht:g}" if ba.punkte_erreicht is not None else "–"
        data.append([Paragraph(str(ba.position), st["zelle"]), Paragraph(html.escape(ba.aufgabe.titel), st["zelle"]),
                     Paragraph(f"{p} / {ba.aufgabe.punkte:g}", st["zelle"]),
                     Paragraph(html.escape(ba.kommentar or "").replace("\n", "<br/>"), st["zelle"])])
    t = Table(data, colWidths=[1.1 * cm, 5.4 * cm, 2.2 * cm, CONTENT_W - 8.7 * cm], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, HELLGRAU), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee"))]))
    story.append(t)
    if blatt.gesamtkommentar:
        story += [Spacer(1, 12), Paragraph("<b>Kommentar der Lehrperson</b>", st["text"])]
        story += markup_flowables(blatt.gesamtkommentar, st)
    for pfad in seiten_pfade:
        bild = _bild_flowable(pfad, CONTENT_W, PAGE_H - 4.0 * cm)
        if bild:
            bild.hAlign = "CENTER"
            story += [PageBreak(), bild]
    doc.build(story, canvasmaker=_seitenrahmen_factory(APP_NAME, blatt.code + " · RÜCKMELDUNG"))
    return buf.getvalue()


def heute():
    return date.today().strftime("%d.%m.%Y")
