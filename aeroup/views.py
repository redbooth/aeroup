import datetime
import uuid

import aerofs
import flask
import flask.ext.login as flask_auth
import flask.json as json
import flask.views
import flask_mail

from .config import appconfig
from .config import db
from .config import login_manager
from .config import mail
from .models import Link
from .models import Upload
from .models import User


blueprint = flask.Blueprint('main', __name__, template_folder='templates')


@login_manager.user_loader
def load_user(userid):
    return User.query.filter_by(email=userid).first()


@blueprint.route('/', methods=['GET'])
@flask_auth.login_required
def hello():
    return flask.render_template('index.html')


@blueprint.route('/login', methods=['GET', 'POST'])
def login():
    if flask.request.method == 'POST':
        config = aerofs.api.InstanceConfiguration(appconfig['hostname'])
        creds = aerofs.api.AppCredentials(
            appconfig['client_id'], appconfig['client_secret'],
            flask.url_for('.oauth_complete', _external=True))
        auth = aerofs.api.APIAuthClient(config, creds)
        url = auth.get_authorization_url(['user.read', 'files.read',
                                          'files.write'])
        return flask.redirect(url)

    return flask.render_template('login.html')


@blueprint.route('/login_complete', methods=['GET'])
def oauth_complete():
    code = flask.request.args.get('code')

    config = aerofs.api.InstanceConfiguration(appconfig['hostname'])
    creds = aerofs.api.AppCredentials(
        appconfig['client_id'], appconfig['client_secret'],
        flask.url_for('.oauth_complete', _external=True))
    auth = aerofs.api.APIAuthClient(config, creds)

    token = auth.get_access_token_with_code(code)
    tokeninfo = auth.get_access_token_info(token)
    email = tokeninfo['principal']['attributes']['userid']

    user = User.query.filter_by(email=email).first()
    if not user:
        client = aerofs.api.APIClient(config, token)
        user_info = client.get_user(email)

        user = User()
        user.email = email
        user.first_name = user_info['first_name']
        user.last_name = user_info['last_name']

    user.oauth_token = token

    db.session.add(user)
    db.session.commit()

    flask_auth.login_user(user)
    return flask.redirect(flask.url_for('.hello'))


@blueprint.route('/logout', methods=['GET'])
def logout():
    flask_auth.logout_user()
    return flask.redirect(flask.url_for('.login'))


class LinksAPI(flask.views.MethodView):
    def get(self, link_id):
        if not link_id:
            links = Link.query.filter_by(
                receiver_id=flask_auth.current_user.id,
                deactivated=False).all()
            return flask.Response(json.dumps([l.to_dict() for l in links]),
                                  status=200, mimetype='application/json')

        link = Link.query.filter_by(
            receiver_id=flask_auth.current_user.id, uuid=link_id,
            deactivated=False).first_or_404()
        return flask.Response(json.dumps(link.to_dict()), status=200,
                              mimetype='application/json')

    def post(self, link_id):
        if not link_id:
            l = Link()
            l.uuid = uuid.uuid4().hex
            l.receiver_id = flask_auth.current_user.id

            # TODO: by default, no expiry and unlimited uploads
            #       in the future, allow users to configure this
            # l.expiry_date = datetime.datetime.today() + \
                    # datetime.timedelta(days=7)
            # l.uploads_allowed = 1

            db.session.add(l)
            db.session.commit()

            return flask.Response(json.dumps(l.to_dict()), status=201,
                                  mimetype='application/json')

        link = Link.query.filter_by(
            receiver_id=flask_auth.current_user.id,
            uuid=link_id).first_or_404()

        if not flask.request.json:
            flask.abort(400)

        email = flask.request.json.get('mail')
        if email:
            link.giver_email = email['giver']
            link.message = email.get('message', '')

            msg = flask_mail.Message(
                'Send me a file via AeroUP',
                body='{}\n\n{}'.format(
                    link.message,
                    flask.url_for('.upload', link_id=link.uuid,
                                  _external=True)),
                sender=(link.receiver.full_name(), link.receiver.email),
                recipients=[link.giver_email])
            mail.send(msg)

        valid_for = flask.request.json.get('valid_for')
        if valid_for:
            link.expiry_date = datetime.datetime.today() + \
                    datetime.timedelta(days=valid_for)

        max_uploads = flask.request.json.get('max_uploads')
        if max_uploads:
            link.uploads_allowed = max_uploads

        db.session.add(link)
        db.session.commit()

        return flask.Response(json.dumps(link.to_dict()), status=200,
                              mimetype='application/json')

    def delete(self, link_id):
        link = Link.query.filter_by(
            receiver_id=flask_auth.current_user.id,
            uuid=link_id).first_or_404()
        link.deactivated = True

        db.session.add(link)
        db.session.commit()

        return flask.Response(status=204)


links_view = flask_auth.login_required(LinksAPI.as_view('links_api'))
blueprint.add_url_rule('/links', defaults={'link_id': None},
                       view_func=links_view, methods=['GET', 'POST'])
blueprint.add_url_rule('/links/<link_id>', view_func=links_view,
                       methods=['GET', 'POST', 'DELETE'])


class UploadView(flask.views.MethodView):
    def get(self, link_id):
        link = Link.query.filter_by(uuid=link_id, deactivated=False).first()
        if not link:
            return flask.render_template('failure.html', link=None,
                                         error=False)

        return flask.render_template('upload.html', link=link)

    def post(self, link_id):
        link = Link.query.filter_by(uuid=link_id,
                                    deactivated=False).first_or_404()

        upload_date = datetime.datetime.now()
        if link.expires_at and upload_date >= link.expires_at:
            link.deactivated = True

            db.session.add(link)
            db.session.commit()

            return flask.redirect(flask.url_for('.failure', link_id=link_id))

        f = flask.request.files['uploaded-file']

        config = aerofs.api.InstanceConfiguration(appconfig['hostname'])
        client = aerofs.api.APIClient(config, link.receiver.oauth_token)

        try:
            folder_res = client.create_folder('root', 'AeroUP')
        except Exception as e:
            if e.response.status_code != 409:
                print e
                return flask.render_template('failure.html', link=None,
                                             error=e)

            folders = client.get_folder_children('root')['folders']
            for folder in folders:
                if folder['name'] == 'AeroUP':
                    folder_res = folder
                    break
            else:
                e.message += '. AeroUP folder not found.'
                print e
                return flask.render_template('failure.html', link=None,
                                             error=e)

        file_res = client.create_file(
            folder_res['id'],
            '{}-{}'.format(upload_date.isoformat(), f.filename))
        try:
            client.upload_file_content(file_res['id'], f.stream)
        except Exception as e:
            print e
            return flask.render_template('failure.html', link=None, error=e)

        upload = Upload()
        upload.link_id = link.id
        upload.filename = f.filename
        upload.size = f.stream.tell()
        upload.oid = file_res['id']

        link.uploads_performed += 1
        if link.uploads_allowed and \
                link.uploads_performed >= link.uploads_allowed:
            link.deactivated = True

        db.session.add(link)
        db.session.add(upload)
        db.session.commit()

        return flask.redirect(flask.url_for('.success', link_id=link_id))


upload_view = UploadView.as_view('upload')
blueprint.add_url_rule('/l/<link_id>', view_func=upload_view,
                       methods=['GET', 'POST'])


@blueprint.route('/l/<link_id>/failure', methods=['GET'])
def failure(link_id):
    link = Link.query.filter_by(uuid=link_id).first_or_404()
    return flask.render_template('failure.html', link=link)


@blueprint.route('/l/<link_id>/success', methods=['GET'])
def success(link_id):
    link = Link.query.filter_by(uuid=link_id).first_or_404()
    return flask.render_template('success.html', link=link)
