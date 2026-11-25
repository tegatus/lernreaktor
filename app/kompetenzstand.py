"""Kompetenzstand der Lernenden: Niveau pro Leistungsziel (BiVo) und pro Thema aus korrigierten Aufgaben.

Jede korrigierte Aufgabe mit Niveau ist eine Bewertung. Sie zählt für die Leistungsziele der Aufgabe (direkt und
über ihre Lernziele) und für ihre Themen. Stand = gerundeter Durchschnitt der letzten 3 Bewertungen, höchstens 3;
Instruktor (4) nur, wenn die jüngste Bewertung Instruktor ist.
"""
from dataclasses import dataclass, field

from .models import Uebungsblatt

LETZTE = 3


@dataclass
class Stand:
    bewertungen: list = field(default_factory=list)  # [(datum, niveau)], aufsteigend nach Datum

    @property
    def anzahl(self):
        return len(self.bewertungen)

    @property
    def zuletzt(self):
        return self.bewertungen[-1][0] if self.bewertungen else None

    @property
    def niveau(self):
        if not self.bewertungen:
            return None
        if self.bewertungen[-1][1] == 4:
            return 4
        letzte = [n for _, n in self.bewertungen[-LETZTE:]]
        return min(3, int(sum(letzte) / len(letzte) + 0.5))


def _codes(aufgabe):
    codes = {l.code for l in aufgabe.leistungsziele}
    for lz in aufgabe.lernziele:
        codes |= {l.code for l in lz.leistungsziele}
    return codes


def kompetenzstand(lernende_ids):
    """{lernende_id: {"ziele": {code: Stand}, "themen": {name: Stand}}} für die angegebenen Lernenden."""
    ergebnis = {i: {"ziele": {}, "themen": {}} for i in lernende_ids}
    if not lernende_ids:
        return ergebnis
    blaetter = (Uebungsblatt.query.filter(Uebungsblatt.lernende_id.in_(lernende_ids),
                                          Uebungsblatt.status == "korrigiert").all())
    eintraege = []
    for b in blaetter:
        datum = b.korrigiert_am or b.erstellt_am
        for ba in b.aufgaben:
            if ba.niveau:
                eintraege.append((datum, ba.id, b.lernende_id, ba.aufgabe, ba.niveau))
    eintraege.sort(key=lambda e: (e[0], e[1]))
    for datum, _, lid, aufgabe, niveau in eintraege:
        for code in _codes(aufgabe):
            ergebnis[lid]["ziele"].setdefault(code, Stand()).bewertungen.append((datum, niveau))
        for t in aufgabe.themen:
            ergebnis[lid]["themen"].setdefault(t.name, Stand()).bewertungen.append((datum, niveau))
    return ergebnis
