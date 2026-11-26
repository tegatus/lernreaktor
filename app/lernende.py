import os

from flask import (Blueprint, abort, current_app, flash, has_request_context, jsonify, redirect, render_template,
                   request, send_file, url_for)
from flask_login import current_user, login_required

from . import pdfgen, storage
from .aufgabentypen import neuer_seed
from .auth import lernende_required
from .einstellungen import einstellung
from .models import (Abgabe, AbgabeSeite, BlattAufgabe, Bereich, Thema, Uebungsblatt, db)
from .selection import auswahl_beschreiben, filter_aufgaben, waehle_uebungsaufgaben

bp = Blueprint("lernende", __name__)


def bild_pfad(bild):
    """AufgabeBild -> absoluter Dateipfad (für die PDF-Erzeugung)."""
    return storage.absolut(bild.datei) if bild and bild.datei else None


def blatt_pdf_rel(blatt, art):
    return storage.relativ("blaetter", str(blatt.id), f"{art}.pdf")


def upload_url(blatt):
    """Absolute Adresse der Blatt-Seite für den QR-Code (BASIS_URL, sonst die Adresse der aktuellen Anfrage)."""
    basis = current_app.config.get("BASIS_URL") or (request.url_root if has_request_context() else "")
    return basis.rstrip("/") + url_for("lernende.blatt", blatt_id=blatt.id) if basis else None


def erzeuge_blatt_pdfs(blatt):
    """Schnappschuss von Aufgaben- und Lösungsblatt (spätere Änderungen an Aufgaben verändern sie nicht)."""
    storage.speichere_bytes(blatt_pdf_rel(blatt, "aufgaben"),
                            pdfgen.uebungsblatt_pdf(blatt, bild_pfad, upload_url=upload_url(blatt)))
    storage.speichere_bytes(blatt_pdf_rel(blatt, "loesung"), pdfgen.uebungsblatt_pdf(blatt, bild_pfad, loesung=True))


def darf_blatt_sehen(blatt):
    return blatt.lernende_id == current_user.id or current_user.betreut(blatt.lernende)


def auswahl_aus_request(src):
    themen = [int(x) for x in src.getlist("thema") if x.isdigit()]
    lernziele = [int(x) for x in src.getlist("lernziel") if x.isdigit()]
    codes = [x for x in src.getlist("bivo") if x]
    k = [int(x) for x in src.getlist("k") if x.isdigit()] if einstellung("k_stufen_filter") else []
    return themen, codes, lernziele, k


@bp.route("/lernende")
@lernende_required
def dashboard():
    return render_template("lernende/dashboard.html", blaetter=current_user.uebungsblaetter)


@bp.route("/lernende/neu", methods=["GET", "POST"])
@lernende_required
def neu():
    if request.method == "POST":
        themen, codes, lernziele, k = auswahl_aus_request(request.form)
        if not (themen or codes or lernziele):
            flash("Bitte wähle mindestens ein Thema, Lernziel oder Kompetenzziel.", "fehler")
            return redirect(url_for(".neu"))
        anzahl = max(1, min(int(request.form.get("anzahl", 5) or 5), 25))
        kandidaten = filter_aufgaben(themen, codes, lernziele, k)
        if not kandidaten:
            flash("Für diese Auswahl gibt es noch keine Übungsaufgaben.", "fehler")
            return redirect(url_for(".neu"))
        aufgaben = waehle_uebungsaufgaben(current_user, kandidaten, anzahl, lernziele, codes)
        beschreibung = auswahl_beschreiben(themen, codes, lernziele, k)
        titel = request.form.get("titel", "").strip() or "Übungsblatt " + (
            ", ".join(t.name for t in Thema.query.filter(Thema.id.in_(themen))) if themen else "Kompetenzen")
        blatt = Uebungsblatt(lernende=current_user, titel=titel[:200], auswahl=beschreibung)
        for i, a in enumerate(aufgaben, 1):
            blatt.aufgaben.append(BlattAufgabe(aufgabe=a, position=i, seed=neuer_seed()))
        db.session.add(blatt)
        db.session.commit()
        erzeuge_blatt_pdfs(blatt)
        if len(aufgaben) < anzahl:
            flash(f"Es gab nur {len(aufgaben)} passende Aufgaben.", "info")
        flash("Dein Übungsblatt ist bereit. Drucke es aus und löse die Aufgaben.", "ok")
        return redirect(url_for(".blatt", blatt_id=blatt.id))
    themen = Thema.query.order_by(Thema.name).all()
    bereiche = Bereich.query.order_by(Bereich.code).all()
    return render_template("lernende/neu.html", themen=themen, bereiche=bereiche)


@bp.route("/lernende/anzahl")
@login_required
def anzahl():
    themen, codes, lernziele, k = auswahl_aus_request(request.args)
    if not (themen or codes or lernziele):
        return jsonify(anzahl=0)
    verw = ("beide", "uebung", "pruefung") if request.args.get("pruefung") and current_user.ist_lp else ("beide", "uebung")
    return jsonify(anzahl=len(filter_aufgaben(themen, codes, lernziele, k, verw)))


@bp.route("/blatt/<int:blatt_id>")
@login_required
def blatt(blatt_id):
    b = db.get_or_404(Uebungsblatt, blatt_id)
    if not darf_blatt_sehen(b):
        abort(403)
    if current_user.ist_lp:
        return redirect(url_for("lp.korrektur", blatt_id=b.id))
    return render_template("lernende/blatt.html", blatt=b)


@bp.route("/blatt/<int:blatt_id>/hochladen", methods=["POST"])
@lernende_required
def hochladen(blatt_id):
    """Formular-Upload (Dateiauswahl) oder Kamera-Upload per fetch (X-Requested-With: fetch → JSON-Antwort)."""
    b = db.get_or_404(Uebungsblatt, blatt_id)
    if b.lernende_id != current_user.id:
        abort(403)
    per_fetch = request.headers.get("X-Requested-With") == "fetch"

    def antwort(meldung, art, status=200):
        if per_fetch:
            return jsonify(ok=art == "ok", meldung=meldung, ziel=url_for(".blatt", blatt_id=b.id)), status
        flash(meldung, art)
        return redirect(url_for(".blatt", blatt_id=b.id))

    dateien = [f for f in request.files.getlist("dateien") if f and f.filename]
    if not dateien:
        return antwort("Bitte wähle mindestens ein Foto oder PDF aus.", "fehler", 400)
    bilder = []
    try:
        for f in dateien:
            bilder += storage.upload_zu_seitenbildern(f)
    except ValueError as e:
        return antwort(str(e), "fehler", 400)
    abgabe = Abgabe(blatt=b)
    for nr, im in enumerate(bilder, 1):
        rel = storage.speichere_bild(im, "abgaben", str(b.id))
        abgabe.seiten.append(AbgabeSeite(nr=nr, bild=rel))
    db.session.add(abgabe)
    b.status = "eingereicht"
    db.session.commit()
    if per_fetch:
        flash(f"{len(bilder)} Seite(n) hochgeladen. Deine Lehrperson wird die Abgabe korrigieren.", "ok")
    return antwort(f"{len(bilder)} Seite(n) hochgeladen. Deine Lehrperson wird die Abgabe korrigieren.", "ok")


@bp.route("/blatt/<int:blatt_id>/loeschen", methods=["POST"])
@lernende_required
def loeschen(blatt_id):
    b = db.get_or_404(Uebungsblatt, blatt_id)
    if b.lernende_id != current_user.id or b.abgaben:
        abort(403)
    db.session.delete(b)
    db.session.commit()
    flash("Übungsblatt gelöscht.", "ok")
    return redirect(url_for(".dashboard"))


@bp.route("/blatt/<int:blatt_id>/<art>.pdf")
@login_required
def blatt_pdf(blatt_id, art):
    b = db.get_or_404(Uebungsblatt, blatt_id)
    if art not in ("aufgaben", "loesung", "rueckmeldung"):
        abort(404)
    if not darf_blatt_sehen(b):
        abort(403)
    if art == "loesung" and not current_user.ist_lp and not b.loesung_freigegeben:
        abort(403)
    if art == "rueckmeldung" and not current_user.ist_lp and b.status != "korrigiert":
        abort(403)
    pfad = storage.absolut(blatt_pdf_rel(b, art))
    if not os.path.exists(pfad):
        if art == "rueckmeldung":
            abort(404)
        erzeuge_blatt_pdfs(b)
    name = {"aufgaben": "Uebungsblatt", "loesung": "Loesung", "rueckmeldung": "Rueckmeldung"}[art]
    return send_file(pfad, mimetype="application/pdf", download_name=f"{name}_{b.code}.pdf",
                     as_attachment=request.args.get("download") == "1")


@bp.route("/seite/<int:seite_id>.jpg")
@login_required
def seite_bild(seite_id):
    s = db.get_or_404(AbgabeSeite, seite_id)
    b = s.abgabe.blatt
    if not darf_blatt_sehen(b):
        abort(403)
    korrigiert = request.args.get("korrigiert") == "1"
    if korrigiert and not current_user.ist_lp and b.status != "korrigiert":
        abort(403)
    rel = s.bild_korrigiert if korrigiert and s.bild_korrigiert else s.bild
    return send_file(storage.absolut(rel), mimetype="image/png" if rel.endswith(".png") else "image/jpeg",
                     max_age=0)
