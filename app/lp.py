"""Bereich der Lehrpersonen: Klassen, Korrektur, Aufgabenverwaltung, Lernziele, Prüfungen."""
import base64
import io
import json
import re
import secrets
from collections import Counter
from types import SimpleNamespace

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, url_for)
from flask_login import current_user
from PIL import Image

from . import importers, pdfgen, storage
from .aufgabentypen import TYPEN, neuer_seed, pruefen, rendern, zahl
from .kompetenzstand import kompetenzstand
from .markup import bild_warnungen
from .auth import lp_required
from .lernende import auswahl_aus_request, bild_pfad, blatt_pdf_rel
from .models import (ANTWORTFORMATE, BILDGROESSEN, VERWENDUNGEN, Aufgabe, AufgabeBild, AbgabeSeite, Bereich, Klasse, Leistungsziel,
                     Lernziel, NIVEAUS, Pruefung, PruefungAufgabe, Thema, TheorieDokument, TheorieKapitel, Uebungsblatt,
                     User, db, niveau_aus_punkten,
                     now)
from .selection import (geuebte_aufgaben_der_klasse, stelle_pruefung_zusammen, ziele_beschreiben)

bp = Blueprint("lp", __name__, url_prefix="/lp")


def meine_lernende_ids():
    return [u.id for k in current_user.eigene_klassen for u in k.lernende]


def pruefe_klasse(klasse):
    if klasse.lp_id != current_user.id:
        abort(403)


def pruefe_lernende(u):
    if not current_user.betreut(u):
        abort(403)


# ---------------------------------------------------------------- Übersicht

@bp.route("/")
@lp_required
def dashboard():
    ids = meine_lernende_ids()
    offen = (Uebungsblatt.query.filter(Uebungsblatt.lernende_id.in_(ids), Uebungsblatt.status == "eingereicht")
             .order_by(Uebungsblatt.erstellt_am).all()) if ids else []
    letzte = (Uebungsblatt.query.filter(Uebungsblatt.lernende_id.in_(ids))
              .order_by(Uebungsblatt.erstellt_am.desc()).limit(10).all()) if ids else []
    stats = {"aufgaben": Aufgabe.query.filter_by(aktiv=True).count(), "themen": Thema.query.count(),
             "lernziele": Lernziel.query.count(), "pruefungen": Pruefung.query.filter_by(lp_id=current_user.id).count()}
    from .lp_review import offene_aufgaben
    return render_template("lp/dashboard.html", offen=offen, letzte=letzte, stats=stats, review=offene_aufgaben())


# ---------------------------------------------------------------- Klassen & Lernende

@bp.route("/klassen", methods=["GET", "POST"])
@lp_required
def klassen():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            db.session.add(Klasse(name=name, lp=current_user))
            db.session.commit()
            flash(f"Klasse {name} erstellt.", "ok")
        return redirect(url_for(".klassen"))
    return render_template("lp/klassen.html", klassen=current_user.eigene_klassen)


def _benutzername(name):
    basis = re.sub(r"[^a-z0-9]+", ".", name.lower()
                   .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("é", "e").replace("è", "e")
                   ).strip(".")[:40] or "user"
    kandidat, i = basis, 1
    while User.query.filter_by(benutzername=kandidat).first():
        i += 1
        kandidat = f"{basis}{i}"
    return kandidat


def _passwort():
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(10))


@bp.route("/klassen/<int:klasse_id>", methods=["GET", "POST"])
@lp_required
def klasse(klasse_id):
    k = db.get_or_404(Klasse, klasse_id)
    pruefe_klasse(k)
    neue_zugaenge = []
    if request.method == "POST":
        for zeile in request.form.get("namen", "").splitlines():
            name = zeile.strip()
            if not name:
                continue
            u = User(benutzername=_benutzername(name), anzeigename=name, rolle="lernende", klasse=k,
                     passwort_aendern=True)
            pw = _passwort()
            u.set_passwort(pw)
            db.session.add(u)
            neue_zugaenge.append((name, u.benutzername, pw))
        db.session.commit()
        if neue_zugaenge:
            flash(f"{len(neue_zugaenge)} Zugänge erstellt. Passwörter jetzt notieren – sie werden nicht erneut angezeigt.", "ok")
    return render_template("lp/klasse.html", klasse=k, neue_zugaenge=neue_zugaenge)


def _geuebte_codes_und_themen():
    """Leistungsziele (direkt + über Lernziele) und Themen, zu denen es aktive Übungsaufgaben gibt."""
    codes, themen = set(), set()
    for a in Aufgabe.query.filter(Aufgabe.aktiv.is_(True), Aufgabe.verwendung != "pruefung"):
        codes |= {l.code for l in a.leistungsziele} | {l.code for lz in a.lernziele for l in lz.leistungsziele}
        themen |= {t.name for t in a.themen}
    return codes, themen


@bp.route("/klassen/<int:klasse_id>/kompetenzen")
@lp_required
def klasse_kompetenzen(klasse_id):
    k = db.get_or_404(Klasse, klasse_id)
    pruefe_klasse(k)
    ansicht = "themen" if request.args.get("ansicht") == "themen" else "bivo"
    stand = kompetenzstand([u.id for u in k.lernende])
    codes, themen = _geuebte_codes_und_themen()
    for s in stand.values():  # bewertete Ziele immer zeigen, auch wenn ihre Aufgaben inzwischen inaktiv sind
        codes |= set(s["ziele"])
        themen |= set(s["themen"])
    bereiche = []
    for b in Bereich.query.order_by(Bereich.code):
        hks = [(hk, [l for l in hk.leistungsziele if l.code in codes]) for hk in b.handlungskompetenzen]
        hks = [(hk, lz) for hk, lz in hks if lz]
        if hks:
            bereiche.append((b, hks))
    return render_template("lp/kompetenzmatrix.html", klasse=k, stand=stand, bereiche=bereiche, ansicht=ansicht,
                           themen=sorted(themen, key=str.lower))


@bp.route("/lernende/<int:user_id>")
@lp_required
def lernende_profil(user_id):
    u = db.get_or_404(User, user_id)
    pruefe_lernende(u)
    blaetter = u.uebungsblaetter
    # Lernstand: erreichte Punkte pro Thema aus korrigierten Blättern
    stand = {}
    for b in blaetter:
        for ba in b.aufgaben:
            if ba.punkte_erreicht is None:
                continue
            for t in ba.aufgabe.themen or [None]:
                key = t.name if t else "ohne Thema"
                e, m = stand.get(key, (0, 0))
                stand[key] = (e + ba.punkte_erreicht, m + ba.aufgabe.punkte)
    ks = kompetenzstand([u.id])[u.id]
    bivo = []  # [(Bereich, [(Handlungskompetenz, [Leistungsziel])])] – nur bearbeitete Ziele
    for b in Bereich.query.order_by(Bereich.code):
        hks = [(hk, [l for l in hk.leistungsziele if l.code in ks["ziele"]]) for hk in b.handlungskompetenzen]
        hks = [(hk, lz) for hk, lz in hks if lz]
        if hks:
            bivo.append((b, hks))
    return render_template("lp/lernende.html", u=u, blaetter=blaetter, stand=stand, ks=ks, bivo=bivo)


@bp.route("/lernende/<int:user_id>/passwort", methods=["POST"])
@lp_required
def lernende_passwort(user_id):
    u = db.get_or_404(User, user_id)
    pruefe_lernende(u)
    pw = _passwort()
    u.set_passwort(pw)
    u.passwort_aendern = True
    db.session.commit()
    flash(f"Neues Passwort für {u.anzeigename} ({u.benutzername}): {pw}", "ok")
    return redirect(url_for(".lernende_profil", user_id=u.id))


# ---------------------------------------------------------------- Korrektur

@bp.route("/korrektur/<int:blatt_id>")
@lp_required
def korrektur(blatt_id):
    b = db.get_or_404(Uebungsblatt, blatt_id)
    pruefe_lernende(b.lernende)
    def loesung_html(ba):
        from .markup import angehaengte_bilder, markup_html, sichtbare_bilder
        a = ba.aufgabe
        url = lambda bild: url_for(".aufgabenbild", bild_id=bild.id)  # noqa: E731
        return markup_html(rendern(a, ba.seed).loesung, sichtbare_bilder(a, "loesung"), url, angehaengte_bilder(a)[1])

    return render_template("lp/korrektur.html", blatt=b, loesung_html=loesung_html)


@bp.route("/korrektur/<int:blatt_id>", methods=["POST"])
@lp_required
def korrektur_speichern(blatt_id):
    """Erwartet JSON: {aufgaben:[{id,punkte,kommentar}], gesamtkommentar, loesung_freigeben, abschliessen,
    seiten:[{id, annotationen, bild (dataURL PNG oder null)}]}"""
    b = db.get_or_404(Uebungsblatt, blatt_id)
    pruefe_lernende(b.lernende)
    d = request.get_json(force=True)
    ba_map = {ba.id: ba for ba in b.aufgaben}
    for eintrag in d.get("aufgaben", []):
        ba = ba_map.get(int(eintrag["id"]))
        if not ba:
            continue
        p = eintrag.get("punkte")
        if p in ("", None):
            ba.punkte_erreicht = None
        else:
            p = float(str(p).replace(",", "."))
            ba.punkte_erreicht = max(0.0, min(p, ba.aufgabe.punkte))
        ba.kommentar = (eintrag.get("kommentar") or "")[:5000]
        n = str(eintrag.get("niveau") or "")
        ba.niveau = int(n) if n.isdigit() and int(n) in NIVEAUS else None
    b.gesamtkommentar = (d.get("gesamtkommentar") or "")[:10000]
    b.loesung_freigegeben = bool(d.get("loesung_freigeben"))
    seiten_ok = {s.id: s for a in b.abgaben for s in a.seiten}
    for s in d.get("seiten", []):
        seite = seiten_ok.get(int(s["id"]))
        if not seite:
            continue
        seite.annotationen = json.dumps(s.get("annotationen") or [])[:2_000_000]
        bild = s.get("bild")
        if bild and bild.startswith("data:image/"):
            roh = base64.b64decode(bild.split(",", 1)[1])
            im = Image.open(io.BytesIO(roh)).convert("RGB")
            if seite.bild_korrigiert is None:
                seite.bild_korrigiert = storage.relativ("abgaben", str(b.id), f"korr_{seite.id}.jpg")
            im.save(storage.pfad(seite.bild_korrigiert), "JPEG", quality=85)
        elif not s.get("annotationen"):
            seite.bild_korrigiert = None
    if d.get("abschliessen"):
        for ba in b.aufgaben:
            if ba.niveau is None:
                ba.niveau = niveau_aus_punkten(ba.punkte_erreicht, ba.aufgabe.punkte)
        b.status = "korrigiert"
        b.korrigiert_am = now()
    db.session.commit()
    if b.status == "korrigiert":
        pfade = [storage.absolut(s.bild_korrigiert or s.bild) for s in (b.letzte_abgabe.seiten if b.letzte_abgabe else [])]
        storage.speichere_bytes(blatt_pdf_rel(b, "rueckmeldung"), pdfgen.rueckmeldung_pdf(b, pfade))
    return jsonify(ok=True, status=b.status, punkte=b.erreichte_punkte)


@bp.route("/korrektur/<int:blatt_id>/wieder-oeffnen", methods=["POST"])
@lp_required
def korrektur_oeffnen(blatt_id):
    b = db.get_or_404(Uebungsblatt, blatt_id)
    pruefe_lernende(b.lernende)
    b.status = "eingereicht" if b.abgaben else "offen"
    db.session.commit()
    return redirect(url_for(".korrektur", blatt_id=b.id))


# ---------------------------------------------------------------- Aufgabenverwaltung

@bp.route("/aufgaben")
@lp_required
def aufgaben():
    q = Aufgabe.query
    thema = request.args.get("thema", type=int)
    suche = request.args.get("q", "").strip()
    verw = request.args.get("verwendung", "")
    inaktiv = request.args.get("inaktiv") == "1"
    if thema:
        q = q.filter(Aufgabe.themen.any(Thema.id == thema))
    if suche:
        q = q.filter(Aufgabe.titel.ilike(f"%{suche}%") | Aufgabe.text.ilike(f"%{suche}%"))
    if verw:
        q = q.filter(Aufgabe.verwendung == verw)
    if not inaktiv:
        q = q.filter(Aufgabe.aktiv.is_(True))
    return render_template("lp/aufgaben.html", aufgaben=q.order_by(Aufgabe.id.desc()).all(),
                           themen=Thema.query.order_by(Thema.name).all())


def _formular_kontext(aufgabe):
    from .ki import ki_aktiv
    vorauswahl = {"lernziele": [int(x) for x in request.args.getlist("lernziel") if x.isdigit()],
                  "themen": [int(x) for x in request.args.getlist("thema") if x.isdigit()]}
    if vorauswahl["lernziele"] and not vorauswahl["themen"]:
        vorauswahl["themen"] = sorted({lz.thema_id for lz in Lernziel.query.filter(Lernziel.id.in_(vorauswahl["lernziele"]))})
    from .theorie import vorgeschlagene_kapitel
    lz_ids = [lz.id for lz in aufgabe.lernziele] if aufgabe else vorauswahl["lernziele"]
    return dict(aufgabe=aufgabe, themen=Thema.query.order_by(Thema.name).all(),
                bereiche=Bereich.query.order_by(Bereich.code).all(), vorauswahl=vorauswahl, ki_aktiv=ki_aktiv(),
                theorie=TheorieDokument.query.order_by(TheorieDokument.titel).all(),
                kapitel_vorschlaege=vorgeschlagene_kapitel(lz_ids))


@bp.route("/aufgaben/neu", methods=["GET", "POST"])
@bp.route("/aufgaben/<int:aufgabe_id>", methods=["GET", "POST"])
@lp_required
def aufgabe_bearbeiten(aufgabe_id=None):
    a = db.get_or_404(Aufgabe, aufgabe_id) if aufgabe_id else None
    if request.method == "POST":
        f = request.form
        if not f.get("titel", "").strip() or not f.get("text", "").strip():
            flash("Titel und Aufgabentext sind Pflicht.", "fehler")
            return render_template("lp/aufgabe_form.html", **_formular_kontext(a))
        a = a or Aufgabe()
        a.titel = f["titel"].strip()[:200]
        a.text = f["text"]
        a.loesung = f.get("loesung", "")
        a.punkte = float(f.get("punkte", "2").replace(",", ".") or 2)
        a.k_stufe = int(f["k_stufe"]) if f.get("k_stufe", "").isdigit() else None
        a.schwierigkeit = int(f.get("schwierigkeit", 2) or 2)
        a.antwortformat = f.get("antwortformat") if f.get("antwortformat") in ANTWORTFORMATE else "linien"
        a.antwortraum_cm = float(f.get("antwortraum_cm", "5").replace(",", ".") or 0)
        a.verwendung = f.get("verwendung") if f.get("verwendung") in VERWENDUNGEN else "beide"
        a.aktiv = f.get("aktiv") == "1"
        a.typ = f.get("typ") if f.get("typ") in TYPEN else "frei"
        try:
            daten = json.loads(f.get("daten") or "{}")
        except ValueError:
            daten = {}
        a.daten = json.dumps(daten if isinstance(daten, dict) and a.typ != "frei" else {}, ensure_ascii=False)
        a.themen = Thema.query.filter(Thema.id.in_([int(x) for x in f.getlist("thema")])).all()
        neues_thema = f.get("neues_thema", "").strip()
        if neues_thema:
            t = Thema.query.filter_by(name=neues_thema).first() or Thema(name=neues_thema)
            a.themen.append(t)
        a.lernziele = Lernziel.query.filter(Lernziel.id.in_([int(x) for x in f.getlist("lernziel")])).all()
        codes = set(f.getlist("bivo"))
        for lz in a.lernziele:  # Lernziele bringen ihre BiVo-Leistungsziele automatisch mit
            codes |= {l.code for l in lz.leistungsziele}
        a.leistungsziele = Leistungsziel.query.filter(Leistungsziel.code.in_(codes)).all()
        a.kapitel = TheorieKapitel.query.filter(
            TheorieKapitel.id.in_([int(x) for x in f.getlist("kapitel") if x.isdigit()])).all()
        vorlage = db.session.get(Aufgabe, f.get("bilder_von", type=int) or 0) if not a.id else None
        if vorlage:  # Variante als neue Aufgabe: Grafiken der Ausgangsaufgabe übernehmen
            a.bilder = [AufgabeBild(nr=b.nr, datei=b.datei, groesse=b.groesse, nur_loesung=b.nur_loesung,
                                    beschriftung=b.beschriftung) for b in vorlage.bilder]
        _bilder_speichern(a, f, request.files.getlist("bilder_neu"))
        db.session.add(a)
        db.session.commit()
        flash("Aufgabe gespeichert.", "ok")
        for w in bild_warnungen(a) + pruefen(a):
            flash(w, "info")
        if f.get("weiter") == "vorschau":
            return redirect(url_for(".aufgabe_bearbeiten", aufgabe_id=a.id, vorschau=1))
        return redirect(url_for(".aufgaben"))
    return render_template("lp/aufgabe_form.html", **_formular_kontext(a))


def _bilder_speichern(a, f, neue_dateien, bild_klasse=AufgabeBild, ordner="aufgabenbilder"):
    """Bestehende Bilder aktualisieren/löschen, neue Bilder anhängen (Nummern bleiben stabil).

    Für Aufgaben (AufgabeBild) und Theoriekapitel (KapitelBild – ohne «nur in der Lösung»)."""
    mit_loesung = bild_klasse is AufgabeBild
    naechste = max([b.nr for b in a.bilder] + [0]) + 1  # vor dem Löschen: vorhergesagte Nummern im Editor bleiben gültig
    for b in list(a.bilder):
        if f.get(f"bild_{b.id}_loeschen") == "1":
            a.bilder.remove(b)
            continue
        g = f.get(f"bild_{b.id}_groesse")
        b.groesse = g if g in BILDGROESSEN else b.groesse
        if mit_loesung:
            b.nur_loesung = f.get(f"bild_{b.id}_loesung") == "1"
        b.beschriftung = f.get(f"bild_{b.id}_text", "").strip()[:300]
    groesse = f.get("neu_groesse") if f.get("neu_groesse") in BILDGROESSEN else "voll"
    for datei in neue_dateien:
        if not datei or not datei.filename:
            continue
        try:
            im = storage.upload_zu_seitenbildern(datei)[0]
        except ValueError as e:
            flash(str(e), "fehler")
            continue
        extra = {"nur_loesung": f.get("neu_loesung") == "1"} if mit_loesung else {}
        a.bilder.append(bild_klasse(nr=naechste, datei=storage.speichere_bild(im, ordner), groesse=groesse, **extra))
        naechste += 1


@bp.route("/aufgaben/vorschau", methods=["POST"])
@lp_required
def aufgabe_live_vorschau():
    """Live-Vorschau im Editor: rendert Aufgabentext und Lösung als HTML (wie im PDF, ohne Seitenlayout)."""
    from .markup import markup_html
    d = request.get_json(force=True)
    a = db.session.get(Aufgabe, int(d.get("aufgabe_id") or 0)) if d.get("aufgabe_id") else None
    bilder = {b.nr: b for b in a.bilder} if a else {}
    url = lambda b: url_for(".aufgabenbild", bild_id=b.id)  # noqa: E731
    sichtbar = {nr: b for nr, b in bilder.items() if not b.nur_loesung}
    entwurf = SimpleNamespace(typ=d.get("typ") if d.get("typ") in TYPEN else "frei", daten=d.get("daten") or {},
                              text=d.get("text", ""), loesung=d.get("loesung", ""))
    g = rendern(entwurf, int(d.get("seed") or 1))
    hinweis = "; ".join(g.fehler)
    if entwurf.typ == "rechnung" and g.werte and not g.fehler:
        hoch = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
        lesbar = lambda v: re.sub(r"\^\{(-?\d+)\}", lambda m: m[1].translate(hoch), zahl(v, 4))  # noqa: E731
        hinweis = "Beispielwerte: " + ", ".join(f"{k} = {lesbar(v)}" for k, v in g.werte.items())
    return jsonify(aufgabe=str(markup_html(g.text, sichtbar, url)), loesung=str(markup_html(g.loesung, bilder, url)),
                   hinweis=hinweis, fehler=bool(g.fehler))


@bp.route("/aufgabenbild/<int:bild_id>")
@lp_required
def aufgabenbild(bild_id):
    """Grafiken nur für Lehrpersonen (Lernende sehen sie ausschliesslich in ihren PDFs)."""
    b = db.get_or_404(AufgabeBild, bild_id)
    return send_file(storage.absolut(b.datei))


@bp.route("/aufgaben/<int:aufgabe_id>/vorschau.pdf")
@lp_required
def aufgabe_vorschau(aufgabe_id):
    a = db.get_or_404(Aufgabe, aufgabe_id)
    return send_file(io.BytesIO(pdfgen.aufgabe_vorschau_pdf(a, bild_pfad)), mimetype="application/pdf",
                     download_name=f"Aufgabe_{a.id}.pdf")


@bp.route("/aufgaben/<int:aufgabe_id>/duplizieren", methods=["POST"])
@lp_required
def aufgabe_duplizieren(aufgabe_id):
    a = db.get_or_404(Aufgabe, aufgabe_id)
    kopie = Aufgabe(**{k: getattr(a, k) for k in ("text", "loesung", "punkte", "k_stufe", "schwierigkeit",
                                                  "antwortformat", "antwortraum_cm", "verwendung", "typ", "daten")})
    kopie.bilder = [AufgabeBild(nr=b.nr, datei=b.datei, groesse=b.groesse, nur_loesung=b.nur_loesung,
                                beschriftung=b.beschriftung) for b in a.bilder]
    kopie.titel = (a.titel + " (Kopie)")[:200]
    kopie.themen, kopie.lernziele, kopie.leistungsziele = list(a.themen), list(a.lernziele), list(a.leistungsziele)
    kopie.kapitel = list(a.kapitel)
    db.session.add(kopie)
    db.session.commit()
    flash("Kopie erstellt – jetzt anpassen (z. B. andere Zahlenwerte).", "ok")
    return redirect(url_for(".aufgabe_bearbeiten", aufgabe_id=kopie.id))


@bp.route("/aufgaben/export.json")
@lp_required
def aufgaben_export():
    daten = [a.to_dict() for a in Aufgabe.query.order_by(Aufgabe.id)]
    return send_file(io.BytesIO(json.dumps(daten, ensure_ascii=False, indent=2).encode()),
                     mimetype="application/json", as_attachment=True, download_name="aufgaben.json")


@bp.route("/aufgaben/import", methods=["POST"])
@lp_required
def aufgaben_import():
    f = request.files.get("datei")
    try:
        daten = json.load(f)
        n = importers.import_aufgaben(daten)
        flash(f"{n} Aufgaben importiert.", "ok")
    except Exception as e:  # noqa: BLE001 – Rückmeldung an die Lehrperson
        db.session.rollback()
        flash(f"Import fehlgeschlagen: {e}", "fehler")
    return redirect(url_for(".aufgaben"))


# ---------------------------------------------------------------- Lernziele & Kompetenzen

@bp.route("/lernziele")
@lp_required
def lernziele():
    themen = Thema.query.order_by(Thema.name).all()
    zaehler = Counter()
    for a in Aufgabe.query.filter_by(aktiv=True):
        for lz in a.lernziele:
            zaehler[(lz.id, "u" if a.verwendung != "pruefung" else "p")] += 1
            if a.verwendung == "beide":
                zaehler[(lz.id, "p")] += 1
    from .ki import ki_aktiv
    return render_template("lp/lernziele.html", themen=themen, zaehler=zaehler, ki_aktiv=ki_aktiv())


@bp.route("/lernziele/import", methods=["GET", "POST"])
@lp_required
def lernziele_import():
    vorschau = None
    if request.method == "POST":
        thema = request.form.get("thema", "").strip()
        text = request.form.get("text", "")
        datei = request.files.get("datei")
        if datei and datei.filename:
            text = importers.pdf_zu_text(datei.read())
        eintraege = importers.parse_lernziele(text)
        if not thema:
            flash("Bitte einen Themennamen angeben.", "fehler")
        elif not eintraege:
            flash("Keine Lernziele erkannt. Format: '1. Ich kann … (a.1.1, K2)'.", "fehler")
        elif request.form.get("bestaetigt") == "1":
            t, neu, akt, fehlend, abgelehnt = importers.import_lernziele(thema, eintraege,
                                                                          request.form.get("ersetzen") == "1")
            flash(f"{t.name}: {neu} neue, {akt} aktualisierte Lernziele.", "ok")
            if abgelehnt:
                flash(f"{len(abgelehnt)} Einträge ohne gültigen BiVo-Code nicht importiert: "
                      + ", ".join(f"{e['bereich']}{e['nummer']}" for e in abgelehnt), "fehler")
            if fehlend:
                flash("Unbekannte BiVo-Codes (nicht verknüpft): " + ", ".join(fehlend), "info")
            return redirect(url_for(".lernziele"))
        else:
            vorschau = eintraege
        bekannte = {l.code for l in Leistungsziel.query} if vorschau else set()
        return render_template("lp/lernziele_import.html", vorschau=vorschau, thema=thema, text=text, bekannte=bekannte)
    return render_template("lp/lernziele_import.html", vorschau=None, thema="", text="", bekannte=set())


@bp.route("/lernziele/neu", methods=["GET", "POST"])
@bp.route("/lernziele/<int:lz_id>", methods=["GET", "POST"])
@lp_required
def lernziel_bearbeiten(lz_id=None):
    """Einzelnes Lernziel anlegen, bearbeiten oder löschen – mit mindestens einem BiVo-Kompetenzziel."""
    from .lernziele import kompetenzziele_setzen, lernziel_loeschen, naechste_nummer
    lz = db.get_or_404(Lernziel, lz_id) if lz_id else None
    themen = Thema.query.order_by(Thema.name).all()
    bereiche = Bereich.query.order_by(Bereich.code).all()

    def formular(werte):
        return render_template("lp/lernziel_form.html", lz=lz, w=werte, themen=themen, bereiche=bereiche)

    if request.method == "GET":
        if lz:
            w = dict(thema=lz.thema_id, bereich=lz.bereich, nummer=lz.nummer, text=lz.text, k_stufe=lz.k_stufe,
                     bivo=[l.code for l in lz.leistungsziele])
        else:
            w = dict(thema=request.args.get("thema", type=int), bereich="", nummer="", text="", k_stufe=None, bivo=[])
        return formular(w)

    f = request.form
    if lz and f.get("loeschen") == "1":
        verwendet = lernziel_loeschen(lz)
        if verwendet:
            flash("Lernziel wird noch verwendet von: " + ", ".join(a.titel for a in verwendet), "fehler")
            return redirect(url_for(".lernziel_bearbeiten", lz_id=lz.id))
        db.session.commit()
        flash("Lernziel gelöscht.", "ok")
        return redirect(url_for(".lernziele"))

    w = dict(thema=f.get("thema", type=int), bereich=f.get("bereich", "").strip().lower(),
             nummer=f.get("nummer", "").strip(), text=f.get("text", "").strip(),
             k_stufe=f.get("k_stufe", type=int), bivo=f.getlist("bivo"))
    bekannt = {l.code for l in Leistungsziel.query.filter(Leistungsziel.code.in_(w["bivo"]))}
    gueltig = [c for c in dict.fromkeys(w["bivo"]) if c in bekannt]  # Reihenfolge der Auswahl bleibt erhalten
    thema = db.session.get(Thema, w["thema"] or 0)
    fehler = None
    if not thema:
        fehler = "Bitte ein Thema wählen."
    elif not w["text"]:
        fehler = "Bitte den Text des Lernziels angeben."
    elif not gueltig:
        fehler = "Bitte mindestens ein BiVo-Kompetenzziel wählen."
    elif w["k_stufe"] is not None and not 1 <= w["k_stufe"] <= 6:
        fehler = "K-Stufe muss zwischen 1 und 6 liegen."
    else:
        w["bereich"] = w["bereich"][:4] or gueltig[0].split(".")[0]
        if not w["nummer"]:
            w["nummer"] = naechste_nummer(thema.id, w["bereich"])
        elif not re.fullmatch(r"[0-9]{1,5}", w["nummer"]) or int(w["nummer"]) < 1:
            fehler = "Die Nummer muss eine positive ganze Zahl sein (höchstens 99999)."
    if not fehler:
        w["nummer"] = int(w["nummer"])
        doppelt = Lernziel.query.filter(Lernziel.thema_id == thema.id, Lernziel.bereich == w["bereich"],
                                        Lernziel.nummer == w["nummer"], Lernziel.id != (lz.id if lz else -1)).first()
        if doppelt:
            fehler = f"Lernziel {thema.name} {doppelt.kuerzel} existiert bereits."
    if fehler:
        flash(fehler, "fehler")
        return formular(w)

    if not lz:
        lz = Lernziel()
        db.session.add(lz)
    lz.thema, lz.bereich, lz.nummer, lz.text, lz.k_stufe = thema, w["bereich"], w["nummer"], w["text"], w["k_stufe"]
    db.session.flush()
    n = kompetenzziele_setzen(lz, gueltig)
    db.session.commit()
    flash(f"Lernziel {lz.label} gespeichert." + (f" {n} Aufgabe{'' if n == 1 else 'n'} angepasst." if n else ""), "ok")
    return redirect(url_for(".lernziele"))


@bp.route("/themen/<int:thema_id>", methods=["POST"])
@lp_required
def thema_bearbeiten(thema_id):
    t = db.get_or_404(Thema, thema_id)
    if request.form.get("loeschen") == "1":
        from .lernziele import verknuepfungen_loesen
        lz_ids = [lz.id for lz in t.lernziele]
        if Aufgabe.query.filter(Aufgabe.themen.any(Thema.id == t.id)).count():
            flash("Thema wird noch von Aufgaben verwendet.", "fehler")
        elif lz_ids and Aufgabe.query.filter(Aufgabe.lernziele.any(Lernziel.id.in_(lz_ids))).count():
            flash("Lernziele dieses Themas werden noch von Aufgaben verwendet.", "fehler")
        else:
            for lz in t.lernziele:
                verknuepfungen_loesen(lz)
            db.session.delete(t)
            db.session.commit()
            flash("Thema gelöscht.", "ok")
    else:
        t.name = request.form.get("name", t.name).strip() or t.name
        t.beschreibung = request.form.get("beschreibung", "")
        db.session.commit()
    return redirect(url_for(".lernziele"))


@bp.route("/kompetenzen", methods=["GET", "POST"])
@lp_required
def kompetenzen():
    if request.method == "POST":
        if not current_user.ist_admin:  # Die BiVo-Liste ändert sich nicht – Neueinlesen nur für Admins
            abort(403)
        f = request.files.get("datei")
        try:
            nb, nh, nl = importers.import_kompetenzen(f)
            flash(f"Importiert: {nb} Bereiche, {nh} Handlungskompetenzen, {nl} Leistungsziele.", "ok")
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            flash(f"Import fehlgeschlagen: {e}", "fehler")
        return redirect(url_for(".kompetenzen"))
    zaehler = Counter(l.code for a in Aufgabe.query.filter_by(aktiv=True) for l in a.leistungsziele)
    return render_template("lp/kompetenzen.html", bereiche=Bereich.query.order_by(Bereich.code).all(), zaehler=zaehler)


# ---------------------------------------------------------------- Prüfungen

@bp.route("/pruefungen")
@lp_required
def pruefungen():
    liste = Pruefung.query.filter_by(lp_id=current_user.id).order_by(Pruefung.erstellt_am.desc()).all()
    return render_template("lp/pruefungen.html", pruefungen=liste)


@bp.route("/pruefungen/neu", methods=["GET", "POST"])
@lp_required
def pruefung_neu():
    if request.method == "POST":
        f = request.form
        themen, codes, lernziele, k = auswahl_aus_request(f)
        klasse = db.session.get(Klasse, f.get("klasse_id", type=int) or 0)
        if klasse:
            pruefe_klasse(klasse)
        ausschliessen = geuebte_aufgaben_der_klasse(klasse) if (klasse and f.get("ohne_geuebte") == "1") else set()
        param = dict(themen_ids=themen, lernziel_ids=lernziele, leistungsziel_codes=codes,
                     ziel_punkte=float(f.get("ziel_punkte", 30) or 30),
                     max_aufgaben=f.get("max_aufgaben", type=int) or None, k_stufen=k,
                     nur_pruefungsaufgaben=f.get("nur_pruefung") == "1")
        res = stelle_pruefung_zusammen(**param, ausschliessen_ids=ausschliessen)
        if not res["aufgaben"]:
            flash("Mit diesen Parametern wurden keine Aufgaben gefunden.", "fehler")
            return redirect(url_for(".pruefung_neu"))
        p = Pruefung(titel=f.get("titel", "").strip() or "Prüfung", lp=current_user, klasse=klasse,
                     datum=f.get("datum", ""), dauer_min=f.get("dauer_min", type=int),
                     hinweise=f.get("hinweise", ""), parameter=json.dumps(param))
        for i, a in enumerate(res["aufgaben"], 1):
            p.aufgaben.append(PruefungAufgabe(aufgabe=a, position=i, seed=neuer_seed()))
        db.session.add(p)
        db.session.commit()
        if res["nicht_abgedeckt"]:
            flash(f"{len(res['nicht_abgedeckt'])} Ziel(e) konnten nicht abgedeckt werden – siehe Übersicht.", "info")
        return redirect(url_for(".pruefung", pruefung_id=p.id))
    return render_template("lp/pruefung_neu.html", themen=Thema.query.order_by(Thema.name).all(),
                           bereiche=Bereich.query.order_by(Bereich.code).all(), klassen=current_user.eigene_klassen)


def _abdeckung(p):
    param = json.loads(p.parameter or "{}")
    lz_ids, codes = set(param.get("lernziel_ids", [])), set(param.get("leistungsziel_codes", []))
    ziele = {("lz", i) for i in lz_ids} | {("bivo", c) for c in codes}
    abgedeckt = set()
    for pa in p.aufgaben:
        abgedeckt |= {("lz", l.id) for l in pa.aufgabe.lernziele if l.id in lz_ids}
        abgedeckt |= {("bivo", l.code) for l in pa.aufgabe.leistungsziele if l.code in codes}
    return ziele_beschreiben(abgedeckt), ziele_beschreiben(ziele - abgedeckt), param


@bp.route("/pruefungen/<int:pruefung_id>", methods=["GET", "POST"])
@lp_required
def pruefung(pruefung_id):
    p = db.get_or_404(Pruefung, pruefung_id)
    if p.lp_id != current_user.id:
        abort(403)
    if request.method == "POST":
        aktion = request.form.get("aktion")
        if aktion == "meta":
            p.titel = request.form.get("titel", p.titel).strip() or p.titel
            p.datum = request.form.get("datum", "")
            p.dauer_min = request.form.get("dauer_min", type=int)
            p.hinweise = request.form.get("hinweise", "")
        elif aktion == "entfernen":
            pa = db.get_or_404(PruefungAufgabe, request.form.get("pa_id", type=int))
            p.aufgaben.remove(pa)
        elif aktion in ("hoch", "runter"):
            pa = db.get_or_404(PruefungAufgabe, request.form.get("pa_id", type=int))
            i = p.aufgaben.index(pa)
            j = i - 1 if aktion == "hoch" else i + 1
            if 0 <= j < len(p.aufgaben):
                p.aufgaben[i].position, p.aufgaben[j].position = p.aufgaben[j].position, p.aufgaben[i].position
        elif aktion == "hinzufuegen":
            a = db.session.get(Aufgabe, request.form.get("aufgabe_id", type=int) or 0)
            if a and a.id not in {x.aufgabe_id for x in p.aufgaben}:
                p.aufgaben.append(PruefungAufgabe(aufgabe=a, position=len(p.aufgaben) + 1, seed=neuer_seed()))
        elif aktion == "loeschen":
            db.session.delete(p)
            db.session.commit()
            flash("Prüfung gelöscht.", "ok")
            return redirect(url_for(".pruefungen"))
        db.session.commit()
        for i, pa in enumerate(sorted(p.aufgaben, key=lambda x: x.position), 1):
            pa.position = i
        db.session.commit()
        return redirect(url_for(".pruefung", pruefung_id=p.id))
    abgedeckt, offen, param = _abdeckung(p)
    vorhandene = {pa.aufgabe_id for pa in p.aufgaben}
    themen_ids = param.get("themen_ids") or []
    q = Aufgabe.query.filter(Aufgabe.aktiv.is_(True), Aufgabe.verwendung != "uebung")
    if themen_ids:
        q = q.filter(Aufgabe.themen.any(Thema.id.in_(themen_ids)))
    weitere = [a for a in q.order_by(Aufgabe.titel) if a.id not in vorhandene]
    k_vert = Counter(pa.aufgabe.k_stufe for pa in p.aufgaben)
    return render_template("lp/pruefung.html", p=p, abgedeckt=abgedeckt, offen=offen, weitere=weitere, k_vert=k_vert)


@bp.route("/pruefungen/<int:pruefung_id>/<art>.pdf")
@lp_required
def pruefung_pdf(pruefung_id, art):
    p = db.get_or_404(Pruefung, pruefung_id)
    if p.lp_id != current_user.id or art not in ("pruefung", "loesung"):
        abort(404)
    daten = pdfgen.pruefung_pdf(p, bild_pfad, loesung=(art == "loesung"))
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", p.titel)[:60]
    return send_file(io.BytesIO(daten), mimetype="application/pdf",
                     download_name=f"{name}{'_Loesung' if art == 'loesung' else ''}.pdf")


# ---------------------------------------------------------------- KI-Assistent

@bp.route("/ki")
@lp_required
def ki_status():
    from datetime import datetime, timedelta
    from .ki import kosten_usd, ki_aktiv, modell
    from .models import KiProtokoll
    monatsbeginn = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def zusammenfassen(eintraege):
        zs = {"anzahl": 0, "input": 0, "output": 0, "usd": 0.0, "aktionen": Counter()}
        for p in eintraege:
            zs["anzahl"] += 1
            zs["input"] += p.input_tokens + p.cache_lesen + p.cache_schreiben
            zs["output"] += p.output_tokens
            zs["usd"] += kosten_usd(p)
            zs["aktionen"][p.aktion] += 1
        return zs
    monat = zusammenfassen(KiProtokoll.query.filter(KiProtokoll.zeit >= monatsbeginn))
    vormonat = zusammenfassen(KiProtokoll.query.filter(KiProtokoll.zeit < monatsbeginn,
                                                        KiProtokoll.zeit >= (monatsbeginn - timedelta(days=1)).replace(day=1)))
    gesamt = zusammenfassen(KiProtokoll.query)
    letzte = KiProtokoll.query.order_by(KiProtokoll.zeit.desc()).limit(15).all()
    return render_template("lp/ki.html", aktiv=ki_aktiv(), modell=modell(), monat=monat, vormonat=vormonat,
                           gesamt=gesamt, letzte=letzte, kosten_usd=kosten_usd)


def _formulardaten(d):
    return {"titel": d.get("titel", ""), "text": d.get("text", ""), "loesung": d.get("loesung", ""),
            "typ": d.get("typ") if d.get("typ") in TYPEN else "frei", "daten": d.get("daten") or {},
            "punkte": d.get("punkte", ""), "k_stufe": d.get("k_stufe", "")}


@bp.route("/ki/<aktion>", methods=["POST"])
@lp_required
def ki_aktion(aktion):
    from . import ki
    if not ki.ki_aktiv():
        return jsonify(fehler="Der KI-Assistent ist nicht aktiviert (ANTHROPIC_API_KEY fehlt)."), 503
    d = request.get_json(force=True) or {}
    try:
        if aktion == "entwurf":
            lz_ids = [int(x) for x in d.get("lernziele", []) if str(x).isdigit()]
            lernziele = Lernziel.query.filter(Lernziel.id.in_(lz_ids)).all() if lz_ids else []
            codes = [c for c in d.get("bivo", []) if isinstance(c, str)]
            leistungsziele = Leistungsziel.query.filter(Leistungsziel.code.in_(codes)).all() if codes else []
            th_ids = [int(x) for x in d.get("themen", []) if str(x).isdigit()]
            themen = Thema.query.filter(Thema.id.in_(th_ids)).all() if th_ids else []
            if not (lernziele or leistungsziele or themen or (d.get("wunsch") or "").strip()):
                return jsonify(fehler="Bitte zuerst Lernziele, Kompetenzziele oder ein Thema wählen "
                                      "(rechts unter «Zuordnung») oder einen Wunsch eingeben."), 400
            q = Aufgabe.query.filter(Aufgabe.aktiv.is_(True))
            if lz_ids:
                q = q.filter(Aufgabe.lernziele.any(Lernziel.id.in_(lz_ids)))
            elif th_ids:
                q = q.filter(Aufgabe.themen.any(Thema.id.in_(th_ids)))
            beispiele = q.order_by(db.func.random()).limit(2).all() if (lz_ids or th_ids) else []
            k = d.get("k_stufe")
            aufgabe, hinweise = ki.entwurf(lernziele, leistungsziele, themen, d.get("typ"),
                                           int(k) if str(k).isdigit() else None, d.get("punkte"),
                                           (d.get("wunsch") or "")[:2000], beispiele)
            return jsonify(aufgabe=aufgabe, hinweise=hinweise)
        if aktion == "pruefen":
            return jsonify(ki.loesung_pruefen(_formulardaten(d)))
        if aktion == "tags":
            return jsonify(ki.tags_vorschlagen(
                _formulardaten(d), Thema.query.order_by(Thema.name).all(),
                Lernziel.query.join(Thema).order_by(Thema.name, Lernziel.bereich, Lernziel.nummer).all(),
                Leistungsziel.query.order_by(Leistungsziel.sort).all()))
        if aktion == "variante":
            aufgabe, hinweise = ki.variante(_formulardaten(d), d.get("art", "zahlen"))
            return jsonify(aufgabe=aufgabe, hinweise=hinweise)
    except ki.KiFehler as e:
        return jsonify(fehler=str(e)), 502
    abort(404)
