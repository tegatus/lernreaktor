"""CLI-Befehle zum Einrichten:  flask --app app init-db [--demo]  ·  flask --app app create-lp"""
import json
import os

import click

from . import importers
from .models import Aufgabe, Klasse, Leistungsziel, User, db

SEED = os.path.join(os.path.dirname(__file__), "seed_data")


def seed_basisdaten():
    if not Leistungsziel.query.first():
        importers.import_kompetenzen(os.path.join(SEED, "Kompetenzen_BiVo.xlsx"))
    with open(os.path.join(SEED, "lernziele_molek1.txt"), encoding="utf-8") as f:
        importers.import_lernziele("qPCR", importers.parse_lernziele(f.read()))
    if not Aufgabe.query.first():
        with open(os.path.join(SEED, "aufgaben.json"), encoding="utf-8") as f:
            importers.import_aufgaben(json.load(f))


def seed_demo():
    if User.query.filter_by(benutzername="lp").first():
        return
    lp = User(benutzername="lp", anzeigename="Demo Lehrperson", rolle="lp")
    lp.set_passwort("lp-demo-2026")
    k = Klasse(name="LAB 2a (Demo)", lp=lp)
    db.session.add_all([lp, k])
    for bn, name in [("lea", "Lea Muster"), ("noah", "Noah Beispiel")]:
        u = User(benutzername=bn, anzeigename=name, rolle="lernende", klasse=k)
        u.set_passwort("lernen-2026")
        db.session.add(u)
    db.session.commit()


def register_cli(app):
    @app.cli.command("init-db")
    @click.option("--demo", is_flag=True, help="Demo-Lehrperson und -Lernende anlegen")
    def init_db(demo):
        """Tabellen anlegen, BiVo-Kompetenzen, qPCR-Lernziele und Beispielaufgaben importieren."""
        db.create_all()
        seed_basisdaten()
        if demo:
            seed_demo()
            click.echo("Demo-Zugänge: lp / lp-demo-2026 · lea / lernen-2026 · noah / lernen-2026")
        click.echo("Datenbank bereit.")

    @app.cli.command("set-admin")
    @click.argument("benutzername")
    @click.option("--entziehen", is_flag=True, help="Admin-Recht wieder entziehen")
    def set_admin(benutzername, entziehen):
        """Admin-Recht (z. B. BiVo-Kompetenzliste einlesen) für eine Lehrperson setzen oder entziehen."""
        u = User.query.filter_by(benutzername=benutzername.lower()).first()
        if not u or u.rolle != "lp":
            raise click.ClickException(f"Keine Lehrperson mit Benutzername «{benutzername}».")
        u.ist_admin = not entziehen
        db.session.commit()
        click.echo(f"{u.anzeigename}: Admin-Recht {'entzogen' if entziehen else 'gesetzt'}.")

    @app.cli.command("create-lp")
    @click.argument("benutzername")
    @click.argument("anzeigename")
    @click.password_option()
    def create_lp(benutzername, anzeigename, password):
        """Neues Lehrpersonen-Konto anlegen."""
        u = User(benutzername=benutzername.lower(), anzeigename=anzeigename, rolle="lp")
        u.set_passwort(password)
        db.session.add(u)
        db.session.commit()
        click.echo(f"Lehrperson {anzeigename} angelegt.")
