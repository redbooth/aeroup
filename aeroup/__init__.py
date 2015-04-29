import os
import json
import imp

from flask import Flask
from flask.ext.login import LoginManager
from flask.ext.sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_wtf.csrf import CsrfProtect
from migrate.versioning import api
from migrate.exceptions import DatabaseAlreadyControlledError
from tornado.wsgi import WSGIContainer
from tornado.web import FallbackHandler, Application

login_manager = LoginManager()

csrf = CsrfProtect()

db = SQLAlchemy()

mail = Mail()

from . import models, views, asyncviews

def migrate_database(app):
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']
    _moddir = os.path.abspath(os.path.dirname(__file__))
    repo = os.path.join(_moddir, 'migrations')
    # If the DB isn't under version control yet, add the migrate_version table
    # at version 0
    try:
        api.version_control(db_uri, repo)
    except DatabaseAlreadyControlledError:
        # we already own the DB
        pass

    # Apply all known migrations to bring the schema up to date
    api.upgrade(db_uri, repo, api.version(repo))

def create_app():
    app = Flask(__name__)

    app.config.from_object('config')

    try:
        imp.find_module('additional_config')
        found = True
    except ImportError:
        found = False

    # Only try to apply config from additional_config if the module exists.
    if found:
        app.config.from_object('additional_config')

    # Look for an appconfig.json downloaded from the AeroFS Appliance
    if not os.path.exists('appconfig.json'):
        raise Exception("Expected to find appconfig.json at {}".format(os.getcwd()))
    with open('appconfig.json') as f:
        app.config['AEROFS_CONFIG'] = json.load(f)

    login_manager.init_app(app)
    login_manager.login_view = '.login'

    csrf.init_app(app)

    db.init_app(app)
    _moddir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_MIGRATE_REPO'] = os.path.join(_moddir, 'migrations')

    mail.init_app(app)

    app.register_blueprint(views.blueprint, url_prefix="")
    return app

def create_tornado_app(flask_app):
    application = Application([
        (r"/l/(.{32})", asyncviews.TornadoMainHandler, dict(app=flask_app, database=db)),
        (r".*", FallbackHandler, dict(fallback=WSGIContainer(flask_app))),
    ], debug=flask_app.debug)
    return application
