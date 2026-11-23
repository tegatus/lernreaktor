import os
import secrets

from flask import Flask
from flask_login import LoginManager

from .models import User, db

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Bitte melde dich an."


@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))


def create_app(config=None):
    # LERNREAKTOR_INSTANCE: Ordner für Datenbank (SQLite), Secret Key usw. – im Betrieb ausserhalb des Codes
    app = Flask(__name__, instance_relative_config=True, instance_path=os.environ.get("LERNREAKTOR_INSTANCE") or None)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or _persistent_secret(app.instance_path),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL")
        or "sqlite:///" + os.path.join(app.instance_path, "lernreaktor.sqlite"),
        UPLOAD_DIR=os.environ.get("UPLOAD_DIR") or os.path.join(app.instance_path, "dateien"),
        MAX_CONTENT_LENGTH=60 * 1024 * 1024,
    )
    if config:
        app.config.update(config)
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from .sicherheit import csrf_token, einrichten
    einrichten(app)

    app.jinja_env.globals["csrf_token"] = csrf_token

    from .aufgabentypen import TYPEN
    from .models import ANTWORTFORMATE, BILDGROESSEN, VERWENDUNGEN
    app.jinja_env.globals.update(ANTWORTFORMATE=ANTWORTFORMATE, VERWENDUNGEN=VERWENDUNGEN, BILDGROESSEN=BILDGROESSEN,
                                 AUFGABENTYPEN=TYPEN)

    @app.template_filter("datum")
    def _datum(d, mit_zeit=False):
        if not d:
            return ""
        return d.strftime("%d.%m.%Y %H:%M" if mit_zeit else "%d.%m.%Y")

    from .markup import markup_html
    app.jinja_env.filters["markup"] = markup_html

    @app.template_filter("pkt")
    def _pkt(p):
        return "–" if p is None else f"{p:g}"

    from . import auth, lernende, lp
    app.register_blueprint(auth.bp)
    app.register_blueprint(lernende.bp)
    app.register_blueprint(lp.bp)

    from .seed import register_cli
    register_cli(app)

    with app.app_context():
        db.create_all()
        from .models import migriere_einzelbilder, spalten_ergaenzen
        spalten_ergaenzen()
        migriere_einzelbilder()
    return app


def _persistent_secret(instance_path):
    pfad = os.path.join(instance_path, "secret_key")
    if not os.path.exists(pfad):
        with open(pfad, "w") as f:
            f.write(secrets.token_hex(32))
        os.chmod(pfad, 0o600)
    with open(pfad) as f:
        return f.read().strip()
