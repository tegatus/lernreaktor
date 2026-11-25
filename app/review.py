"""Änderungsvorschläge zu Review-Hinweisen: prüfen (Agent-Schnittstelle), vergleichen und übernehmen (Lehrperson)."""
import difflib
import html
import json
import re
from types import SimpleNamespace

from markupsafe import Markup

from .aufgabentypen import TYPEN, pruefen as typ_pruefen
from .importers import aufgabe_aus_dict
from .markup import RE_BILD, referenzierte_bilder
from .models import ANTWORTFORMATE, VERWENDUNGEN, Leistungsziel, Lernziel, Thema

AUFGABE_FELDER = {
    "titel": "Titel", "text": "Aufgabentext", "loesung": "Musterlösung", "punkte": "Punkte", "k_stufe": "K-Stufe",
    "schwierigkeit": "Schwierigkeit", "antwortformat": "Antwortformat", "antwortraum_cm": "Antwortfeld (cm)",
    "verwendung": "Verwendung", "typ": "Aufgabentyp", "daten": "Daten des Aufgabentyps", "themen": "Themen",
    "lernziele": "Lernziele", "leistungsziele": "BiVo-Leistungsziele",
}
KAPITEL_FELDER = {"titel": "Titel", "text": "Text"}
GROESSEN = ("voll", "zweidrittel", "halb", "drittel", "viertel")


def _bildmarker_pruefen(texte, vorhandene):
    fehler = []
    for name, text in texte:
        for nr in sorted(referenzierte_bilder(text) - vorhandene):
            fehler.append(f"{name}: [[bild:{nr}]] gibt es nicht (vorhanden: {sorted(vorhandene) or 'keine Bilder'}).")
        for m in RE_BILD.finditer(text or ""):
            if m[2] and m[2].lower() not in GROESSEN:
                fehler.append(f"{name}: unbekannte Bildgrösse «{m[2]}» (erlaubt: {', '.join(GROESSEN)}).")
    return fehler


def pruefe_aufgabe(a, aenderungen):
    """Gibt (bereinigte Änderungen, Fehlerliste) zurück. Nur bekannte Felder, Tags nur aus dem Katalog."""
    fehler = [f"Unbekanntes Feld «{k}» (erlaubt: {', '.join(AUFGABE_FELDER)})." for k in aenderungen
              if k not in AUFGABE_FELDER]
    neu = {k: v for k, v in aenderungen.items() if k in AUFGABE_FELDER}
    alt = a.to_dict()
    for k in ("titel", "text", "loesung"):
        if k in neu and not isinstance(neu[k], str):
            fehler.append(f"«{k}» muss Text sein.")
    if "titel" in neu and not str(neu["titel"]).strip():
        fehler.append("Der Titel darf nicht leer sein.")
    if "text" in neu and not str(neu["text"]).strip():
        fehler.append("Der Aufgabentext darf nicht leer sein.")
    for k, lo, hi in (("punkte", 0.5, 50), ("antwortraum_cm", 0, 25)):
        if k in neu:
            try:
                neu[k] = float(neu[k])
                if not lo <= neu[k] <= hi:
                    raise ValueError
            except (TypeError, ValueError):
                fehler.append(f"«{k}» muss eine Zahl zwischen {lo} und {hi} sein.")
    for k, werte in (("k_stufe", range(1, 7)), ("schwierigkeit", range(1, 4))):
        if k in neu and neu[k] is not None and neu[k] not in werte:
            fehler.append(f"«{k}» muss zwischen {werte.start} und {werte.stop - 1} liegen.")
    for k, werte in (("antwortformat", ANTWORTFORMATE), ("verwendung", VERWENDUNGEN), ("typ", TYPEN)):
        if k in neu and neu[k] not in werte:
            fehler.append(f"«{k}» muss einer dieser Werte sein: {', '.join(werte)}.")
    if "daten" in neu and not isinstance(neu["daten"], dict):
        fehler.append("«daten» muss ein JSON-Objekt sein.")
    for k in ("themen", "lernziele", "leistungsziele"):
        if k in neu and not (isinstance(neu[k], list) and all(isinstance(x, str) for x in neu[k])):
            fehler.append(f"«{k}» muss eine Liste von Texten sein.")
            neu.pop(k)
    if "themen" in neu:
        bekannt = {t.name for t in Thema.query}
        fehler += [f"Thema «{n}» gibt es nicht – nur bestehende Themen verwenden." for n in neu["themen"] if n not in bekannt]
    if "lernziele" in neu:
        for ref in neu["lernziele"]:
            m = re.fullmatch(r"(.+)\|([a-z])(\d+)", str(ref))
            if not m or not Lernziel.query.join(Thema).filter(Thema.name == m[1], Lernziel.bereich == m[2],
                                                              Lernziel.nummer == int(m[3])).first():
                fehler.append(f"Lernziel «{ref}» gibt es nicht (Format «Thema|a9»).")
    if "leistungsziele" in neu:
        bekannt = {l.code for l in Leistungsziel.query}
        fehler += [f"Leistungsziel «{c}» gibt es nicht." for c in neu["leistungsziele"] if c not in bekannt]
    neu = {k: v for k, v in neu.items() if v != alt.get(k)}
    if fehler:
        return neu, fehler
    zusammen = {**alt, **neu}
    fehler += _bildmarker_pruefen([("Aufgabentext", zusammen["text"]), ("Musterlösung", zusammen["loesung"])],
                                  {b.nr for b in a.bilder})
    entwurf = SimpleNamespace(typ=zusammen["typ"], text=zusammen["text"], loesung=zusammen["loesung"],
                              daten=json.dumps(zusammen["daten"] if zusammen["typ"] != "frei" else {}))
    fehler += [f"Aufgabentyp: {f}" for f in typ_pruefen(entwurf)]
    return neu, fehler


def pruefe_kapitel(k, aenderungen):
    fehler = [f"Unbekanntes Feld «{x}» (erlaubt: titel, text)." for x in aenderungen if x not in KAPITEL_FELDER]
    neu = {x: v for x, v in aenderungen.items() if x in KAPITEL_FELDER}
    if any(not isinstance(v, str) for v in neu.values()):
        fehler.append("Titel und Text müssen Text sein.")
    elif "titel" in neu and not neu["titel"].strip():
        fehler.append("Der Titel darf nicht leer sein.")
    neu = {x: v for x, v in neu.items() if v != getattr(k, x)}
    if not fehler and "text" in neu:
        fehler += _bildmarker_pruefen([("Text", neu["text"])], {b.nr for b in k.bilder})
    return neu, fehler


def _zeilen_markieren(alt, neu):
    """Geänderte Zeilen in beiden Fassungen mit <mark> hervorheben (HTML-sicher)."""
    a, b = alt.split("\n"), neu.split("\n")
    links, rechts = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        links += [f"<mark>{html.escape(z)}</mark>" if op != "equal" else html.escape(z) for z in a[i1:i2]]
        rechts += [f"<mark>{html.escape(z)}</mark>" if op != "equal" else html.escape(z) for z in b[j1:j2]]
    return Markup("\n".join(links)), Markup("\n".join(rechts))


def unterschiede(kommentar):
    """[(Feldname, alt, neu)] für die Ansicht der Lehrperson; geänderte Zeilen sind markiert."""
    v = kommentar.vorschlag_dict or {}
    if kommentar.aufgabe:
        alt, namen = kommentar.aufgabe.to_dict(), AUFGABE_FELDER
    else:
        alt, namen = {"titel": kommentar.kapitel.titel, "text": kommentar.kapitel.text}, KAPITEL_FELDER
    lesbar = lambda x: ", ".join(map(str, x)) if isinstance(x, list) else (  # noqa: E731
        json.dumps(x, ensure_ascii=False, indent=1) if isinstance(x, dict) else ("–" if x is None else str(x)))
    return [(namen.get(f, f), *_zeilen_markieren(lesbar(alt.get(f)), lesbar(neu))) for f, neu in v.items()]


def uebernehmen(kommentar, aenderungen=None):
    """Übernimmt den Vorschlag (oder die übergebenen Änderungen). Bilder und Theorie-Verknüpfungen bleiben."""
    aenderungen = kommentar.vorschlag_dict if aenderungen is None else aenderungen
    if kommentar.aufgabe:
        aufgabe_aus_dict({**kommentar.aufgabe.to_dict(), **aenderungen}, kommentar.aufgabe)
    elif kommentar.kapitel:
        for feld, wert in aenderungen.items():
            setattr(kommentar.kapitel, feld, wert)
