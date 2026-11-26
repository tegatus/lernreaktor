"""Importfunktionen: Kompetenzen der BiVo (Excel), konkrete Lernziele (Text/PDF), Aufgaben (JSON)."""
import io
import json
import re

import openpyxl

from .lernziele import kompetenzziele_setzen
from .models import (Aufgabe, Bereich, Handlungskompetenz, Leistungsziel, Lernziel, Thema, db)

RE_HK = re.compile(r"^\s*([a-z])\.(\d+)\s*:?\s+(.*)$", re.S)
RE_LZ = re.compile(r"^\s*([a-z])\.(\d+)\.(\d+)\s+(.*)$", re.S)


def _clean(s):
    s = re.sub(r"\s+", " ", str(s)).strip()
    s = re.sub(r"\s+([.,])", r"\1", s)
    return s


# ---------------------------------------------------------------- BiVo-Kompetenzen (Excel)

def parse_kompetenzen_xlsx(datei):
    """Liest die Kompetenzliste (Spalte A: Bereich, B: Text, C: K-Stufe).

    Gibt (bereiche, handlungskompetenzen, leistungsziele) als Listen von dicts zurück.
    """
    wb = openpyxl.load_workbook(datei, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    bereiche, hks, lzs = [], [], []
    aktueller_bereich = None
    for row in ws.iter_rows(values_only=True):
        a, b = (row[0] if len(row) > 0 else None), (row[1] if len(row) > 1 else None)
        c = row[2] if len(row) > 2 else None
        if isinstance(a, str) and re.fullmatch(r"\s*[a-z]\s*", a) and b:
            aktueller_bereich = a.strip()
            bereiche.append({"code": aktueller_bereich, "titel": _clean(b)})
            continue
        if not isinstance(b, str) or not b.strip():
            continue
        m = RE_LZ.match(b)
        if m:
            code = f"{m[1]}.{m[2]}.{m[3]}"
            k = int(c) if isinstance(c, (int, float)) else None
            lzs.append({"code": code, "hk": f"{m[1]}.{m[2]}", "text": _clean(m[4]), "k_stufe": k,
                        "sort": len(lzs)})
            continue
        m = RE_HK.match(b)
        if m:
            hks.append({"code": f"{m[1]}.{m[2]}", "bereich": m[1], "titel": _clean(m[3]), "sort": len(hks)})
    return bereiche, hks, lzs


def import_kompetenzen(datei):
    """Importiert/aktualisiert die Kompetenzen. Bestehende Codes werden aktualisiert, nichts gelöscht."""
    bereiche, hks, lzs = parse_kompetenzen_xlsx(datei)
    for b in bereiche:
        obj = db.session.get(Bereich, b["code"]) or Bereich(code=b["code"])
        obj.titel = b["titel"]
        db.session.add(obj)
    db.session.flush()
    for h in hks:
        if not db.session.get(Bereich, h["bereich"]):
            db.session.add(Bereich(code=h["bereich"], titel=h["bereich"]))
            db.session.flush()
        obj = db.session.get(Handlungskompetenz, h["code"]) or Handlungskompetenz(code=h["code"])
        obj.titel, obj.bereich_code, obj.sort = h["titel"], h["bereich"], h["sort"]
        db.session.add(obj)
    db.session.flush()
    for l in lzs:
        if not db.session.get(Handlungskompetenz, l["hk"]):  # Lückenhafte Liste tolerieren
            db.session.add(Handlungskompetenz(code=l["hk"], titel=l["hk"], bereich_code=l["hk"][0], sort=999))
            db.session.flush()
        obj = db.session.get(Leistungsziel, l["code"]) or Leistungsziel(code=l["code"])
        obj.text, obj.k_stufe, obj.hk_code, obj.sort = l["text"], l["k_stufe"], l["hk"], l["sort"]
        db.session.add(obj)
    db.session.commit()
    return len(bereiche), len(hks), len(lzs)


# ---------------------------------------------------------------- Konkrete Lernziele (Text / PDF)

RE_ITEM = re.compile(
    r"(?:^|\s)(\d{1,3})\.\s+(.+?)\(\s*((?:[a-z]\.\d+\.\d+\s*,\s*)*[a-z]\.\d+\.\d+)\s*,\s*K\s*(\d)\s*\)",
    re.S,
)


def pdf_zu_text(datei_bytes):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(datei_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_lernziele(text):
    """Erkennt Einträge der Form '12. Ich kann … (a.2.6, K4)' oder '(a.4.1, a.4.2, K2)'.

    Gibt Liste von dicts {bereich, nummer, text, codes, k_stufe} zurück. Der Bereich wird aus dem ersten
    BiVo-Code abgeleitet; Seitenzahlen ("S. 3") werden ignoriert.
    """
    text = re.sub(r"\bS\.\s*\d+\s*$", " ", text, flags=re.M)
    text = re.sub(r"\s+", " ", text)
    eintraege = []
    for m in RE_ITEM.finditer(text):
        codes = [c.strip() for c in m[3].split(",")]
        eintraege.append({
            "bereich": codes[0][0],
            "nummer": int(m[1]),
            "text": re.sub(r"(\w)- (?!(?:und|oder|bzw|sowie)\b)(\w)", r"\1-\2", _clean(m[2])),
            "codes": codes,
            "k_stufe": int(m[4]),
        })
    return eintraege


def import_lernziele(thema_name, eintraege, ersetzen=False):
    """Legt die Lernziele beim Thema an (aktualisiert gleiche Bereich+Nummer).

    Einträge ohne einen einzigen bekannten BiVo-Code werden nicht übernommen (jedes Lernziel braucht mindestens ein
    Kompetenzziel). Gibt (thema, neu, aktualisiert, fehlende_codes, abgelehnte_eintraege) zurück."""
    thema = Thema.query.filter_by(name=thema_name).first()
    if not thema:
        thema = Thema(name=thema_name)
        db.session.add(thema)
        db.session.flush()
    if ersetzen:
        for lz in list(thema.lernziele):
            db.session.delete(lz)
        db.session.flush()
    neu = akt = 0
    fehlend = set()
    abgelehnt = []
    for e in eintraege:
        fehlend.update(c for c in e["codes"] if not db.session.get(Leistungsziel, c))
        if all(c in fehlend for c in e["codes"]):
            abgelehnt.append(e)
            continue
        lz = Lernziel.query.filter_by(thema_id=thema.id, bereich=e["bereich"], nummer=e["nummer"]).first()
        if lz:
            akt += 1
        else:
            lz = Lernziel(thema=thema, bereich=e["bereich"], nummer=e["nummer"])
            db.session.add(lz)
            neu += 1
        lz.text, lz.k_stufe = e["text"], e["k_stufe"]
        kompetenzziele_setzen(lz, e["codes"])
    db.session.commit()
    return thema, neu, akt, sorted(fehlend), abgelehnt


# ---------------------------------------------------------------- Aufgaben (JSON)

def aufgabe_aus_dict(d, aufgabe=None):
    a = aufgabe or Aufgabe()
    for feld in ("titel", "text", "loesung", "punkte", "k_stufe", "schwierigkeit", "antwortformat",
                 "antwortraum_cm", "verwendung"):
        if feld in d:
            setattr(a, feld, d[feld])
    a.typ = d.get("typ") or "frei"
    a.daten = json.dumps(d.get("daten") or {}, ensure_ascii=False)
    themen = []
    for name in d.get("themen", []):
        t = Thema.query.filter_by(name=name).first()
        if not t:
            t = Thema(name=name)
            db.session.add(t)
            db.session.flush()
        themen.append(t)
    a.themen = themen
    a.lernziele = []
    for ref in d.get("lernziele", []):  # "qPCR|a9"
        thema_name, kuerzel = ref.split("|")
        m = re.fullmatch(r"([a-z])(\d+)", kuerzel)
        lz = (Lernziel.query.join(Thema)
              .filter(Thema.name == thema_name, Lernziel.bereich == m[1], Lernziel.nummer == int(m[2])).first())
        if lz:
            a.lernziele.append(lz)
    codes = set(d.get("leistungsziele", []))
    for lz in a.lernziele:  # Lernziele implizieren ihre BiVo-Leistungsziele
        codes.update(l.code for l in lz.leistungsziele)
    a.leistungsziele = [x for x in (db.session.get(Leistungsziel, c) for c in sorted(codes)) if x]
    db.session.add(a)
    return a


def import_aufgaben(liste):
    n = 0
    for d in liste:
        aufgabe_aus_dict(d)
        n += 1
    db.session.commit()
    return n
