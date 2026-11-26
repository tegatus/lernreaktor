"""Aufgabenauswahl (Übungsblatt/Prüfung): Lernziele und Kompetenzziele als eine Gruppe, gegenseitiges Ankreuzen."""
from app.models import Aufgabe, Leistungsziel, Thema, db
from app.selection import filter_aufgaben


def _b16():
    return next(lz for lz in Thema.query.filter_by(name="qPCR").one().lernziele if lz.kuerzel == "b16")


def _aufgabe(titel, codes=(), lernziele=(), themen=()):
    a = Aufgabe(titel=titel, text="…", verwendung="beide")
    db.session.add(a)
    a.leistungsziele = [db.session.get(Leistungsziel, c) for c in codes]
    a.lernziele = list(lernziele)
    a.themen = list(themen)
    db.session.commit()
    return a


def test_lernziel_oder_kompetenzziel(app):
    with app.app_context():
        b16 = _b16()
        nur_code = _aufgabe("Nur Code", codes=["e.1.1"])
        nur_lz = _aufgabe("Nur Lernziel", lernziele=[b16])
        ids = {a.id for a in filter_aufgaben(leistungsziel_codes=["e.1.1"], lernziel_ids=[b16.id])}
        assert {nur_code.id, nur_lz.id} <= ids


def test_thema_bleibt_und(app):
    with app.app_context():
        anderes = Thema(name="Anderes")
        db.session.add(anderes)
        nur_code = _aufgabe("Nur Code", codes=["e.1.1"])
        mit_thema = _aufgabe("Mit Thema", codes=["e.1.1"], themen=[anderes])
        ids = {a.id for a in filter_aufgaben(themen_ids=[anderes.id], leistungsziel_codes=["e.1.1"],
                                             lernziel_ids=[_b16().id])}
        assert mit_thema.id in ids and nur_code.id not in ids
