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
