"""Theorie: Dokumente mit Kapiteln zum Nachschlagen, verknüpft mit Aufgaben und Lernzielen.

Lesen dürfen alle Angemeldeten (Entwürfe nur Lehrpersonen), bearbeiten nur Lehrpersonen.
"""
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from . import storage
from .auth import lp_required
from .markup import markup_html, referenzierte_bilder
from .models import Bereich, KapitelBild, Lernziel, TheorieDokument, TheorieKapitel, Thema, db

bp = Blueprint("theorie", __name__)


def darf_sehen(kapitel):
    return kapitel.sichtbar or current_user.ist_lp


def kapitel_html(k, text=None):
    bilder = {b.nr: b for b in k.bilder} if k else {}
    frei = [b for b in (k.bilder if k else []) if b.nr not in referenzierte_bilder(text if text is not None else k.text)]
    return markup_html(k.text if text is None else text, bilder, lambda b: url_for("theorie.bild", bild_id=b.id),
                       anhaengen=frei, zwischentitel=True)


# ---------------------------------------------------------------- Lesen

@bp.route("/theorie")
@login_required
def index():
    dokumente = [(d, [k for k in d.kapitel_sortiert if darf_sehen(k)])
                 for d in TheorieDokument.query.order_by(TheorieDokument.titel)]
    return render_template("theorie/index.html", dokumente=dokumente)


@bp.route("/theorie/kapitel/<int:kapitel_id>")
@login_required
def kapitel(kapitel_id):
    k = db.get_or_404(TheorieKapitel, kapitel_id)
    if not darf_sehen(k):
        abort(404)
    geschwister = [x for x in k.dokument.kapitel_sortiert if darf_sehen(x)]
    i = geschwister.index(k)
    return render_template("theorie/kapitel.html", k=k, inhalt=kapitel_html(k),
                           vorher=geschwister[i - 1] if i > 0 else None,
                           nachher=geschwister[i + 1] if i + 1 < len(geschwister) else None)


@bp.route("/theorie/bild/<int:bild_id>")
@login_required
def bild(bild_id):
    b = db.get_or_404(KapitelBild, bild_id)
    if not darf_sehen(b.kapitel):
        abort(404)
    return send_file(storage.absolut(b.datei), max_age=3600)


# ---------------------------------------------------------------- Bearbeiten (Lehrpersonen)

@bp.route("/lp/theorie/dokument", methods=["POST"])
@bp.route("/lp/theorie/dokument/<int:dokument_id>", methods=["POST"])
@lp_required
def dokument_speichern(dokument_id=None):
    d = db.get_or_404(TheorieDokument, dokument_id) if dokument_id else TheorieDokument()
    titel = request.form.get("titel", "").strip()[:200]
    if not titel:
        flash("Bitte einen Titel angeben.", "fehler")
        return redirect(url_for(".index"))
    d.titel = titel
    d.beschreibung = request.form.get("beschreibung", "").strip()
    db.session.add(d)
    db.session.commit()
    flash("Theorieteil gespeichert.", "ok")
    return redirect(url_for(".index") + f"#dok-{d.id}")


@bp.route("/lp/theorie/dokument/<int:dokument_id>/loeschen", methods=["POST"])
@lp_required
def dokument_loeschen(dokument_id):
    d = db.get_or_404(TheorieDokument, dokument_id)
    if d.kapitel:
        flash("Nur leere Theorieteile können gelöscht werden.", "fehler")
    else:
        db.session.delete(d)
        db.session.commit()
        flash("Theorieteil gelöscht.", "ok")
    return redirect(url_for(".index"))


@bp.route("/lp/theorie/kapitel/neu", methods=["GET", "POST"])
@bp.route("/lp/theorie/kapitel/<int:kapitel_id>", methods=["GET", "POST"])
@lp_required
def kapitel_bearbeiten(kapitel_id=None):
    from .lp import _bilder_speichern
    k = db.get_or_404(TheorieKapitel, kapitel_id) if kapitel_id else None
    dokumente = TheorieDokument.query.order_by(TheorieDokument.titel).all()
    if not dokumente:
        flash("Zuerst einen Theorieteil (z. B. ein Skript) anlegen.", "info")
        return redirect(url_for(".index"))
    if request.method == "POST":
        f = request.form
        dok = db.session.get(TheorieDokument, f.get("dokument_id", type=int) or 0)
        if not dok or not f.get("titel", "").strip():
            flash("Theorieteil und Titel sind Pflicht.", "fehler")
            return render_template("theorie/kapitel_form.html", k=k, dokumente=dokumente, **_auswahl())
        if k is None:
            k = TheorieKapitel()
            db.session.add(k)
        k.dokument = dok
        k.nummer = f.get("nummer", "").strip()[:20]
        k.titel = f["titel"].strip()[:200]
        k.text = f.get("text", "")
        k.sichtbar = f.get("sichtbar") == "1"
        k.lernziele = Lernziel.query.filter(Lernziel.id.in_([int(x) for x in f.getlist("lernziel") if x.isdigit()])).all()
        _bilder_speichern(k, f, request.files.getlist("bilder_neu"), KapitelBild, "theoriebilder")
        db.session.commit()
        flash("Kapitel gespeichert.", "ok")
        nrn = {b.nr for b in k.bilder}
        for nr in sorted(referenzierte_bilder(k.text) - nrn):
            flash(f"[[bild:{nr}]] verweist auf ein Bild, das es nicht gibt.", "info")
        if f.get("weiter") == "ansehen":
            return redirect(url_for(".kapitel", kapitel_id=k.id))
        return redirect(url_for(".index") + f"#dok-{k.dokument_id}")
    return render_template("theorie/kapitel_form.html", k=k, dokumente=dokumente,
                           vorauswahl_dokument=request.args.get("dokument", type=int), **_auswahl())


def _auswahl():
    return dict(themen=Thema.query.order_by(Thema.name).all(), bereiche=Bereich.query.order_by(Bereich.code).all())


@bp.route("/lp/theorie/kapitel/<int:kapitel_id>/loeschen", methods=["POST"])
@lp_required
def kapitel_loeschen(kapitel_id):
    k = db.get_or_404(TheorieKapitel, kapitel_id)
    dok = k.dokument_id
    db.session.delete(k)
    db.session.commit()
    flash("Kapitel gelöscht. Verknüpfungen mit Aufgaben wurden entfernt.", "ok")
    return redirect(url_for(".index") + f"#dok-{dok}")


@bp.route("/lp/theorie/vorschau", methods=["POST"])
@lp_required
def vorschau():
    """Live-Vorschau im Kapitel-Editor (aufgabe_id = Kapitel-ID, damit editor.js unverändert senden kann)."""
    d = request.get_json(force=True)
    k = db.session.get(TheorieKapitel, int(d.get("aufgabe_id") or 0)) if d.get("aufgabe_id") else None
    text = d.get("text", "")
    if k:
        return jsonify(aufgabe=str(kapitel_html(k, text)), loesung="", hinweis="")
    return jsonify(aufgabe=str(markup_html(text, {}, lambda b: "", zwischentitel=True)), loesung="", hinweis="")


def vorgeschlagene_kapitel(aufgabe_lernziel_ids):
    """Kapitel, die mindestens ein Lernziel mit der Aufgabe teilen."""
    if not aufgabe_lernziel_ids:
        return set()
    return {k.id for k in TheorieKapitel.query.filter(
        TheorieKapitel.lernziele.any(Lernziel.id.in_(aufgabe_lernziel_ids)))}
