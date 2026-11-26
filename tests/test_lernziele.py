"""Lernziele: Pflicht-Verknüpfung zu BiVo-Kompetenzzielen, Formular, Import, Weitergabe an Aufgaben."""
from app.lernziele import aufgaben_mit, kompetenzziele_setzen, lernziel_loeschen, naechste_nummer
from app.models import Aufgabe, Leistungsziel, Lernziel, Thema, TheorieDokument, TheorieKapitel, db


def _qpcr():
    return Thema.query.filter_by(name="qPCR").one()


def _lz(kuerzel):
    t = _qpcr()
    return next(lz for lz in t.lernziele if lz.kuerzel == kuerzel)


def _ziele(*codes):
    return [db.session.get(Leistungsziel, c) for c in codes]


def _codes(obj):
    return {l.code for l in obj.leistungsziele}


def _neues_lz(nummer, *codes):
    lz = Lernziel(thema=_qpcr(), bereich="z", nummer=nummer, text=f"Testziel {nummer}", k_stufe=2)
    db.session.add(lz)
    lz.leistungsziele = _ziele(*codes)
    return lz


def _aufgabe(lernziele, codes):
    a = Aufgabe(titel="Testaufgabe", text="…")
    a.lernziele = list(lernziele)
    a.leistungsziele = _ziele(*codes)
    db.session.add(a)
    db.session.commit()
    return a


# ---------------------------------------------------------------- Domänenfunktionen

def test_naechste_nummer(app):
    with app.app_context():
        assert naechste_nummer(_qpcr().id, "a") == 16
        assert naechste_nummer(_qpcr().id, "z") == 1


def test_setzen_ergaenzt_und_entfernt(app):
    with app.app_context():
        lz = _neues_lz(1, "a.1.1")
        a = _aufgabe([lz], ["a.1.1"])
        assert kompetenzziele_setzen(lz, ["a.1.2"]) == 1
        db.session.commit()
        assert _codes(lz) == {"a.1.2"}
        assert _codes(db.session.get(Aufgabe, a.id)) == {"a.1.2"}


def test_setzen_behaelt_code_anderer_lernziele(app):
    with app.app_context():
        lz1, lz2 = _neues_lz(1, "a.1.1"), _neues_lz(2, "a.1.1", "a.1.2")
        a = _aufgabe([lz1, lz2], ["a.1.1", "a.1.2"])
        kompetenzziele_setzen(lz1, ["a.1.2"])
        db.session.commit()
        assert _codes(db.session.get(Aufgabe, a.id)) == {"a.1.1", "a.1.2"}


def test_setzen_ignoriert_unbekannte_codes(app):
    with app.app_context():
        lz = _neues_lz(1, "a.1.1")
        kompetenzziele_setzen(lz, ["a.1.1", "x.9.9"])
        assert _codes(lz) == {"a.1.1"}


def test_setzen_ohne_aenderung_zaehlt_null(app):
    with app.app_context():
        lz = _neues_lz(1, "a.1.1")
        _aufgabe([lz], ["a.1.1"])
        assert kompetenzziele_setzen(lz, ["a.1.1"]) == 0


def test_aufgaben_mit(app):
    with app.app_context():
        lz = _neues_lz(1, "a.1.1")
        a = _aufgabe([lz], ["a.1.1"])
        assert [x.id for x in aufgaben_mit(lz)] == [a.id]


def test_loeschen_blockiert_bei_aufgabe(app):
    with app.app_context():
        lz = _neues_lz(1, "a.1.1")
        a = _aufgabe([lz], ["a.1.1"])
        assert [x.id for x in lernziel_loeschen(lz)] == [a.id]
        db.session.commit()
        assert db.session.get(Lernziel, lz.id) is not None


def test_loeschen_entfernt_kapitelverknuepfung(app):
    with app.app_context():
        lz = _neues_lz(1, "a.1.1")
        dok = TheorieDokument(titel="Skript")
        k = TheorieKapitel(dokument=dok, titel="Kapitel", text="")
        k.lernziele = [lz]
        db.session.add_all([dok, k])
        db.session.commit()
        lz_id, k_id = lz.id, k.id
        assert lernziel_loeschen(lz) == []
        db.session.commit()
        assert db.session.get(Lernziel, lz_id) is None
        assert db.session.get(TheorieKapitel, k_id).lernziele == []
