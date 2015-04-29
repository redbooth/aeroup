# TODO: finish making this use tornado's async http client
import codecs
from io import BytesIO
import json
import urllib

from flask import url_for
import tornado
import tornado.httpclient
import tornado.httputil
import tornado.gen

class AuthorizationAPIClient(object):
    def __init__(self, aerofs_config):
        self.hostname = aerofs_config["hostname"]
        self.client_id = aerofs_config["client_id"]
        self.client_secret = aerofs_config["client_secret"]
        self.http_client = tornado.httpclient.AsyncHTTPClient()
        # TODO: do I care about the cert?
        # Python will make me use a tempfile for CA bundles, :(

    @tornado.gen.coroutine
    def get_access_token_with_code(self, code):
        headers = tornado.httputil.HTTPHeaders({
            "Content-Type": "application/x-www-form-urlencoded",
        })
        params = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": url_for('.oauth_complete', _external=True)
        }
        url = "https://{}/auth/token".format(self.hostname)
        request = tornado.httpclient.HTTPRequest(url,
                method='POST',
                data=urllib.urlencode(params),
                )
        response = yield self.http_client.fetch(request)
        reader = codecs.getreader("utf-8")
        return json.load(reader(response.buffer))

class APIClient(object):
    VERSION_PREFIX = "/api/v1.2"
    def __init__(self, aerofs_config, token):
        self.hostname = aerofs_config["hostname"]
        self.client_id = aerofs_config["client_id"]
        self.client_secret = aerofs_config["client_secret"]
        self.token = token
        self.cookies = []
        self.default_headers = tornado.httputil.HTTPHeaders({
            "Authorization": "Bearer {}".format(self.token),
            "Endpoint-Consistency": "strict",
        })
        self.http_client = tornado.httpclient.AsyncHTTPClient()

    @tornado.gen.coroutine
    def fetch(self, request, *args, **kwargs):
        resp = yield self.http_client.fetch(request, *args, **kwargs)
        self._process_cookies(resp)
        return resp

    def _process_cookies(self, response):
        # not very intelligent cookie persistence logic, just enough to make
        # the next request have any cookies set by the previous one which is
        # enough to get sticky API sessions
        cookies = []
        for header in response.headers.get_list("set-cookie"):
            cookie = header.split(';', 1)[0]
            cookies.append(cookie)
        self.cookies = cookies

    def _headers(self, **kwargs):
        headers = tornado.httputil.HTTPHeaders(self.default_headers, **kwargs)
        for cookie in self.cookies:
            headers.add("Cookie", cookie)
        return headers

    def _process_response(self, response):
        reader = codecs.getreader("utf-8")
        return json.load(reader(response.buffer))

    @tornado.gen.coroutine
    def get_token_info(self):
        url = tornado.httputil.url_concat("https://{}/auth/tokeninfo".format(self.hostname),
                {"access_token": self.token})
        # Embarrassingly, bifrost does not create a resource server for 3rd party apps,
        # so we cannot actually use our own client id/secret here.
        # We don't need to use the usual _headers here, since authorization is
        # done differently for /tokeninfo (and we're abusing the existing
        # resource server).
        request = tornado.httpclient.HTTPRequest(url,
                method='GET',
                auth_username='oauth-havre',
                auth_password='i-am-not-a-restful-secret',
                )
        response = yield self.http_client.fetch(request)
        reader = codecs.getreader("utf-8")
        return json.load(reader(response.buffer))

    @tornado.gen.coroutine
    def get_user_info(self, email):
        url = "https://{}{}/users/{}".format(self.hostname, self.VERSION_PREFIX, email)
        request = tornado.httpclient.HTTPRequest(url,
                method='GET',
                )
        response = yield self.fetch(request)
        return self._process_response(response)

    @tornado.gen.coroutine
    def create_folder(self, parent_folder, foldername):
        url = "https://{}{}/folders".format(self.hostname, self.VERSION_PREFIX)
        data = {"parent": parent_folder, "name": foldername}
        request = tornado.httpclient.HTTPRequest(
            url,
            method='POST',
            headers=self._headers(**{
                    "Content-Type": "application/json",
            }),
            body=json.dumps(data),
        )
        try:
            response = yield self.fetch(request)
        except tornado.httpclient.HTTPError as error:
            print ("Failed, response was:", error.response)
            raise error
        return self._process_response(response)

    @tornado.gen.coroutine
    def create_file(self, parent_folder, filename):
        url = "https://{}{}/files".format(self.hostname, self.VERSION_PREFIX)
        data = {"parent": parent_folder, "name": filename}
        request = tornado.httpclient.HTTPRequest(
            url,
            method='POST',
            headers=self._headers(**{
                    "Content-Type": "application/json",
            }),
            body=json.dumps(data),
        )
        response = yield self.fetch(request)
        return self._process_response(response)

    @tornado.gen.coroutine
    def set_file_contents(self, oid, stream):
        upload = yield self.start_content_upload(oid)

        MAX_CHUNK_SIZE = 1024 * 1024 # upload in 1MB chunks for now?
        current_chunk = stream.read(MAX_CHUNK_SIZE)

        while len(current_chunk) != 0:
            yield upload.upload_chunk(current_chunk)
            current_chunk = stream.read(MAX_CHUNK_SIZE)

        response = yield upload.commit()
        return response

    @tornado.gen.coroutine
    def start_content_upload(self, oid):
        url = "https://{}{}/files/{}/content".format(self.hostname, self.VERSION_PREFIX, oid)

        # Create upload identifier
        initial_headers = self._headers(**{
            "Content-Range": "bytes */*",
            "Content-Length": "0",
        })
        request = tornado.httpclient.HTTPRequest(
            url,
            method='PUT',
            headers=initial_headers,
            body="",
        )
        response = yield self.fetch(request)

        upload_id = response.headers["Upload-ID"]
        etag = response.headers.get("ETag")
        print ("upload id is {}".format(upload_id))

        upload = AsyncUpload(
            api_client = self,
            url = url,
            upload_id = upload_id,
            etag = etag,
        )
        return upload

class AsyncUpload(object):
    def __init__(self, url=None, api_client=None, upload_id=None, etag=None):
        self.url = url
        self.api_client = api_client
        self.upload_id = upload_id
        self.etag = etag
        self.total_bytes_sent = 0

    @tornado.gen.coroutine
    def upload_chunk(self, chunk):
        assert self.upload_id is not None
        # TODO: maybe shouldn't call api_client's _headers directly?
        headers = self.api_client._headers(**{
            "Upload-ID": self.upload_id,
            "Content-Range": "bytes {}-{}/*".format(self.total_bytes_sent, self.total_bytes_sent + len(chunk) - 1),
        })
        if self.etag: headers.add("If-Match", self.etag)
        print ("uploading {} bytes {}-{}".format(self.upload_id, self.total_bytes_sent, self.total_bytes_sent + len(chunk)))
        request = tornado.httpclient.HTTPRequest(
            self.url,
            method='PUT',
            headers=headers,
            body=chunk,
        )
        response = yield self.api_client.fetch(request)
        self.total_bytes_sent += len(chunk)
        return response

    @tornado.gen.coroutine
    def commit(self):
        assert self.upload_id is not None
        # TODO: maybe shouldn't call api_client's _headers directly?
        commit_headers = self.api_client._headers(**{
            "Upload-ID": self.upload_id,
            "Content-Range": "bytes */{}".format(self.total_bytes_sent),
            "Content-Length": "0",
        })
        if self.etag: headers.add("If-Match", self.etag)
        print ("committing {}".format(self.upload_id))
        request = tornado.httpclient.HTTPRequest(
            self.url,
            method='PUT',
            headers=commit_headers,
            body="",
        )
        response = yield self.api_client.fetch(request)
        # PUT replies with no content
        return response
