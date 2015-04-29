import os
basedir = os.path.abspath(os.path.dirname(__file__))

# Stuff for CSRF tokens & login
CSRF_ENABLED = True
state_dir = os.path.join(basedir, 'state')
if not os.path.isdir(state_dir):
    os.mkdir(state_dir)
csrf_keyfile = os.path.join(state_dir, 'csrf_secret')
if not os.path.exists(csrf_keyfile):
    with open("/dev/urandom", "rb") as rng:
        key = rng.read(64)
    with open(csrf_keyfile, "wb") as f:
        f.write(key)

SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(state_dir, 'database.db')

with open(csrf_keyfile, "rb") as f:
    SECRET_KEY = f.read()

# Email: use svmail to send emails for development purposes
MAIL_SERVER = "sv.aerofs.com"
MAIL_PORT = 25
MAIL_USE_TLS = False
MAIL_USE_SSL = False
MAIL_DEBUG = False
MAIL_USERNAME = None
MAIL_PASSWORD = None