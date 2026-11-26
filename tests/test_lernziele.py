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


# ---------------------------------------------------------------- Import

def test_import_ohne_gueltigen_code_abgelehnt(app):
    from app.importers import import_lernziele, parse_lernziele
    with app.app_context():
        e = parse_lernziele("1. Ich kann A. (x.9.9, K2) 2. Ich kann B. (a.1.1, x.9.9, K2)")
        assert len(e) == 2
        _, neu, akt, fehlend, abgelehnt = import_lernziele("Neues Thema", e)
        assert (neu, akt, fehlend) == (1, 0, ["x.9.9"])
        assert [x["nummer"] for x in abgelehnt] == [1]
        t = Thema.query.filter_by(name="Neues Thema").one()
        assert [(lz.nummer, _codes(lz)) for lz in t.lernziele] == [(2, {"a.1.1"})]


def test_import_vorschau_warnt(lp, app):
    with app.app_context():
        q_id = _qpcr().id
    r = lp.post("/lp/lernziele/import", data={"thema_id": q_id, "text": "1. Ich kann A. (x.9.9, K2)"})
    assert "wird nicht importiert" in r.get_data(as_text=True)


def test_import_meldet_abgelehnte(lp, app):
    with app.app_context():
        q_id = _qpcr().id
    r = lp.post("/lp/lernziele/import", data={"thema_id": q_id, "bestaetigt": "1",
                                              "text": "1. Ich kann A. (x.9.9, K2) 2. Ich kann B. (a.1.1, K2)"},
                follow_redirects=True)
    assert "ohne gültigen BiVo-Code nicht importiert" in r.get_data(as_text=True)


# ---------------------------------------------------------------- Aufgabenformular

def test_aufgabenformular_hat_bivo_daten(lp, app):
    with app.app_context():
        b16 = _lz("b16").id
    html = lp.get("/lp/aufgaben/neu").get_data(as_text=True)
    assert f'data-bivo="b.5.3 b.5.4" name="lernziel" value="{b16}"' in html
    assert 'data-verknuepfen="einseitig"' in html


def test_lernziele_liste_ohne_k_stufe(lp, app):
    with app.app_context():
        lz = _neues_lz(1, "a.1.1")
        lz.k_stufe = None
        db.session.commit()
    assert "KNone" not in lp.get("/lp/lernziele").get_data(as_text=True)


# ---------------------------------------------------------------- Befunde aus dem Review

def _kapitel_mit(lz):
    dok = TheorieDokument(titel="Skript")
    k = TheorieKapitel(dokument=dok, titel="Kapitel", text="")
    k.lernziele = [lz]
    db.session.add_all([dok, k])
    return k


def test_import_ersetzen_mit_verknuepfungen(app):
    from app.importers import import_lernziele, parse_lernziele
    with app.app_context():
        a1 = _lz("a1")
        a = _aufgabe([a1], ["a.1.1"])
        k = _kapitel_mit(a1)
        db.session.commit()
        a_id, k_id = a.id, k.id
        import_lernziele("qPCR", parse_lernziele("1. Ich kann neu. (a.1.1, K2)"), ersetzen=True)
        assert [lz.text for lz in _qpcr().lernziele] == ["Ich kann neu."]
        assert db.session.get(Aufgabe, a_id).lernziele == []
        assert db.session.get(TheorieKapitel, k_id).lernziele == []


def test_thema_loeschen_blockiert_wenn_lernziel_verwendet(lp, app):
    with app.app_context():
        lz = _neues_lz(1, "a.1.1")
        _aufgabe([lz], ["a.1.1"])  # Aufgabe ohne das Thema selbst
        q_id = _qpcr().id
    lp.post(f"/lp/themen/{q_id}", data={"loeschen": "1"})
    with app.app_context():
        assert db.session.get(Thema, q_id) is not None


def test_thema_loeschen_entfernt_kapitelverknuepfung(lp, app):
    with app.app_context():
        t = Thema(name="Leer")
        lz = Lernziel(thema=t, bereich="a", nummer=1, text="x")
        db.session.add_all([t, lz])
        k = _kapitel_mit(lz)
        db.session.commit()
        t_id, k_id = t.id, k.id
    lp.post(f"/lp/themen/{t_id}", data={"loeschen": "1"})
    with app.app_context():
        assert db.session.get(Thema, t_id) is None
        assert db.session.get(TheorieKapitel, k_id).lernziele == []


def test_lernziel_nummer_ungueltig(lp, app):
    with app.app_context():
        q_id = _qpcr().id
    for nr in ["²", "99999999999", "-3"]:
        r = lp.post("/lp/lernziele/neu", data=_formular(thema=q_id, nummer=nr, text="Ich kann Z.", bivo=["a.1.1"]))
        assert r.status_code == 200 and "positive ganze Zahl" in r.get_data(as_text=True), nr


def test_lernziel_formular_laedt_auswahl_js(lp, app):
    assert "auswahl.js" in lp.get("/lp/lernziele/neu").get_data(as_text=True)


# ---------------------------------------------------------------- Themen zuerst anlegen

def test_thema_anlegen(lp, app):
    r = lp.post("/lp/themen/neu", data={"name": "  Gelelektrophorese ", "beschreibung": "Agarose"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/lp/lernziele")
    with app.app_context():
        assert Thema.query.filter_by(name="Gelelektrophorese").one().beschreibung == "Agarose"


def test_thema_anlegen_doppelt(lp, app):
    r = lp.post("/lp/themen/neu", data={"name": " qPCR "}, follow_redirects=True)
    assert "existiert bereits" in r.get_data(as_text=True)
    with app.app_context():
        assert Thema.query.filter_by(name="qPCR").count() == 1


def test_thema_anlegen_ohne_namen(lp, app):
    with app.app_context():
        n = Thema.query.count()
    lp.post("/lp/themen/neu", data={"name": "  "})
    with app.app_context():
        assert Thema.query.count() == n


def test_import_hat_themen_auswahl(lp, app):
    with app.app_context():
        q_id = _qpcr().id
    html = lp.get(f"/lp/lernziele/import?thema={q_id}").get_data(as_text=True)
    assert '<select name="thema_id"' in html and f'value="{q_id}" selected' in html


def test_import_ohne_themen_hinweis(lp, app):
    from app.models import aufgabe_lernziel, aufgabe_thema, kapitel_lernziel
    with app.app_context():
        for tabelle in (aufgabe_thema, aufgabe_lernziel, kapitel_lernziel):
            db.session.execute(tabelle.delete())
        for t in Thema.query.all():
            db.session.delete(t)
        db.session.commit()
    html = lp.get("/lp/lernziele/import").get_data(as_text=True)
    assert "zuerst ein Thema" in html and '<select name="thema_id"' not in html


def test_import_unbekanntes_thema(lp, app):
    with app.app_context():
        n = Thema.query.count()
    r = lp.post("/lp/lernziele/import", data={"thema_id": "9999", "bestaetigt": "1",
                                              "text": "1. Ich kann A. (a.1.1, K2)"})
    assert "Bitte ein Thema" in r.get_data(as_text=True)
    with app.app_context():
        assert Thema.query.count() == n


def test_lernziele_seite_hat_thema_formular(lp, app):
    html = lp.get("/lp/lernziele").get_data(as_text=True)
    assert 'action="/lp/themen/neu"' in html and "/lp/lernziele/import?thema=" in html


def test_thema_anlegen_doppelt_gross_klein(lp, app):
    r = lp.post("/lp/themen/neu", data={"name": "QPCR"}, follow_redirects=True)
    assert "existiert bereits" in r.get_data(as_text=True)
    with app.app_context():
        assert Thema.query.filter(db.func.lower(Thema.name) == "qpcr").count() == 1


def test_thema_umbenennen_auf_bestehenden_namen(lp, app):
    with app.app_context():
        t = Thema(name="Anderes")
        db.session.add(t)
        db.session.commit()
        t_id = t.id
    r = lp.post(f"/lp/themen/{t_id}", data={"name": "qpcr"}, follow_redirects=True)
    assert r.status_code == 200 and "existiert bereits" in r.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Thema, t_id).name == "Anderes"
