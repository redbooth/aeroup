import os

from flask import Flask
from flask_wtf.csrf import CsrfProtect
from tornado.web import Application
from tornado.web import FallbackHandler
from tornado.wsgi import WSGIContainer

from .config import db
from .config import login_manager
from .config import mail
from . import views


csrf = CsrfProtect()


def create_app(debug):
    app = Flask(__name__)
    app.config.from_object('config')
    app.debug = debug

    login_manager.init_app(app)
    login_manager.login_view = '.login'

    csrf.init_app(app)

    _moddir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_MIGRATE_REPO'] = os.path.join(_moddir, 'migrations')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()

    mail.init_app(app)

    app.register_blueprint(views.blueprint, url_prefix='')
    return app


def create_tornado_app(app):
    application = Application([
        (r".*", FallbackHandler, dict(fallback=WSGIContainer(app))),
    ], debug=app.debug)
    return application
