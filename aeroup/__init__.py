import flask
import flask_wtf
import tornado.web
import tornado.wsgi

from .config import db
from .config import login_manager
from .config import mail
from . import views


csrf = flask_wtf.csrf.CsrfProtect()


def create_app(debug):
    app = flask.Flask(__name__)
    app.config.from_object('config')
    app.debug = debug

    login_manager.init_app(app)
    login_manager.login_view = '.login'

    csrf.init_app(app)

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()

    mail.init_app(app)

    app.register_blueprint(views.blueprint, url_prefix='')
    return app


def create_tornado_app(app):
    application = tornado.web.Application([
        (r".*",
         tornado.web.FallbackHandler,
         dict(fallback=tornado.wsgi.WSGIContainer(app))),
    ], debug=app.debug)
    return application
