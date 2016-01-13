import os
import json

import flask.ext.login
import flask.ext.sqlalchemy
import flask_mail


db = flask.ext.sqlalchemy.SQLAlchemy()
login_manager = flask.ext.login.LoginManager()
mail = flask_mail.Mail()


# Look for an appconfig.json downloaded from the AeroFS Appliance
if not os.path.exists('appconfig.json'):
    raise Exception('Expected to find {}/appconfig.json'.format(os.getcwd()))

with open('appconfig.json', 'r') as f:
    appconfig = json.load(f)
