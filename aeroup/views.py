import datetime
# Python 2/3 compat
try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode
import uuid

from flask import Blueprint, Response, abort, current_app, json, redirect, render_template, request, url_for
from flask.views import MethodView
from flask.ext.login import current_user, login_user, login_required, logout_user
from flask_mail import Message

from . import login_manager, db, mail, models, apiclient

blueprint = Blueprint('main', __name__, template_folder='templates')


@login_manager.user_loader
def load_user(userid):
    return models.User.query.filter_by(email=userid).first()

@blueprint.route('/', methods=['GET'])
@login_required
def hello():
    # TODO: pass in logged in user info as current_user
    # so we can use name and email in email template
    return render_template('index.html', current_user=current_user)

@blueprint.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        aerofs_conf = current_app.config['AEROFS_CONFIG']
        params = {
            "response_type": "code",
            "client_id": aerofs_conf["client_id"],
            "redirect_uri": url_for('.oauth_complete', _external=True),
            "scope": "user.read,files.appdata",
            "state": "lolol",
        }
        url = "https://{}/authorize?{}".format(aerofs_conf['hostname'], urlencode(params))
        return redirect(url)
    return render_template('login.html')

@blueprint.route('/login_complete', methods=['GET'])
def oauth_complete():
    # expect query params: 'code' and 'state'
    code = request.args.get('code')
    state = request.args.get('state')
    auth_client = apiclient.AuthorizationAPIClient(current_app.config['AEROFS_CONFIG'])
    token = auth_client.get_access_token_with_code(code)
    client = apiclient.APIClient(current_app.config['AEROFS_CONFIG'], token['access_token'])
    tokeninfo = client.get_token_info()
    userid = tokeninfo["principal"]["attributes"]["userid"]
    user = models.User.query.filter_by(email=userid).first()
    if user is None:
        userinfo = client.get_user_info(userid)
        user = models.User()
        user.email = userid
        user.first_name = userinfo['first_name']
        user.last_name = userinfo['last_name']
    user.oauth_token = token['access_token']
    db.session.add(user)
    db.session.commit()
    print ("added {}".format(userid))
    login_user(user)
    return redirect(url_for('.hello'))

@blueprint.route('/logout', methods=['GET'])
def logout():
    logout_user()
    return redirect(url_for('.login'))

class LinksAPI(MethodView):
    def get(self, link_id):
        if link_id is None:
            # List links
            links = models.Link.query.filter_by(receiver_id=current_user.id, deactivated=False).all()
            return Response(json.dumps([ l.to_dict() for l in links ]), status=200, mimetype='application/json')
        else:
            # get info for particular link
            link = models.Link.query.filter_by(receiver_id=current_user.id, uuid=link_id, deactivated=False).first_or_404()
            return Response(json.dumps(link.to_dict()), status=200, mimetype='application/json')

    def post(self, link_id):
        if link_id is not None:
            return self.handle_post_update_link(link_id)
        else:
            return self.handle_post_new_link()

    def handle_post_new_link(self):
        l = models.Link()
        l.uuid = uuid.uuid4().hex
        l.receiver_id = current_user.id
        l.giver_email = None
        # TODO: get a functional token here
        l.token = "lololololololol not a real token"
        # TODO: allow user-specified expiry dates?
        l.expiry_date = datetime.datetime.today() + datetime.timedelta(days=14)
        l.uploads_allowed = 1
        l.uploads_performed = 0
        l.deactivated = False
        db.session.add(l)
        db.session.commit()
        return Response(json.dumps(l.to_dict()), status=201, mimetype='application/json')

    def handle_post_update_link(self, link_id):
        link = models.Link.query.filter_by(receiver_id=current_user.id, uuid=link_id).first_or_404()
        if not request.json:
            abort(400)
        needs_update = False
        if 'giver' in request.json:
            link.giver_email = request.json['giver']
            needs_update = True
        if 'message' in request.json:
            link.message = request.json['message']
            needs_update = True
        if needs_update:
            db.session.add(link)
            db.session.commit()
            msg = Message("Send me a file via AeroUP", sender=(link.receiver.full_name(), link.receiver.email), recipients=[link.giver_email])
            msg.body = link.message + "\n\n" + url_for('.upload', token=link.uuid, _external=True)
            mail.send(msg)

        return Response(json.dumps(link.to_dict()), status=200, mimetype='application/json')

    def delete(self, link_id):
        link = models.Link.query.filter_by(receiver_id=current_user.id, uuid=link_id).first_or_404()
        link.deactivated = True
        db.session.add(link)
        db.session.commit()
        return Response(status=204)


links_view = login_required(LinksAPI.as_view('links_api'))
blueprint.add_url_rule('/links', defaults={'link_id': None}, view_func=links_view, methods=['GET', 'POST'])
blueprint.add_url_rule('/links/<link_id>', view_func=links_view, methods=['GET', 'POST', 'DELETE'])

class UploadView(MethodView):
    def get(self, token):
        # TODO: also nice error handling for used-up or invalid links
        link = models.Link.query.filter_by(uuid=token, deactivated=False).first_or_404()
        return render_template('upload.html', link={'token': token, 'receiver': { 'name': link.receiver.full_name() }})

    def post(self, token):
        link = models.Link.query.filter_by(uuid=token, deactivated=False).first_or_404()
        # TODO: check if link is expired/consumed, if so abort
        upload_date = datetime.datetime.today()
        f = request.files['uploaded-file']
        client = apiclient.APIClient(current_app.config['AEROFS_CONFIG'], link.receiver.oauth_token)
        # TODO: make this fail nicely when clients are offline or what have you
        # 503 Server Error: Service Unavailable
        folder_res = client.create_folder("appdata", upload_date.isoformat())
        file_res = client.create_file(folder_res["id"], f.filename)
        file_content_res = client.set_file_contents(file_res["id"], f.stream)

        upload = models.Upload()
        upload.link_id = link.id
        upload.upload_date = upload_date
        upload.filename = f.filename
        upload.size = f.stream.tell()
        upload.oid = file_res["id"]
        db.session.add(upload)
        db.session.commit()

        return redirect(url_for('.thankyou', token=token))

upload_view = UploadView.as_view('upload')
blueprint.add_url_rule('/l/<token>', view_func=upload_view, methods=['GET', 'POST'])

@blueprint.route('/l/<token>/success', methods=['GET', 'POST'])
def thankyou(token):
    # TODO: pass in file metadata?
    link = models.Link.query.filter_by(uuid=token).first_or_404()
    return render_template('thankyou.html', link=link)
