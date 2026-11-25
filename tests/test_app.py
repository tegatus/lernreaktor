import base64
import os
import io
import json

import pytest
from PIL import Image
from pypdf import PdfReader

from app import create_app
from app.importers import parse_kompetenzen_xlsx, parse_lernziele
from app.models import Aufgabe, Lernziel, Thema, Uebungsblatt, User, db
from app.seed import seed_basisdaten, seed_demo
from app.selection import stelle_pruefung_zusammen


@pytest.fixture
def app(tmp_path):
    # Standard: frische SQLite-Datei pro Test. Mit TEST_DATABASE_URL=postgresql+psycopg://… laufen die Tests
    # gegen PostgreSQL (die Datenbank wird pro Test geleert).
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path}/t.sqlite"
    app = create_app({"SQLALCHEMY_DATABASE_URI": url,
                      "UPLOAD_DIR": str(tmp_path / "dateien"), "TESTING": True, "TESTING_NO_CSRF": True})
    with app.app_context():
        if url.startswith("postgresql"):
            db.drop_all()
            db.create_all()
        seed_basisdaten()
        seed_demo()
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def login(client, name, pw):
    return client.post("/login", data={"benutzername": name, "passwort": pw}, follow_redirects=True)


def pdf_text(daten):
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(daten)).pages)


def test_parser_auf_benutzerdateien():
    with open("app/seed_data/lernziele_molek1.txt", encoding="utf-8") as f:
        e = parse_lernziele(f.read())
    assert len(e) == 33
    assert sum(1 for x in e if x["bereich"] == "a") == 15
    assert e[13]["codes"] == ["a.4.1", "a.4.2"] and e[13]["k_stufe"] == 2
    b, h, l = parse_kompetenzen_xlsx("app/seed_data/Kompetenzen_BiVo.xlsx")
    assert [x["code"] for x in b] == ["a", "b", "e", "f", "g"]
    assert len(l) == 71 and l[0] == {"code": "a.1.1", "hk": "a.1", "text": "Sie erklären die Zielsetzung eines Laborauftrags.",
                                     "k_stufe": 2, "sort": 0}


def test_lernziele_mit_bivo_verknuepft(app):
    with app.app_context():
        lz = Lernziel.query.join(Thema).filter(Thema.name == "qPCR", Lernziel.bereich == "b", Lernziel.nummer == 16).one()
        assert [l.code for l in lz.leistungsziele] == ["b.5.3", "b.5.4"]
        # Aufgaben erben BiVo-Codes ihrer Lernziele
        a = Aufgabe.query.filter_by(titel="Master-Mix für eine qPCR-Platte").one()
        assert {"a.2.3", "b.1.3"} <= {l.code for l in a.leistungsziele}


def test_ganzer_ablauf_lernende_und_lp(app):
    c = app.test_client()
    assert "Meine Übungsblätter" in login(c, "lea", "lernen-2026").get_data(as_text=True)
    with app.app_context():
        qpcr = Thema.query.filter_by(name="qPCR").one().id
    r = c.post("/lernende/neu", data={"thema": qpcr, "bivo": "a.2.3", "anzahl": 3}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        blatt = Uebungsblatt.query.one()
        ids = [ba.aufgabe for ba in blatt.aufgaben]
        assert ids and all(a.verwendung != "pruefung" for a in ids)
        assert all("a.2.3" in [l.code for l in a.leistungsziele] for a in ids)
        bid = blatt.id
    pdf = c.get(f"/blatt/{bid}/aufgaben.pdf")
    assert pdf.status_code == 200 and "Aufgabe 1" in pdf_text(pdf.data)
    assert c.get(f"/blatt/{bid}/loesung.pdf").status_code == 403  # Lösung noch nicht freigegeben

    # Foto hochladen
    buf = io.BytesIO()
    Image.new("RGB", (800, 1100), "white").save(buf, "JPEG")
    buf.seek(0)
    r = c.post(f"/blatt/{bid}/hochladen", data={"dateien": (buf, "seite1.jpg")},
               content_type="multipart/form-data", follow_redirects=True)
    assert "1 Seite(n) hochgeladen" in r.get_data(as_text=True)

    # Andere Lernende dürfen nichts sehen
    c2 = app.test_client()
    login(c2, "noah", "lernen-2026")
    assert c2.get(f"/blatt/{bid}/aufgaben.pdf").status_code == 403

    # LP korrigiert
    lp = app.test_client()
    login(lp, "lp", "lp-demo-2026")
    assert "Zu korrigieren" in lp.get("/lp/").get_data(as_text=True)
    assert lp.get(f"/blatt/{bid}/loesung.pdf").status_code == 200
    with app.app_context():
        blatt = db.session.get(Uebungsblatt, bid)
        seite_id = blatt.abgaben[0].seiten[0].id
        aufg = [{"id": ba.id, "punkte": "2", "kommentar": "gut"} for ba in blatt.aufgaben]
    png = io.BytesIO()
    Image.new("RGB", (800, 1100), "pink").save(png, "PNG")
    data_url = "data:image/png;base64," + base64.b64encode(png.getvalue()).decode()
    r = lp.post(f"/lp/korrektur/{bid}", json={
        "aufgaben": aufg, "gesamtkommentar": "Weiter so!", "loesung_freigeben": True, "abschliessen": True,
        "seiten": [{"id": seite_id, "annotationen": [{"t": "haken", "x": 10, "y": 10, "farbe": "#f00"}], "bild": data_url}]})
    assert r.get_json()["status"] == "korrigiert"

    # Lernende sehen Rückmeldung + Lösung
    seite = c.get(f"/lernende").get_data(as_text=True)
    assert "korrigiert" in seite
    rm = c.get(f"/blatt/{bid}/rueckmeldung.pdf")
    assert rm.status_code == 200 and "Weiter so!" in pdf_text(rm.data)
    assert c.get(f"/blatt/{bid}/loesung.pdf").status_code == 200
    assert c.get(f"/seite/{seite_id}.jpg?korrigiert=1").status_code == 200


def test_pruefungsgenerator_deckt_lernziele_ab(app):
    with app.app_context():
        qpcr = Thema.query.filter_by(name="qPCR").one()
        ziele = [lz.id for lz in qpcr.lernziele if lz.kuerzel in ("a9", "b16", "a7")]
        res = stelle_pruefung_zusammen(themen_ids=[qpcr.id], lernziel_ids=ziele, ziel_punkte=20, seed=1)
        assert not res["nicht_abgedeckt"]
        assert res["punkte"] <= 20 * 1.15
        assert all(a.verwendung in ("pruefung", "beide") for a in res["aufgaben"])
        nur = stelle_pruefung_zusammen(themen_ids=[qpcr.id], nur_pruefungsaufgaben=True, ziel_punkte=50, seed=1)
        assert {a.verwendung for a in nur["aufgaben"]} == {"pruefung"}


def test_pruefung_ueber_web_und_pdf(app):
    lp = app.test_client()
    login(lp, "lp", "lp-demo-2026")
    with app.app_context():
        ids = [t.id for t in Thema.query]
        klasse = User.query.filter_by(benutzername="lp").one().eigene_klassen[0].id
    r = lp.post("/lp/pruefungen/neu", data={"titel": "Test-Prüfung", "thema": ids, "bivo": ["b.5.6"],
                                            "ziel_punkte": "25", "klasse_id": klasse, "ohne_geuebte": "1",
                                            "dauer_min": "45"}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Test-Prüfung" in html and "Abdeckung der Ziele" in html
    pdf = lp.get("/lp/pruefungen/1/pruefung.pdf")
    text = pdf_text(pdf.data)
    assert "Test-Prüfung" in text and "Name" in text
    assert "Lösung" in pdf_text(lp.get("/lp/pruefungen/1/loesung.pdf").data)


def test_lernende_haben_keinen_lp_zugang(app):
    c = app.test_client()
    login(c, "lea", "lernen-2026")
    assert c.get("/lp/aufgaben").status_code == 403
    assert c.get("/lp/pruefungen/neu").status_code == 403


def test_aufgabe_anlegen_und_export(app):
    lp = app.test_client()
    login(lp, "lp", "lp-demo-2026")
    with app.app_context():
        lz = Lernziel.query.join(Thema).filter(Thema.name == "qPCR", Lernziel.bereich == "a", Lernziel.nummer == 13).one().id
    r = lp.post("/lp/aufgaben/neu", data={"titel": "Ökologie der Verbrauchsmaterialien", "text": "a) Nenne **zwei** Punkte.",
                                          "loesung": "Filterspitzen …", "punkte": "3", "k_stufe": "2", "lernziel": lz,
                                          "neues_thema": "Nachhaltigkeit", "antwortformat": "linien",
                                          "antwortraum_cm": "4", "verwendung": "beide", "aktiv": "1"},
                follow_redirects=True)
    assert "Aufgabe gespeichert" in r.get_data(as_text=True)
    daten = json.loads(lp.get("/lp/aufgaben/export.json").data)
    neu = [d for d in daten if d["titel"].startswith("Ökologie")][0]
    assert neu["leistungsziele"] == ["a.3.1"] and set(neu["themen"]) == {"Nachhaltigkeit"}


def test_csrf_schutz(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/c.sqlite", "UPLOAD_DIR": str(tmp_path / "d")})
    assert app.test_client().post("/login", data={"benutzername": "x", "passwort": "y"}).status_code == 400


# ---------------------------------------------------------------- Grafiken in Aufgaben

def _bild(farbe, groesse=(400, 300)):
    buf = io.BytesIO()
    Image.new("RGB", groesse, farbe).save(buf, "PNG")
    buf.seek(0)
    return buf


def _anzahl_bilder(pdf_bytes):
    return sum(len(p.images) for p in PdfReader(io.BytesIO(pdf_bytes)).pages)


def test_mehrere_bilder_platziert_und_nur_loesung(app):
    from app.models import AufgabeBild
    lp = app.test_client()
    login(lp, "lp", "lp-demo-2026")
    basis = {"titel": "Gel auswerten", "punkte": "4", "k_stufe": "3", "antwortformat": "linien",
             "antwortraum_cm": "4", "verwendung": "beide", "aktiv": "1", "neues_thema": "Gelelektrophorese"}
    r = lp.post("/lp/aufgaben/neu", data={**basis, "text": "Schau dir das Gel an.", "loesung": "Siehe Bild.",
                                          "bilder_neu": [(_bild("red"), "gel.png"), (_bild("blue"), "marker.png")],
                                          "neu_groesse": "halb"},
                content_type="multipart/form-data", follow_redirects=True)
    assert "Aufgabe gespeichert" in r.get_data(as_text=True)
    with app.app_context():
        a = Aufgabe.query.filter_by(titel="Gel auswerten").one()
        assert [(b.nr, b.groesse) for b in a.bilder] == [(1, "halb"), (2, "halb")]
        aid, b1, b2 = a.id, a.bilder[0].id, a.bilder[1].id
    # drittes Bild nur für die Lösung, Bilder 1+2 nebeneinander, Bild 3 in der Lösung platziert, Tippfehler-Marker
    r = lp.post(f"/lp/aufgaben/{aid}", data={
        **basis, "text": "Schau dir das Gel an.\n[[bild:1]] [[bild:2|drittel]]\nWelche Bande ist das Produkt?\n[[bild:7]]",
        "loesung": "Bande bei 500 bp:\n[[bild:3]]", f"bild_{b1}_groesse": "halb", f"bild_{b1}_text": "Agarosegel 1 %",
        f"bild_{b2}_groesse": "halb", "bilder_neu": [(_bild("green"), "loesung.png")], "neu_loesung": "1"},
        content_type="multipart/form-data", follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "[[bild:7]] verweist auf ein Bild, das es nicht gibt" in html
    with app.app_context():
        a = db.session.get(Aufgabe, aid)
        assert [(b.nr, b.nur_loesung) for b in a.bilder] == [(1, False), (2, False), (3, True)]
        assert a.bilder[0].beschriftung == "Agarosegel 1 %"
        from app.lernende import bild_pfad
        from app import pdfgen
        from datetime import datetime
        with db.session.no_autoflush:
            blatt = Uebungsblatt(id=9999, lernende=User.query.filter_by(benutzername="lea").one(), titel="Gel",
                                 erstellt_am=datetime(2026, 11, 16))
            from app.models import BlattAufgabe
            blatt.aufgaben.append(BlattAufgabe(aufgabe=a, position=1))
            aufgabenblatt = pdfgen.uebungsblatt_pdf(blatt, bild_pfad)
            loesungsblatt = pdfgen.uebungsblatt_pdf(blatt, bild_pfad, loesung=True)
        db.session.rollback()
    assert _anzahl_bilder(aufgabenblatt) == 2          # Lösungsbild ist NICHT auf dem Aufgabenblatt
    assert _anzahl_bilder(loesungsblatt) == 3
    assert "Agarosegel 1 %" in pdf_text(aufgabenblatt)
    assert "[[bild" not in pdf_text(aufgabenblatt)

    # Bild löschen: Nummern der übrigen bleiben stabil
    lp.post(f"/lp/aufgaben/{aid}", data={**basis, "text": "x", "loesung": "y", f"bild_{b1}_loeschen": "1",
                                          f"bild_{b2}_groesse": "voll"}, content_type="multipart/form-data")
    with app.app_context():
        assert [b.nr for b in db.session.get(Aufgabe, aid).bilder] == [2, 3]
        bid = AufgabeBild.query.first().id
    # Lernende kommen nicht an die Bilddateien heran
    c = app.test_client()
    login(c, "lea", "lernen-2026")
    assert c.get(f"/lp/aufgabenbild/{bid}").status_code == 403
    assert lp.get(f"/lp/aufgabenbild/{bid}").status_code == 200


def test_bildzeile_skaliert_nebeneinander():
    from types import SimpleNamespace
    import tempfile, os
    from app.pdfgen import CONTENT_W, _bildzeile, _styles
    d = tempfile.mkdtemp()
    pfade = []
    for i, f in enumerate(["red", "blue", "green"]):
        p = os.path.join(d, f"{i}.png")
        Image.new("RGB", (800, 400), f).save(p)
        pfade.append(p)
    bilder = [SimpleNamespace(groesse="halb", beschriftung="", p=p) for p in pfade]
    t = _bildzeile([(b, None) for b in bilder], _styles(), CONTENT_W, lambda b: b.p)
    assert sum(t._colWidths) <= CONTENT_W + 0.01   # 3 × halb passt nicht → wird verkleinert
    t2 = _bildzeile([(bilder[0], "viertel")], _styles(), CONTENT_W, lambda b: b.p)
    assert abs(t2._colWidths[0] - CONTENT_W / 4) < 0.01


def test_altes_einzelbild_wird_migriert(app):
    from app.models import migriere_einzelbilder
    with app.app_context():
        a = Aufgabe.query.first()
        a.bild = "aufgabenbilder/alt.jpg"
        db.session.commit()
        migriere_einzelbilder()
        a = db.session.get(Aufgabe, a.id)
        assert a.bild is None and [(b.nr, b.datei) for b in a.bilder] == [(1, "aufgabenbilder/alt.jpg")]


# ---------------------------------------------------------------- Editor: Live-Vorschau & Bildnummern

def test_live_vorschau(app):
    lp = app.test_client()
    login(lp, "lp", "lp-demo-2026")
    r = lp.post("/lp/aufgaben/vorschau", json={"text": "H_{2}O und **fett**\n[[bild:4|halb]]", "loesung": "| A | B |\n| 1 | 2 |"})
    d = r.get_json()
    assert "<sub>2</sub>" in d["aufgabe"] and "<b>fett</b>" in d["aufgabe"]
    assert 'class="platzhalter" data-nr="4"' in d["aufgabe"]          # noch nicht gespeichertes Bild
    assert "<table" in d["loesung"]
    c = app.test_client()
    login(c, "lea", "lernen-2026")
    assert c.post("/lp/aufgaben/vorschau", json={"text": "x"}).status_code == 403


def test_neue_bildnummern_bleiben_bei_gleichzeitigem_loeschen(app):
    """Der Editor sagt Nummern neuer Bilder voraus (max+1); das muss auch gelten, wenn im selben
    Speichervorgang das Bild mit der höchsten Nummer gelöscht wird."""
    lp = app.test_client()
    login(lp, "lp", "lp-demo-2026")
    basis = {"titel": "Nummern", "text": "t", "loesung": "l", "punkte": "1", "antwortformat": "linien",
             "antwortraum_cm": "2", "verwendung": "beide", "aktiv": "1"}
    lp.post("/lp/aufgaben/neu", data={**basis, "bilder_neu": [(_bild("red"), "a.png"), (_bild("blue"), "b.png")]},
            content_type="multipart/form-data")
    with app.app_context():
        a = Aufgabe.query.filter_by(titel="Nummern").one()
        aid, hoechstes = a.id, a.bilder[-1].id
    lp.post(f"/lp/aufgaben/{aid}", data={**basis, "text": "[[bild:3]]", f"bild_{hoechstes}_loeschen": "1",
                                          "bilder_neu": [(_bild("green"), "c.png")]}, content_type="multipart/form-data")
    with app.app_context():
        assert [b.nr for b in db.session.get(Aufgabe, aid).bilder] == [1, 3]


# ---------------------------------------------------------------- Aufgabentypen & variable Zahlen

def test_formeln_sicher_und_zahlen_schweizerisch():
    from app.aufgabentypen import FormelFehler, formel_auswerten, zahl
    assert formel_auswerten("n * 2 * 10^4", {"n": 54}) == 1080000
    assert abs(formel_auswerten("10^(1/3,45) - 1", {}) - 0.9492) < 1e-3       # Dezimalkomma erlaubt
    assert formel_auswerten("log10(1000) + sqrt(16)", {}) == 7
    for boese in ["__import__('os')", "open('x')", "n.__class__", "(lambda: 1)()", "9**9**9"]:
        with pytest.raises(FormelFehler):
            formel_auswerten(boese, {"n": 1})
    assert zahl(1080000) == "1,08 · 10^{6}" and zahl(4.62962) == "4,63" and zahl(54.0) == "54"
    assert zahl(0.000123) == "1,23 · 10^{-4}" and zahl(12216.77) == "12200"


def test_rechenaufgabe_gleiche_zahlen_in_aufgabe_und_loesung(app):
    from app.aufgabentypen import rendern
    with app.app_context():
        a = Aufgabe.query.filter_by(typ="rechnung").first()
        g1, g1b, g2 = rendern(a, 11), rendern(a, 11), rendern(a, 12)
        assert g1.text == g1b.text and g1.loesung == g1b.loesung      # deterministisch pro Seed
        assert g1.text != g2.text                                       # andere Zahlen bei anderem Seed
        w = g1.werte
        assert f"{w['z1']}, {w['z2']}, {w['z3']} und {w['z4']}" in g1.text
        assert abs(w["c"] - (w["z1"] + w["z2"] + w["z3"] + w["z4"]) / 4 * w["vf"] * 1e4) < 1e-6
        assert "{" not in g1.text.replace("^{4}", "") and not g1.fehler


def test_mc_zuordnung_luecken(app):
    from app.aufgabentypen import rendern
    with app.app_context():
        mc = Aufgabe.query.filter_by(typ="mc").first()
        for seed in range(1, 6):
            g = rendern(mc, seed)
            optionen = [z for z in g.text.splitlines() if z.startswith("☐")]
            richtig = g.loesung.splitlines()[0].removeprefix("Richtig: ").split(", ")
            # die als richtig gemeldeten Buchstaben zeigen auf die richtigen Aussagen
            for b in richtig:
                text = next(o for o in optionen if o.startswith(f"☐ {b})"))[5:]
                assert any(opt["korrekt"] and opt["text"] == text for opt in json.loads(mc.daten)["optionen"])
        zu = rendern(Aufgabe.query.filter_by(typ="zuordnung").first(), 3)
        assert zu.text.count("\n| ") == 5 and "**" in zu.loesung   # Kopf + 4 Paare
        lu = rendern(Aufgabe.query.filter_by(typ="luecken").first(), 3)
        assert "{{" not in lu.text and "(5)" in lu.text and "Wortliste" in lu.text
        assert "**Denaturierung**" in lu.loesung and "**95 °C / 94 °C**" in lu.loesung


def test_uebungsblaetter_mit_variablen_zahlen(app):
    """Zwei Lernende erhalten dieselbe Rechenaufgabe mit verschiedenen Zahlen; die Lösungen passen dazu."""
    with app.app_context():
        a = Aufgabe.query.filter_by(typ="rechnung").first()
        thema = a.themen[0].id
        a_id = a.id
    texte = []
    for wer in ("lea", "noah"):
        c = app.test_client()
        login(c, wer, "lernen-2026")
        c.post("/lernende/neu", data={"thema": thema, "anzahl": 10})
        with app.app_context():
            blatt = Uebungsblatt.query.join(User).filter(User.benutzername == wer).order_by(Uebungsblatt.id.desc()).first()
            ba = next(x for x in blatt.aufgaben if x.aufgabe_id == a_id)
            assert ba.seed
            from app.aufgabentypen import rendern
            g = rendern(ba.aufgabe, ba.seed)
            bid = blatt.id
        lp = app.test_client()
        login(lp, "lp", "lp-demo-2026")
        aufg = pdf_text(c.get(f"/blatt/{bid}/aufgaben.pdf").data)
        loes = pdf_text(lp.get(f"/blatt/{bid}/loesung.pdf").data)
        from app.aufgabentypen import zahl
        assert str(g.werte["z1"]) in aufg and zahl(g.werte["m"], 3) in loes
        texte.append(g.text)
    assert texte[0] != texte[1]


def test_spalten_werden_nachgetragen(tmp_path):
    """Eine Datenbank aus einer früheren Version (ohne typ/daten/seed) wird beim Start ergänzt."""
    import sqlite3
    pfad = tmp_path / "alt.sqlite"
    konfig = {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{pfad}", "UPLOAD_DIR": str(tmp_path / "d")}
    app = create_app(konfig)
    with app.app_context():
        db.session.add(Aufgabe(titel="alt", text="t", loesung="l", punkte=1))
        db.session.commit()
        db.engine.dispose()
    con = sqlite3.connect(pfad)
    for tabelle, spalte in [("aufgabe", "typ"), ("aufgabe", "daten"), ("blatt_aufgabe", "seed"), ("pruefung_aufgabe", "seed")]:
        con.execute(f"ALTER TABLE {tabelle} DROP COLUMN {spalte}")
    con.commit(); con.close()
    app = create_app(konfig)
    with app.app_context():
        a = Aufgabe.query.one()
        assert a.typ == "frei" and a.daten == "{}"


# ---------------------------------------------------------------- KI-Assistent (mit simuliertem API-Client)

from types import SimpleNamespace


class FakeClaude:
    """Ersetzt anthropic.Anthropic: zeichnet Anfragen auf und liefert vorbereitete JSON-Antworten."""

    def __init__(self, antworten, stop_reason="end_turn"):
        self.antworten, self.anfragen, self.stop_reason = list(antworten), [], stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.anfragen.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(self.antworten.pop(0)))],
                               stop_reason=self.stop_reason, model=kw["model"],
                               usage=SimpleNamespace(input_tokens=1200, output_tokens=800,
                                                     cache_read_input_tokens=0, cache_creation_input_tokens=3000))


@pytest.fixture
def ki_app(app, monkeypatch):
    app.config["ANTHROPIC_API_KEY"] = "sk-test"
    return app


def _lp_client(app):
    c = app.test_client()
    login(c, "lp", "lp-demo-2026")
    return c


def test_ki_standby_ohne_schluessel(app, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    lp = _lp_client(app)
    r = lp.post("/lp/ki/entwurf", json={"wunsch": "x"})
    assert r.status_code == 503 and "nicht aktiviert" in r.get_json()["fehler"]
    seite = lp.get("/lp/aufgaben/neu").get_data(as_text=True)
    assert "KI-Assistent nicht aktiviert" in seite and 'id="ki-panel"' not in seite
    assert "So wird er eingeschaltet" in lp.get("/lp/ki").get_data(as_text=True)


def test_ki_entwurf_anfrage_und_validierung(ki_app, monkeypatch):
    from app import ki
    antwort = {"titel": "Verdünnung berechnen", "typ": "rechnung",
               "text": "Verdünne {v} µL Stammlösung (c = {c0} mM) auf {ve} µL. Welche Konzentration entsteht?",
               "loesung": "c = {c0} × {v} / {ve} = **{c} mM** (2 P.)",
               "daten_json": json.dumps({"variablen": [{"name": "v", "min": 10, "max": 50, "schritt": 5},
                                                       {"name": "c0", "min": 10, "max": 100, "schritt": 10},
                                                       {"name": "ve", "min": 500, "max": 1000, "schritt": 100}],
                                         "ergebnisse": [{"name": "c", "formel": "c0 * v / ve", "stellen": 3}]}),
               "punkte": 2, "k_stufe": 3, "antwortformat": "karo", "antwortraum_cm": 5, "kommentar": "Annahme: Wasser"}
    fake = FakeClaude([antwort])
    monkeypatch.setattr(ki, "_client", lambda: fake)
    lp = _lp_client(ki_app)
    assert 'id="ki-panel"' in lp.get("/lp/aufgaben/neu").get_data(as_text=True)
    with ki_app.app_context():
        lz = Lernziel.query.join(Thema).filter(Thema.name == "qPCR", Lernziel.bereich == "a", Lernziel.nummer == 9).one()
        lz_id, lz_text = lz.id, lz.text
    r = lp.post("/lp/ki/entwurf", json={"lernziele": [lz_id], "typ": "rechnung", "k_stufe": "3", "wunsch": "einfach"})
    d = r.get_json()
    assert r.status_code == 200 and d["aufgabe"]["typ"] == "rechnung" and d["hinweise"] == []
    assert d["aufgabe"]["daten"]["ergebnisse"][0]["formel"] == "c0 * v / ve"
    kw = fake.anfragen[0]
    assert kw["model"] == "claude-opus-5-5" and kw["fallbacks"] == "default"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert kw["output_config"]["format"]["type"] == "json_schema" and kw["output_config"]["effort"] == "medium"
    assert lz_text in kw["messages"][0]["content"] and "ß" in kw["system"]           # Lernziel + Rechtschreibregel
    assert "Lea" not in json.dumps(kw, ensure_ascii=False)                              # keine Lernendendaten
    from app.models import KiProtokoll
    with ki_app.app_context():
        p = KiProtokoll.query.one()
        assert (p.aktion, p.input_tokens, p.output_tokens, p.cache_schreiben) == ("entwurf", 1200, 800, 3000)
    seite = lp.get("/lp/ki").get_data(as_text=True)
    assert "aktiv" in seite and "Dieser Monat" in seite


def test_ki_fehlerhafte_formel_wird_gemeldet(ki_app, monkeypatch):
    from app import ki
    kaputt = {"titel": "x", "typ": "rechnung", "text": "{a}", "loesung": "{b}",
              "daten_json": json.dumps({"variablen": [{"name": "a", "min": 0, "max": 2, "schritt": 1}],
                                        "ergebnisse": [{"name": "b", "formel": "1 / a", "stellen": 3}]}),
              "punkte": 99, "k_stufe": 3, "antwortformat": "unbekannt", "antwortraum_cm": 5, "kommentar": ""}
    monkeypatch.setattr(ki, "_client", lambda: FakeClaude([kaputt]))
    d = _lp_client(ki_app).post("/lp/ki/entwurf", json={"wunsch": "x"}).get_json()
    assert any("Division durch null" in h for h in d["hinweise"])
    assert d["aufgabe"]["punkte"] == 50 and d["aufgabe"]["antwortformat"] == "linien"     # Werte begrenzt


def test_ki_tags_nur_aus_katalog(ki_app, monkeypatch):
    from app import ki
    fake = FakeClaude([{"themen": ["qPCR", "Erfunden"], "lernziele": ["qPCR a9", "qPCR z99"],
                        "bivo": ["a.2.3", "x.9.9"], "k_stufe": 3, "begruendung": "Rechnung"}])
    monkeypatch.setattr(ki, "_client", lambda: fake)
    d = _lp_client(ki_app).post("/lp/ki/tags", json={"text": "Master-Mix berechnen", "loesung": ""}).get_json()
    with ki_app.app_context():
        qpcr = Thema.query.filter_by(name="qPCR").one()
        a9 = next(l.id for l in qpcr.lernziele if l.kuerzel == "a9")
        assert d["themen"] == [qpcr.id] and d["lernziele"] == [a9] and d["bivo"] == ["a.2.3"]
    assert fake.anfragen[0]["output_config"]["effort"] == "low"
    assert "qPCR a15:" in fake.anfragen[0]["system"]                                   # Katalog im (gecachten) System-Prompt


def test_ki_pruefen_und_ablehnung(ki_app, monkeypatch):
    from app import ki
    befund = {"urteil": "fehler_gefunden", "zusammenfassung": "Rechenfehler",
              "befunde": [{"schwere": "fehler", "bereich": "loesung", "beschreibung": "0,4 × 20 / 10 = 0,8, nicht 8",
                           "vorschlag": "korrigieren"}]}
    fake = FakeClaude([befund])
    monkeypatch.setattr(ki, "_client", lambda: fake)
    lp = _lp_client(ki_app)
    with ki_app.app_context():
        a = Aufgabe.query.filter_by(typ="rechnung").first().to_dict()
    d = lp.post("/lp/ki/pruefen", json=a).get_json()
    assert d["urteil"] == "fehler_gefunden" and fake.anfragen[0]["output_config"]["effort"] == "high"
    assert "Gerenderte Variante 1" in fake.anfragen[0]["messages"][0]["content"]       # konkrete Zahlen zum Nachrechnen
    monkeypatch.setattr(ki, "_client", lambda: FakeClaude([befund], stop_reason="refusal"))
    r = lp.post("/lp/ki/pruefen", json=a)
    assert r.status_code == 502 and "abgelehnt" in r.get_json()["fehler"]


def test_variante_als_neue_aufgabe_mit_bildern(app):
    lp = _lp_client(app)
    basis = {"titel": "Original", "text": "Gel [[bild:1]]", "loesung": "l", "punkte": "2", "antwortformat": "linien",
             "antwortraum_cm": "3", "verwendung": "beide", "aktiv": "1"}
    lp.post("/lp/aufgaben/neu", data={**basis, "bilder_neu": [(_bild("red"), "gel.png")]}, content_type="multipart/form-data")
    with app.app_context():
        orig = Aufgabe.query.filter_by(titel="Original").one()
        oid = orig.id
    lp.post("/lp/aufgaben/neu", data={**basis, "titel": "Variante (KI)", "bilder_von": oid}, content_type="multipart/form-data")
    with app.app_context():
        v = Aufgabe.query.filter_by(titel="Variante (KI)").one()
        assert [b.nr for b in v.bilder] == [1] and v.id != oid
        assert len(db.session.get(Aufgabe, oid).bilder) == 1


def test_lernziel_vorauswahl_im_editor(app):
    lp = _lp_client(app)
    with app.app_context():
        lz = Lernziel.query.first()
        lz_id, th_id = lz.id, lz.thema_id
    html = lp.get(f"/lp/aufgaben/neu?lernziel={lz_id}").get_data(as_text=True)
    assert f'name="lernziel" value="{lz_id}" checked' in html and f'name="thema" value="{th_id}" checked' in html


# ---------------------------------------------------------------- Sicherheit

def test_login_sperre_nach_fehlversuchen(app):
    c = app.test_client()
    for _ in range(5):
        r = c.post("/login", data={"benutzername": "lea", "passwort": "falsch"})
        assert r.status_code == 200
    r = c.post("/login", data={"benutzername": "lea", "passwort": "lernen-2026"})   # richtig, aber gesperrt
    assert r.status_code == 429 and "Zu viele Fehlversuche" in r.get_data(as_text=True)
    # anderes Konto ist nicht betroffen
    assert "Meine Übungsblätter" in login(app.test_client(), "noah", "lernen-2026").get_data(as_text=True)


def test_sperre_pro_ip(app):
    c = app.test_client()
    for i in range(20):
        c.post("/login", data={"benutzername": f"gibtsnicht{i}", "passwort": "x"})
    assert c.post("/login", data={"benutzername": "noah", "passwort": "lernen-2026"}).status_code == 429


def test_sicherheits_header_und_offene_weiterleitung(app):
    c = app.test_client()
    r = c.get("/login")
    csp = r.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "unsafe-inline" not in csp.split("style-src")[0]
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Content-Type-Options"] == "nosniff"
    for boese in ["//boese.example", "https://boese.example", "/\\boese.example"]:
        r = c.post(f"/login?next={boese}", data={"benutzername": "lea", "passwort": "lernen-2026"})
        assert r.headers["Location"] in ("/", "http://localhost/")
    assert app.test_client().get("/lp/").headers.get("Cache-Control") != "no-store"  # nur angemeldete Seiten
    lp = app.test_client(); login(lp, "lp", "lp-demo-2026")
    assert lp.get("/lp/").headers["Cache-Control"] == "no-store"


def test_keine_inline_skripte_in_vorlagen():
    """Die CSP verbietet Inline-Skripte – Vorlagen dürfen keine enthalten."""
    import glob, re
    for p in glob.glob("app/templates/**/*.html", recursive=True):
        s = open(p, encoding="utf-8").read()
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", s), p
        assert not re.search(r"\son(click|submit|change|load|input)=", s), p


def test_secure_cookie_bei_https(tmp_path, monkeypatch):
    monkeypatch.setenv("LERNREAKTOR_HTTPS", "1")
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/h.sqlite", "UPLOAD_DIR": str(tmp_path / "d")})
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert "Strict-Transport-Security" in app.test_client().get("/login").headers


def test_startpasswort_muss_geaendert_werden(app):
    lp = app.test_client(); login(lp, "lp", "lp-demo-2026")
    with app.app_context():
        klasse_id = User.query.filter_by(benutzername="lp").one().eigene_klassen[0].id
    html = lp.post(f"/lp/klassen/{klasse_id}", data={"namen": "Mia Neu"}).get_data(as_text=True)
    import re
    pw = re.search(r'mia\.neu</td><td><span class="pw">([a-z0-9]+)</span>', html)[1]
    c = app.test_client()
    r = login(c, "mia.neu", pw)
    assert "eigenes Passwort" in r.get_data(as_text=True)                  # direkt zur Passwortänderung
    assert c.get("/lernende/neu").status_code == 302                        # alles andere gesperrt
    assert c.post("/lernende/neu", data={"anzahl": 1}).status_code == 403
    r = c.post("/passwort", data={"alt": pw, "neu": pw, "neu2": pw}, follow_redirects=True)
    assert "unterscheiden" in r.get_data(as_text=True)
    c.post("/passwort", data={"alt": pw, "neu": "neues-passwort-1", "neu2": "neues-passwort-1"})
    assert c.get("/lernende/neu").status_code == 200


def test_abmeldung_nach_inaktivitaet(app):
    c = app.test_client(); login(c, "lea", "lernen-2026")
    assert c.get("/lernende").status_code == 200
    with c.session_transaction() as s:
        s["zuletzt"] -= 61 * 60
    r = c.get("/lernende")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert c.get("/lernende").status_code == 302                             # wirklich abgemeldet


def test_csrf_konstante_zeit_und_neue_sitzung_beim_login(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/c2.sqlite", "UPLOAD_DIR": str(tmp_path / "d")})
    with app.app_context():
        seed_basisdaten(); seed_demo()
    c = app.test_client()
    import re
    tok = re.search(r'name="_csrf" value="([^"]+)"', c.get("/login").get_data(as_text=True))[1]
    assert c.post("/login", data={"benutzername": "lea", "passwort": "lernen-2026", "_csrf": tok[:-1] + "x"}).status_code == 400
    c.post("/login", data={"benutzername": "lea", "passwort": "lernen-2026", "_csrf": tok})
    with c.session_transaction() as s:
        assert s.get("_csrf") != tok                                           # Sitzung beim Login erneuert
    import inspect
    from app import sicherheit
    assert "compare_digest" in inspect.getsource(sicherheit.csrf_pruefen)


# ---------------------------------------------------------------- Kamera-Upload

def _blatt_fuer(app, client):
    with app.app_context():
        qpcr = Thema.query.filter_by(name="qPCR").one().id
    client.post("/lernende/neu", data={"thema": qpcr, "anzahl": 2})
    with app.app_context():
        return Uebungsblatt.query.order_by(Uebungsblatt.id.desc()).first().id


def _jpeg(farbe="white"):
    buf = io.BytesIO()
    Image.new("RGB", (600, 850), farbe).save(buf, "JPEG")
    buf.seek(0)
    return buf


def test_kamera_upload_mehrere_seiten_als_eine_abgabe(app):
    c = app.test_client()
    login(c, "lea", "lernen-2026")
    bid = _blatt_fuer(app, c)
    seite = c.get(f"/blatt/{bid}").get_data(as_text=True)
    assert 'capture="environment"' in seite and "kamera.js" in seite
    r = c.post(f"/blatt/{bid}/hochladen", headers={"X-Requested-With": "fetch"}, content_type="multipart/form-data",
               data={"dateien": [(_jpeg(), "seite-1.jpg"), (_jpeg("gray"), "seite-2.jpg"), (_jpeg(), "seite-3.jpg")]})
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["ziel"] == f"/blatt/{bid}"
    with app.app_context():
        b = db.session.get(Uebungsblatt, bid)
        assert b.status == "eingereicht" and len(b.abgaben) == 1 and [s.nr for s in b.abgaben[0].seiten] == [1, 2, 3]
    # Fehler kommen per fetch als JSON zurück
    r = c.post(f"/blatt/{bid}/hochladen", headers={"X-Requested-With": "fetch"}, content_type="multipart/form-data",
               data={})
    assert r.status_code == 400 and not r.get_json()["ok"]


def test_qr_code_auf_uebungsblatt(app):
    app.config["BASIS_URL"] = "https://lernreaktor.example.ch/"
    c = app.test_client()
    login(c, "lea", "lernen-2026")
    bid = _blatt_fuer(app, c)
    pdf = c.get(f"/blatt/{bid}/aufgaben.pdf").data
    assert "QR-Code" in pdf_text(pdf)
    from app.lernende import upload_url
    with app.test_request_context("/"):
        assert upload_url(db.session.get(Uebungsblatt, bid)) == f"https://lernreaktor.example.ch/blatt/{bid}"


# ---------------------------------------------------------------- Kompetenzniveau

def _korrigieren(app, lp, bid, punkte_fn, niveaus=None):
    with app.app_context():
        blatt = db.session.get(Uebungsblatt, bid)
        aufg = [{"id": ba.id, "punkte": str(punkte_fn(ba)), "kommentar": "",
                 "niveau": (niveaus or {}).get(ba.position, "")} for ba in blatt.aufgaben]
    return lp.post(f"/lp/korrektur/{bid}", json={"aufgaben": aufg, "abschliessen": True, "seiten": []})


def test_niveau_aus_punkten_und_von_hand(app):
    from app.models import BlattAufgabe, niveau_aus_punkten
    assert [niveau_aus_punkten(e, 10) for e in (0, 4.9, 5, 7.9, 8, 10)] == [1, 1, 2, 2, 3, 3]
    assert niveau_aus_punkten(None, 10) is None
    c, lp = app.test_client(), app.test_client()
    login(c, "lea", "lernen-2026")
    login(lp, "lp", "lp-demo-2026")
    bid = _blatt_fuer(app, c)
    seite = lp.get(f"/lp/korrektur/{bid}").get_data(as_text=True)
    assert 'class="niveau"' in seite and "Instruktor" in seite
    # Aufgabe 1 von Hand auf Instruktor, Aufgabe 2 ohne Angabe → aus den Punkten (volle Punktzahl → 3)
    r = _korrigieren(app, lp, bid, lambda ba: ba.aufgabe.punkte, {1: "4"})
    assert r.get_json()["status"] == "korrigiert"
    with app.app_context():
        assert [ba.niveau for ba in db.session.get(Uebungsblatt, bid).aufgaben] == [4, 3]


def test_kompetenzstand_regeln(app):
    from datetime import datetime
    from app.kompetenzstand import Stand
    t = [datetime(2026, 1, d) for d in range(1, 8)]
    assert Stand().niveau is None
    assert Stand([(t[0], 1), (t[1], 2)]).niveau == 2                       # 1.5 → 2
    assert Stand([(t[0], 1), (t[1], 1), (t[2], 3), (t[3], 3)]).niveau == 2  # nur die letzten 3: 1,3,3 → 2.33
    assert Stand([(t[0], 4), (t[1], 3)]).niveau == 3                       # Instruktor nur, wenn zuletzt
    assert Stand([(t[0], 3), (t[1], 3), (t[2], 4)]).niveau == 4
    assert Stand([(t[0], 4), (t[1], 4), (t[2], 3)]).niveau == 3            # Durchschnitt 3.67 → höchstens 3


def test_kompetenzmatrix_der_klasse(app):
    from app.kompetenzstand import kompetenzstand
    c, lp = app.test_client(), app.test_client()
    login(c, "lea", "lernen-2026")
    login(lp, "lp", "lp-demo-2026")
    bid = _blatt_fuer(app, c)
    _korrigieren(app, lp, bid, lambda ba: 0)  # keine Punkte → Gestartet
    with app.app_context():
        lea = User.query.filter_by(benutzername="lea").one()
        blatt = db.session.get(Uebungsblatt, bid)
        erwartet = {l.code for ba in blatt.aufgaben for l in ba.aufgabe.leistungsziele}
        erwartet |= {l.code for ba in blatt.aufgaben for lz in ba.aufgabe.lernziele for l in lz.leistungsziele}
        ks = kompetenzstand([lea.id])[lea.id]
        assert set(ks["ziele"]) == erwartet and all(s.niveau == 1 for s in ks["ziele"].values())
        assert "qPCR" in ks["themen"]
        klasse_id, lea_id = lea.klasse_id, lea.id
    seite = lp.get(f"/lp/klassen/{klasse_id}/kompetenzen").get_data(as_text=True)
    code = sorted(erwartet)[0]
    assert f"Lea Muster · {code}: Gestartet (" in seite and "noch nicht bearbeitet" in seite
    assert "Lea Muster · qPCR: Gestartet" in lp.get(f"/lp/klassen/{klasse_id}/kompetenzen?ansicht=themen").get_data(as_text=True)
    assert "Kompetenzziele (BiVo)" in lp.get(f"/lp/lernende/{lea_id}").get_data(as_text=True)
    # Lernende haben keinen Zugang, andere LP sehen fremde Klassen nicht
    assert c.get(f"/lp/klassen/{klasse_id}/kompetenzen").status_code == 403
    with app.app_context():
        fremd = User(benutzername="lp2", anzeigename="LP 2", rolle="lp")
        fremd.set_passwort("lp2-passwort-2026")
        db.session.add(fremd)
        db.session.commit()
    lp2 = app.test_client()
    login(lp2, "lp2", "lp2-passwort-2026")
    assert lp2.get(f"/lp/klassen/{klasse_id}/kompetenzen").status_code == 403
