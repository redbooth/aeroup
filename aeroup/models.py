from flask import url_for

from . import db

_EMAIL_MAX_LEN = 256
_USER_STRING_MAX_LEN = 256

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.Unicode(length=_EMAIL_MAX_LEN), index=True, unique=True, nullable=False)
    # TODO: make these nonnull on breaking DB change
    oauth_token = db.Column(db.Unicode(length=256))
    first_name = db.Column(db.Unicode(length=_USER_STRING_MAX_LEN))
    last_name = db.Column(db.Unicode(length=_USER_STRING_MAX_LEN))
    links = db.relationship("Link", backref="receiver", lazy="dynamic")
    def full_name(self):
        return "{} {}".format(self.first_name, self.last_name)
    # The following four methods are used for Flask-Login integration
    def is_active(self):
        return True
    def is_authenticated(self):
        return True
    def is_anonymous(self):
        return False
    def get_id(self):
        return self.email

class Link(db.Model):
    __tablename__ = 'link'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(32), index=True, unique=True, nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    giver_email = db.Column(db.Unicode(length=_EMAIL_MAX_LEN), nullable=True)
    token = db.Column(db.Unicode(length=256), nullable=False)
    # Ideally create_date would be nonnull, but migrations are hard
    # TODO: flatten migrations into single initial migration
    create_date = db.Column(db.DateTime, nullable=True)
    expiry_date = db.Column(db.DateTime, nullable=True)
    uploads_allowed = db.Column(db.Integer, nullable=True)
    uploads_performed = db.Column(db.Integer, nullable=True)
    message = db.Column(db.Unicode(length=4096), nullable=True)
    deactivated = db.Column(db.Boolean)
    uploads = db.relationship("Upload", backref="link", lazy="dynamic")
    def to_dict(self):
        d = {
            "uri": url_for('.links_api', link_id=self.uuid),
            "public_uri": url_for('.upload', token=self.uuid),
            "receiver": self.receiver.email,
            "giver": self.giver_email or "",
            "message": self.message or "",
            "create_date": self.create_date.isoformat() if self.create_date else "",
            "expiry_date": self.expiry_date.isoformat() if self.create_date else "",
            "expires_after_uses": self.uploads_allowed or -1,
            "uploads": [ u.to_dict() for u in self.uploads.order_by('upload_date') ],
        }
        return d

class Upload(db.Model):
    __tablename__ = 'uploads'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    link_id = db.Column(db.Integer, db.ForeignKey('link.id'), nullable=False)
    upload_date = db.Column(db.DateTime, nullable=False)
    filename = db.Column(db.Unicode(length=_USER_STRING_MAX_LEN), nullable=False)
    size = db.Column(db.Integer, nullable=False)
    oid = db.Column(db.String(length=64), nullable=False)
    def to_dict(self):
        return {
            "date": self.upload_date.isoformat(),
            "filename": self.filename,
            "size": self.size,
        }
