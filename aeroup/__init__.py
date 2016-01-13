import os

from flask import Flask
from flask_wtf.csrf import CsrfProtect
from migrate.exceptions import DatabaseAlreadyControlledError
from migrate.versioning import api
from tornado.web import Application
from tornado.web import FallbackHandler
from tornado.wsgi import WSGIContainer

from .config import db
from .config import login_manager
from .config import mail
from . import views


csrf = CsrfProtect()


def migrate_database(app):
    _moddir = os.path.abspath(os.path.dirname(__file__))
    repo = os.path.join(_moddir, 'migrations')

    db_uri = app.config['SQLALCHEMY_DATABASE_URI']

    # If the DB isn't under version control yet, add the migrate_version table
    # at version 0
    try:
        api.version_control(db_uri, repo)
    except DatabaseAlreadyControlledError:
        pass

    # Apply all known migrations to bring the schema up to date
    api.upgrade(db_uri, repo, api.version(repo))


def create_app():
    app = Flask(__name__)
    app.config.from_object('config')

    login_manager.init_app(app)
    login_manager.login_view = '.login'

    csrf.init_app(app)

    _moddir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_MIGRATE_REPO'] = os.path.join(_moddir, 'migrations')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    mail.init_app(app)

    app.register_blueprint(views.blueprint, url_prefix='')
    return app


def create_tornado_app(app):
    application = Application([
        (r".*", FallbackHandler, dict(fallback=WSGIContainer(app))),
    ], debug=app.debug)
    return application
