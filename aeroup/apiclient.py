from io import BytesIO

from flask import url_for
import requests

class AuthorizationAPIClient(object):
    def __init__(self, aerofs_config):
        self.hostname = aerofs_config["hostname"]
        self.client_id = aerofs_config["client_id"]
        self.client_secret = aerofs_config["client_secret"]
        # TODO: do I care about the cert?
        # Python will make me use a tempfile for CA bundles, :(

    def get_access_token_with_code(self, code):
        params = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": url_for('.oauth_complete', _external=True)
        }
        url = "https://{}/auth/token".format(self.hostname)
        res = requests.post(url, data=params)
        res.raise_for_status()
        return res.json()

class APIClient(object):
    VERSION_PREFIX = "/api/v1.2"
    def __init__(self, aerofs_config, token):
        self.hostname = aerofs_config["hostname"]
        self.client_id = aerofs_config["client_id"]
        self.client_secret = aerofs_config["client_secret"]
        self.token = token
        self.session = requests.Session()
        self.session.headers = self.auth_headers()
    # TODO: allow interesting interactions with the API backend

    def auth_headers(self):
        return {"Authorization": "Bearer {}".format(self.token),
                "Endpoint-Consistency": "strict"}

    def get_token_info(self):
        url = "https://{}/auth/tokeninfo".format(self.hostname)
        params = {"access_token": self.token}
        # Embarrassingly, bifrost does not create a resource server for 3rd party apps,
        # so we cannot actually use our own client id/secret here.
        res = requests.get(url, params=params, auth=('oauth-havre', 'i-am-not-a-restful-secret'))
        res.raise_for_status()
        return res.json()

    def get_user_info(self, email):
        url = "https://{}{}/users/{}".format(self.hostname, self.VERSION_PREFIX, email)
        res = self.session.get(url)
        res.raise_for_status()
        return res.json()

    def create_folder(self, parent_folder, foldername):
        url = "https://{}{}/folders".format(self.hostname, self.VERSION_PREFIX)
        data = {"parent": parent_folder, "name": foldername}
        res = self.session.post(url, json=data)
        res.raise_for_status()
        return res.json()

    def create_file(self, parent_folder, filename):
        url = "https://{}{}/files".format(self.hostname, self.VERSION_PREFIX)
        data = {"parent": parent_folder, "name": filename}
        res = self.session.post(url, json=data)
        res.raise_for_status()
        return res.json()

    def set_file_contents(self, oid, stream):
        url = "https://{}{}/files/{}/content".format(self.hostname, self.VERSION_PREFIX, oid)
        MAX_CHUNK_SIZE = 1024 * 1024 # upload in 1MB chunks for now?

        # Create upload identifier
        initial_headers = {
            "Content-Range": "bytes */*",
            "Content-Length": "0",
        }
        res = self.session.put(url, headers=initial_headers)
        res.raise_for_status()
        upload_id = res.headers["Upload-ID"]
        etag = res.headers.get("ETag")
        print ("upload id is {}".format(upload_id))
        current_chunk = stream.read(MAX_CHUNK_SIZE)
        total_bytes_sent = 0

        # Upload content, one chunk at a time
        while len(current_chunk) != 0:
            headers = {
                "Upload-ID": upload_id,
                "Endpoint-Consistency": "strict",
                "Content-Range": "bytes {}-{}/*".format(total_bytes_sent, total_bytes_sent + len(current_chunk) - 1),
            }
            if etag: headers["If-Match"] = etag
            print ("uploading {} bytes {}-{}".format(upload_id, total_bytes_sent, total_bytes_sent + len(current_chunk)))
            res = self.session.put(url, headers=headers, data=BytesIO(current_chunk))
            res.raise_for_status()
            total_bytes_sent += len(current_chunk)
            current_chunk = stream.read(MAX_CHUNK_SIZE)

        # Commit upload
        commit_headers = {
            "Upload-ID": upload_id,
            "Endpoint-Consistency": "strict",
            "Content-Range": "bytes */{}".format(total_bytes_sent),
            "Content-Length": "0",
        }
        if etag: headers["If-Match"] = etag
        print ("committing {}".format(upload_id))
        res = self.session.put(url, headers=commit_headers)
        res.raise_for_status()
        # Not res.json() because this PUT replies with no content
        return res
