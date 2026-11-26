"""Auswahl von Aufgaben für Übungsblätter und Zusammenstellung von Prüfungen."""
import random
from collections import Counter

from .models import (Aufgabe, BlattAufgabe, Leistungsziel, Lernziel, Thema, Uebungsblatt, User, db,
                     aufgabe_leistungsziel, aufgabe_lernziel, aufgabe_thema)


def filter_aufgaben(themen_ids=(), leistungsziel_codes=(), lernziel_ids=(), k_stufen=(), verwendungen=("beide", "uebung")):
    """Innerhalb einer Kategorie ODER, zwischen den Kategorien UND. Lernziele und BiVo-Kompetenzziele bilden
    zusammen eine Kategorie (Lernziele beruhen auf Kompetenzzielen und werden in der Auswahl gemeinsam angekreuzt)."""
    q = Aufgabe.query.filter(Aufgabe.aktiv.is_(True), Aufgabe.verwendung.in_(list(verwendungen)))
    if themen_ids:
        q = q.filter(Aufgabe.id.in_(db.select(aufgabe_thema.c.aufgabe_id)
                                    .where(aufgabe_thema.c.thema_id.in_(list(themen_ids)))))
    ziele = []
    if leistungsziel_codes:
        ziele.append(Aufgabe.id.in_(db.select(aufgabe_leistungsziel.c.aufgabe_id)
                                    .where(aufgabe_leistungsziel.c.leistungsziel_code.in_(list(leistungsziel_codes)))))
    if lernziel_ids:
        ziele.append(Aufgabe.id.in_(db.select(aufgabe_lernziel.c.aufgabe_id)
                                    .where(aufgabe_lernziel.c.lernziel_id.in_(list(lernziel_ids)))))
    if ziele:
        q = q.filter(db.or_(*ziele))
    if k_stufen:
        q = q.filter(Aufgabe.k_stufe.in_(list(k_stufen)))
    return q.order_by(Aufgabe.id).all()


def _ziele(aufgabe, lernziel_ids, codes):
    """Welche der gewünschten Ziele deckt die Aufgabe ab?"""
    z = {("lz", l.id) for l in aufgabe.lernziele if l.id in lernziel_ids}
    z |= {("bivo", l.code) for l in aufgabe.leistungsziele if l.code in codes}
    return z


def waehle_uebungsaufgaben(lernende, kandidaten, anzahl, lernziel_ids=(), codes=(), rng=None):
    """Wählt `anzahl` Aufgaben: bevorzugt noch nie bearbeitete und möglichst breite Abdeckung der Ziele."""
    rng = rng or random.Random()
    gebraucht = Counter(
        aid for (aid,) in db.session.query(BlattAufgabe.aufgabe_id)
        .join(Uebungsblatt).filter(Uebungsblatt.lernende_id == lernende.id)
    )
    pool = list(kandidaten)
    rng.shuffle(pool)
    lernziel_ids, codes = set(lernziel_ids), set(codes)
    abgedeckt, gewaehlt = set(), []
    while pool and len(gewaehlt) < anzahl:
        best = max(pool, key=lambda a: (len(_ziele(a, lernziel_ids, codes) - abgedeckt), -gebraucht[a.id]))
        pool.remove(best)
        gewaehlt.append(best)
        abgedeckt |= _ziele(best, lernziel_ids, codes)
    # sinnvolle Reihenfolge: nach Thema, dann K-Stufe (einfach → anspruchsvoll)
    gewaehlt.sort(key=lambda a: ((a.themen[0].name if a.themen else ""), a.k_stufe or 0, a.id))
    return gewaehlt


def stelle_pruefung_zusammen(themen_ids=(), lernziel_ids=(), leistungsziel_codes=(), ziel_punkte=30,
                             max_aufgaben=None, k_stufen=(), nur_pruefungsaufgaben=False,
                             ausschliessen_ids=(), seed=None):
    """Greedy-Zusammenstellung.

    1. Pool: aktive Aufgaben (Verwendung Prüfung/beide), gefiltert nach Themen und K-Stufen.
    2. Abdeckung: solange Ziele (Lernziele/BiVo-Leistungsziele) offen sind, die Aufgabe nehmen,
       welche am meisten offene Ziele abdeckt (bei Gleichstand: zufällig).
    3. Auffüllen bis zur gewünschten Punktzahl.
    Rückgabe: dict mit aufgaben, punkte, abgedeckt, nicht_abgedeckt, k_verteilung.
    """
    rng = random.Random(seed)
    verw = ["pruefung"] if nur_pruefungsaufgaben else ["pruefung", "beide"]
    lernziel_ids, codes = set(lernziel_ids), set(leistungsziel_codes)
    ziele = {("lz", i) for i in lernziel_ids} | {("bivo", c) for c in codes}

    pool = filter_aufgaben(themen_ids=themen_ids, k_stufen=k_stufen, verwendungen=verw)
    if not themen_ids and ziele:
        pool = [a for a in pool if _ziele(a, lernziel_ids, codes)]
    pool = [a for a in pool if a.id not in set(ausschliessen_ids)]
    rng.shuffle(pool)

    gewaehlt, punkte, abgedeckt = [], 0.0, set()
    max_n = max_aufgaben or 10_000

    def nehmen(a):
        nonlocal punkte, abgedeckt
        pool.remove(a)
        gewaehlt.append(a)
        punkte += a.punkte
        abgedeckt |= _ziele(a, lernziel_ids, codes)

    # Phase 1: Ziele abdecken
    while pool and len(gewaehlt) < max_n and (ziele - abgedeckt):
        best = max(pool, key=lambda a: len(_ziele(a, lernziel_ids, codes) - abgedeckt))
        if not (_ziele(best, lernziel_ids, codes) - abgedeckt):
            break
        if punkte + best.punkte > ziel_punkte * 1.15 and gewaehlt:
            break  # Punktebudget erschöpft – Rest als "nicht abgedeckt" melden
        nehmen(best)

    # Phase 2: auffüllen
    for a in list(pool):
        if len(gewaehlt) >= max_n or punkte >= ziel_punkte:
            break
        if punkte + a.punkte <= ziel_punkte:
            nehmen(a)

    gewaehlt.sort(key=lambda a: ((a.themen[0].name if a.themen else ""), a.k_stufe or 0, a.id))
    return {
        "aufgaben": gewaehlt,
        "punkte": punkte,
        "abgedeckt": abgedeckt,
        "nicht_abgedeckt": ziele - abgedeckt,
        "k_verteilung": Counter(a.k_stufe for a in gewaehlt),
    }


def ziele_beschreiben(ziele):
    """Wandelt {("lz", id), ("bivo", code)} in lesbare Labels um."""
    out = []
    for art, wert in sorted(ziele, key=lambda z: (z[0], str(z[1]))):
        if art == "lz":
            lz = db.session.get(Lernziel, wert)
            if lz:
                out.append(f"{lz.label}: {lz.text}")
        else:
            l = db.session.get(Leistungsziel, wert)
            if l:
                out.append(f"{l.code}: {l.text}")
    return out


def geuebte_aufgaben_der_klasse(klasse):
    ids = {u.id for u in klasse.lernende} if klasse else set()
    if not ids:
        return set()
    return {aid for (aid,) in db.session.query(BlattAufgabe.aufgabe_id).join(Uebungsblatt)
            .filter(Uebungsblatt.lernende_id.in_(ids))}


def auswahl_beschreiben(themen_ids, codes, lernziel_ids, k_stufen):
    teile = []
    if themen_ids:
        teile.append("Themen: " + ", ".join(t.name for t in Thema.query.filter(Thema.id.in_(themen_ids))))
    if codes:
        teile.append("BiVo: " + ", ".join(sorted(codes)))
    if lernziel_ids:
        teile.append("Lernziele: " + ", ".join(l.label for l in Lernziel.query.filter(Lernziel.id.in_(lernziel_ids))))
    if k_stufen:
        teile.append("K-Stufen: " + ", ".join(f"K{k}" for k in sorted(k_stufen)))
    return " · ".join(teile)
