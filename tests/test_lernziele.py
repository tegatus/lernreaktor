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


# ---------------------------------------------------------------- Formular

def _formular(**werte):
    d = {"thema": "", "bereich": "", "nummer": "", "text": "", "k_stufe": "", "bivo": []}
    d.update(werte)
    return d


def test_lernziel_anlegen_mit_kompetenzziel(lp, app):
    with app.app_context():
        q_id, anzahl = _qpcr().id, Lernziel.query.count()
        erwartet = naechste_nummer(q_id, "b")
    r = lp.post("/lp/lernziele/neu", data=_formular(thema=q_id, text="Ich kann X.", bivo=["b.5.3", "a.1.1"]))
    assert r.status_code == 302 and r.headers["Location"].endswith("/lp/lernziele")
    with app.app_context():
        assert Lernziel.query.count() == anzahl + 1
        lz = Lernziel.query.filter_by(text="Ich kann X.").one()
        assert (lz.bereich, lz.nummer, lz.thema_id) == ("b", erwartet, q_id)
        assert _codes(lz) == {"b.5.3", "a.1.1"}


def test_lernziel_formular_zeigt_kompetenzziele(lp, app):
    with app.app_context():
        q_id = _qpcr().id
    html = lp.get(f"/lp/lernziele/neu?thema={q_id}").get_data(as_text=True)
    assert 'name="bivo" value="a.1.1"' in html and f'value="{q_id}" selected' in html


def test_lernziel_ohne_kompetenzziel_abgelehnt(lp, app):
    with app.app_context():
        q_id, anzahl = _qpcr().id, Lernziel.query.count()
    r = lp.post("/lp/lernziele/neu", data=_formular(thema=q_id, text="Ich kann Y."))
    assert r.status_code == 200 and "mindestens ein" in r.get_data(as_text=True)
    with app.app_context():
        assert Lernziel.query.count() == anzahl


def test_lernziel_nur_unbekannte_codes_abgelehnt(lp, app):
    with app.app_context():
        q_id, anzahl = _qpcr().id, Lernziel.query.count()
    r = lp.post("/lp/lernziele/neu", data=_formular(thema=q_id, text="Ich kann Y.", bivo=["x.9.9"]))
    assert r.status_code == 200 and "mindestens ein" in r.get_data(as_text=True)
    with app.app_context():
        assert Lernziel.query.count() == anzahl


def test_lernziel_bearbeiten_fuehrt_aufgaben_nach(lp, app):
    with app.app_context():
        lz = _neues_lz(1, "a.1.1")
        a = _aufgabe([lz], ["a.1.1"])
        lz_id, a_id, q_id = lz.id, a.id, _qpcr().id
    r = lp.post(f"/lp/lernziele/{lz_id}", data=_formular(thema=q_id, bereich="z", nummer="1", text="Neu",
                                                        bivo=["a.1.1", "a.1.2"]), follow_redirects=True)
    assert "1 Aufgabe angepasst" in r.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Lernziel, lz_id).text == "Neu"
        assert _codes(db.session.get(Aufgabe, a_id)) == {"a.1.1", "a.1.2"}


def test_lernziel_nummer_konflikt(lp, app):
    with app.app_context():
        a1 = _lz("a1")
        a1_id, q_id, text = a1.id, a1.thema_id, a1.text
        codes = sorted(_codes(a1))
    r = lp.post(f"/lp/lernziele/{a1_id}", data=_formular(thema=q_id, bereich="a", nummer="2", text="Anders", bivo=codes))
    assert r.status_code == 200 and "existiert bereits" in r.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Lernziel, a1_id).text == text
    r = lp.post(f"/lp/lernziele/{a1_id}", data=_formular(thema=q_id, bereich="a", nummer="1", text="Anders", bivo=codes))
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(Lernziel, a1_id).text == "Anders"


def test_lernziel_loeschen_blockiert(lp, app):
    with app.app_context():
        lz = _neues_lz(1, "a.1.1")
        a = _aufgabe([lz], ["a.1.1"])
        a.titel = "Pipettieren üben"
        db.session.commit()
        lz_id = lz.id
    r = lp.post(f"/lp/lernziele/{lz_id}", data={"loeschen": "1"}, follow_redirects=True)
    assert "Pipettieren üben" in r.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Lernziel, lz_id) is not None


def test_lernziel_loeschen(lp, app):
    with app.app_context():
        lz = _neues_lz(1, "a.1.1")
        db.session.commit()
        lz_id = lz.id
    r = lp.post(f"/lp/lernziele/{lz_id}", data={"loeschen": "1"})
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(Lernziel, lz_id) is None


def test_lernziele_liste_markiert_ohne_bivo(lp, app):
    with app.app_context():
        _neues_lz(1)
        db.session.commit()
    html = lp.get("/lp/lernziele").get_data(as_text=True)
    assert "kein BiVo-Ziel" in html and "/lp/lernziele/neu?thema=" in html
