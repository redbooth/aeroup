import datetime

import flask

from .config import db


_EMAIL_MAX_LEN = 256
_USER_STRING_MAX_LEN = 256


class User(db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.Unicode(length=_EMAIL_MAX_LEN), index=True,
                      unique=True, nullable=False)
    oauth_token = db.Column(db.Unicode(length=256), nullable=False)
    first_name = db.Column(db.Unicode(length=_USER_STRING_MAX_LEN),
                           nullable=False)
    last_name = db.Column(db.Unicode(length=_USER_STRING_MAX_LEN),
                          nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.datetime.now,
                           nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.now,
                           onupdate=datetime.datetime.now, nullable=False)

    links = db.relationship('Link', backref='receiver', lazy='dynamic')

    def full_name(self):
        return '{} {}'.format(self.first_name, self.last_name)

    # The following four methods are used for Flask-Login integration
    def get_id(self):
        return self.email

    @staticmethod
    def is_active():
        return True

    @staticmethod
    def is_authenticated():
        return True

    @staticmethod
    def is_anonymous():
        return False


class Link(db.Model):
    __tablename__ = 'link'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(32), index=True, unique=True, nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'),
                            nullable=False)
    giver_email = db.Column(db.Unicode(length=_EMAIL_MAX_LEN))
    uploads_allowed = db.Column(db.Integer)
    uploads_performed = db.Column(db.Integer, default=0, nullable=False)
    message = db.Column(db.Unicode(length=4096))
    deactivated = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.datetime.now,
                           nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.now,
                           onupdate=datetime.datetime.now, nullable=False)
    expires_at = db.Column(db.DateTime)

    uploads = db.relationship('Upload', backref='link', lazy='dynamic')

    def to_dict(self):
        return {
            'uri': flask.url_for('.links_api', link_id=self.uuid),
            'public_uri': flask.url_for('.upload', link_id=self.uuid),
            'receiver': self.receiver.email,
            'giver': self.giver_email or '',
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat() \
                    if self.expires_at else '',
        }


class Upload(db.Model):
    __tablename__ = 'upload'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    link_id = db.Column(db.Integer, db.ForeignKey('link.id'), nullable=False)
    filename = db.Column(db.Unicode(length=_USER_STRING_MAX_LEN),
                         nullable=False)
    size = db.Column(db.Integer, nullable=False)
    oid = db.Column(db.String(length=64), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.datetime.now,
                           nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.now,
                           onupdate=datetime.datetime.now, nullable=False)
