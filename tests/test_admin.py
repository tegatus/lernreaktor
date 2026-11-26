"""Admin-Recht: Nur Admin-Lehrpersonen dürfen die BiVo-Kompetenzliste neu einlesen."""
from app.models import SPALTEN_NACHTRAG, User, db

XLSX = "app/seed_data/Kompetenzen_BiVo.xlsx"


def _user(name):
    return User.query.filter_by(benutzername=name).one()


def _admin_setzen(app, name, wert=True):
    with app.app_context():
        _user(name).ist_admin = wert
        db.session.commit()


def _upload(client):
    with open(XLSX, "rb") as f:
        return client.post("/lp/kompetenzen", data={"datei": (f, "Kompetenzen_BiVo.xlsx")},
                           content_type="multipart/form-data", follow_redirects=True)


def test_demo_lp_ist_kein_admin(app):
    with app.app_context():
        assert _user("lp").ist_admin is False


def test_lp_sieht_kein_bivo_upload(lp):
    r = lp.get("/lp/kompetenzen")
    assert r.status_code == 200 and 'name="datei"' not in r.get_data(as_text=True)


def test_lp_darf_bivo_nicht_importieren(lp):
    with open(XLSX, "rb") as f:
        r = lp.post("/lp/kompetenzen", data={"datei": (f, "x.xlsx")}, content_type="multipart/form-data")
    assert r.status_code == 403


def test_admin_sieht_upload_und_importiert(app, lp):
    _admin_setzen(app, "lp")
    assert 'name="datei"' in lp.get("/lp/kompetenzen").get_data(as_text=True)
    assert "Importiert:" in _upload(lp).get_data(as_text=True)


def test_set_admin_cli(app):
    runner = app.test_cli_runner()
    r = runner.invoke(args=["set-admin", "lp"])
    assert r.exit_code == 0, r.output
    with app.app_context():
        assert _user("lp").ist_admin is True
    r = runner.invoke(args=["set-admin", "lp", "--entziehen"])
    assert r.exit_code == 0, r.output
    with app.app_context():
        assert _user("lp").ist_admin is False


def test_set_admin_nur_lp(app):
    runner = app.test_cli_runner()
    assert runner.invoke(args=["set-admin", "lea"]).exit_code != 0
    assert runner.invoke(args=["set-admin", "gibtsnicht"]).exit_code != 0
    with app.app_context():
        assert _user("lea").ist_admin is False


def test_spalte_nachgeruestet():
    assert any(t == "user" and s == "ist_admin" for t, s, _ in SPALTEN_NACHTRAG)


# ---------------------------------------------------------------- Einstellungen: K-Stufen-Filter

def _lea(app):
    c = app.test_client()
    c.post("/login", data={"benutzername": "lea", "passwort": "lernen-2026"})
    return c


def _qpcr_lernziel_id(app):
    from app.models import Thema
    with app.app_context():
        return next(lz.id for lz in Thema.query.filter_by(name="qPCR").one().lernziele if lz.kuerzel == "a9")


def test_k_filter_standard_aus(app, lp):
    assert 'name="k"' not in _lea(app).get("/lernende/neu").get_data(as_text=True)
    assert 'name="k"' not in lp.get("/lp/pruefungen/neu").get_data(as_text=True)


def test_k_filter_aus_wird_ignoriert(app):
    lea, lz = _lea(app), _qpcr_lernziel_id(app)
    ohne = lea.get(f"/lernende/anzahl?lernziel={lz}").get_json()["anzahl"]
    assert ohne > 0
    assert lea.get(f"/lernende/anzahl?lernziel={lz}&k=6").get_json()["anzahl"] == ohne


def test_einstellungen_nur_admin(lp):
    assert lp.get("/lp/einstellungen").status_code == 403
    assert lp.post("/lp/einstellungen", data={"k_stufen_filter": "1"}).status_code == 403
    assert "/lp/einstellungen" not in lp.get("/lp/").get_data(as_text=True)


def test_admin_schaltet_k_filter_ein(app, lp):
    _admin_setzen(app, "lp")
    assert "/lp/einstellungen" in lp.get("/lp/").get_data(as_text=True)
    r = lp.post("/lp/einstellungen", data={"k_stufen_filter": "1"}, follow_redirects=True)
    assert r.status_code == 200 and "gespeichert" in r.get_data(as_text=True)
    lea, lz = _lea(app), _qpcr_lernziel_id(app)
    assert 'name="k"' in lea.get("/lernende/neu").get_data(as_text=True)
    assert lea.get(f"/lernende/anzahl?lernziel={lz}&k=6").get_json()["anzahl"] == 0
    lp.post("/lp/einstellungen", data={})  # ausschalten
    assert 'name="k"' not in lea.get("/lernende/neu").get_data(as_text=True)


def test_bestehende_pruefung_mit_k_stufen_laedt(app, lp):
    import json
    from app.models import Pruefung
    with app.app_context():
        p = Pruefung(titel="Alt", lp=_user("lp"), parameter=json.dumps({"k_stufen": [2, 3], "lernziel_ids": []}))
        db.session.add(p)
        db.session.commit()
        p_id = p.id
    assert lp.get(f"/lp/pruefungen/{p_id}").status_code == 200
