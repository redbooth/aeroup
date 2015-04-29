import datetime
import hashlib
from io import BytesIO
import re
import time

import tornado
from concurrent.futures import ThreadPoolExecutor
from tornado.web import RequestHandler, stream_request_body, asynchronous
from tornado import gen
from tornado.concurrent import return_future
from functools import partial

from . import models
from . import asyncapiclient as apiclient

DB_WORK_THREAD = ThreadPoolExecutor(max_workers=1)

BACKEND_CHUNK_SIZE = 1024 * 1024 # 1MB chunks to backend

class HTTPPart(object):
    """Holder object for headers, body, hasher"""
    def __init__(self):
        self.headers = tornado.httputil.HTTPHeaders()
        self.body = BytesIO()
        self.hasher = hashlib.sha1()

class StreamingMultipartParser(object):
    states = [
        "START",
        "EXPECT_HEADER",
        "EXPECT_PART_DATA",
        "FINISHED",
    ]
    LINE_SEP = b'\r\n'

    def __init__(self, boundary, condition=None, trigger=None, on_finished=None):
        self.state = "START"
        self.incoming_buffer = b""
        self.boundary = boundary
        self.parts = []
        self.part_in_progress = None
        self.condition = condition or self.default_condition
        self.trigger = trigger or self.default_trigger
        self.on_finished = on_finished or self.default_on_finished
        self.total_consumed = 0

    @gen.coroutine
    def transition(self, new_state):
        # Optional: add hooks on transitions?
        #print("Transitioning from", self.state, "to", new_state)
        if new_state == "EXPECT_HEADER" or new_state == "FINISHED":
            if self.part_in_progress:
                yield self.trigger(self.part_in_progress)
                self.parts.append(self.part_in_progress)
                #print("saving part", self.part_in_progress)
            self.part_in_progress = HTTPPart()
        if new_state == "EXPECT_PART_DATA":
            #print("Streaming body of part", self.part_in_progress)
            pass
        self.state = new_state

    def default_condition(self, part_in_progress):
        return len(part_in_progress.body.getbuffer()) >= BACKEND_CHUNK_SIZE

    @gen.coroutine
    def default_trigger(self, part_in_progress):
        pass

    @gen.coroutine
    def default_on_finished(self, part_in_progress):
        yield self.trigger(part_in_progress)

    @property
    def start_boundary(self):
        return b'--' + self.boundary + self.LINE_SEP

    @property
    def body_end_prefix(self):
        return self.LINE_SEP + b'--' + self.boundary

    @property
    def mid_boundary(self):
        return self.body_end_prefix + self.LINE_SEP

    @property
    def end_boundary(self):
        return self.body_end_prefix + b'--'

    @gen.coroutine
    def append_to_current_body(self, buf):
        self.part_in_progress.body.write(buf)
        self.part_in_progress.hasher.update(buf)
        if self.condition(self.part_in_progress):
            future = self.trigger(self.part_in_progress)
            yield future

    @gen.coroutine
    def handle_start(self):
        # read until you see --boundary\r\n
        index = self.incoming_buffer.find(self.start_boundary)
        if index != -1:
            # drop preamble and boundary
            self.incoming_buffer = self.incoming_buffer[index + len(self.start_boundary):]
            # transition to EXPECT_HEADER
            yield self.transition("EXPECT_HEADER")
            return True
        return False

    @gen.coroutine
    def handle_expect_header(self):
        # Part headers.  A header is complete when we reach a \r\n sequence.
        index = self.incoming_buffer.find(self.LINE_SEP)
        # If there was no content between the last \r\n and this one, then
        # we have an empty line and we're done reading headers.
        if index == 0:
            self.incoming_buffer = self.incoming_buffer[len(self.LINE_SEP):]
            yield self.transition("EXPECT_PART_DATA")
            return True
        # Otherwise, we should save the content of the header.
        if index > 0:
            header, self.incoming_buffer = self.incoming_buffer[0:index], self.incoming_buffer[index + len(self.LINE_SEP):]
            self.part_in_progress.headers.parse_line(header.decode('utf-8'))
            return True
        return False

    @gen.coroutine
    def handle_expect_part_data(self):
        # Part body.  Anything that isn't a prefix match for mid separator or end
        # separator is definitely part of the body.
        # Streaming caveat: anything that *is* a prefix match for the mid
        # separator can't go into the body until we have sufficient data to
        # prove that it will or won't be a match

        # search for the mid boundary or the end boundary from the left
        index = self.incoming_buffer.find(self.body_end_prefix)
        if index == -1:
            # We don't see a full boundary.  Look backwards from the end to see if
            # a prefix of body_end_prefix is a suffix of self.incoming_buffer.
            # We can safely add everything that isn't part of the largest matching prefix to the body.
            for pattern_len in range(len(self.body_end_prefix)-1, 0, -1):
                pattern = self.body_end_prefix[0:pattern_len]
                if self.incoming_buffer.endswith(pattern):
                    # Save the possible prefix in incoming_buffer, but add the rest to the part body.
                    yield self.append_to_current_body(self.incoming_buffer[0:-pattern_len])
                    self.incoming_buffer = self.incoming_buffer[-pattern_len:]
                    # We can't make any more progress until we have more data, so return False.
                    return False
            # No prefix matched.  We can move the whole buffer to the part body.  No more progress
            # can be made without additional data.
            yield self.append_to_current_body(self.incoming_buffer)
            self.incoming_buffer = b""
            return False
        else:
            # Figure out if this is a mid boundary, an end boundary, or neither.
            # First, check that we have enough data to tell:
            if index + 2 >= len(self.incoming_buffer):
                # Insufficient data, wait for more.
                return False
            # Next, is this a mid boundary?
            if self.incoming_buffer[index : index + len(self.mid_boundary)] == self.mid_boundary:
                # Yes?  finish up this part, transition to EXPECT_HEADER
                yield self.append_to_current_body(self.incoming_buffer[0:index])
                self.incoming_buffer = self.incoming_buffer[index + len(self.mid_boundary):]
                yield self.transition("EXPECT_HEADER")
                return True
            # Is this the final boundary?
            if self.incoming_buffer[index : index + len(self.end_boundary)] == self.end_boundary:
                # Yes?  finish up this part, transition to FINISHED
                yield self.append_to_current_body(self.incoming_buffer[0:index])
                self.incoming_buffer = self.incoming_buffer[index + len(self.end_boundary):]
                yield self.transition("FINISHED")
                return True
            # At this point, we found no actual boundary, just something that
            # matched body_end_prefix (which is not sufficient to be a
            # boundary).  Since we now know it's not the boundary, we can add
            # everything up to the end of the body_end_prefix to the body.  And
            # then we should try again, because there might be another match
            # later on in this buffer.
            # BUG: maybe we should only add the first byte of the
            # body_end_prefix, in case the boundary is self-overlapping?
            # Implementations likely prevent this, but better to be more correct?
            yield self.append_to_current_body(self.incoming_buffer[0:index + len(self.body_end_prefix)])
            self.incoming_buffer = self.incoming_buffer[index + len(self.body_end_prefix):]
            return True
        return False

    @gen.coroutine
    def handle_finished(self):
        # Ignore anything in the epilogue
        return False

    @gen.coroutine
    def got_bytes(self, buf):
        # Append new bytes to existing buffer
        self.incoming_buffer = self.incoming_buffer + buf

        # Attempt to process any state transitions the new data could have
        # triggered.  If the handler was able to do work, see if it can do any
        # more.  Repeat until no more work can be done.
        do_more = True
        while do_more:
            handler = {
                "START": self.handle_start,
                "EXPECT_HEADER": self.handle_expect_header,
                "EXPECT_PART_DATA": self.handle_expect_part_data,
                "FINISHED": self.handle_finished,
            }[self.state]
            do_more = yield handler()

@stream_request_body
class TornadoMainHandler(RequestHandler):
    def initialize(self, app, database):
        # Reject files larger than 8 GB, for now.  This server can stream things
        # arbitrarily large, but this seems a reasonable upper bound for now.
        self.request.connection.set_max_body_size(8 * 1024 * 1024 * 1024)
        self.app = app
        self.db = database
        self.oauth_token = None
        self.api_client = None
        self.streaming_parser = None
        self.folder_res = None
        self.file_res = None
        self.folder_res_future = None
        self.file_res_future = None
        self.upload_handle = None
        self.upload_handle_future = None

    def __str__(self):
        return "\n".join([
            "TornadoMainHandler(",
            "\tstreaming_parser: {}".format(self.streaming_parser),
            "\tfolder_res_future: {}".format(self.folder_res_future),
            "\tfolder_res: {}".format(self.folder_res),
            "\tfile_res_future: {}".format(self.file_res_future),
            "\tfile_res: {}".format(self.file_res),
            "\tupload_handle_future: {}".format(self.upload_handle_future),
            "\tupload_handle: {}".format(self.upload_handle),
            ")",
        ])

    def get(self, token):
        # This whole function is some ridiculous hackery to run the Flask
        # handler from within the tornado handler.
        # First, patch out the request body, since WSGIContainer.environ
        # expects it to be fully read.
        temp, self.request.body = self.request.body, None
        environ = tornado.wsgi.WSGIContainer.environ(self.request)
        self.request.body = temp
        # Then, provide a minimal WSGI middleware implementation
        data = {}
        reply = []
        def start_response(status, response_headers, exc_info=None):
            data["status"] = status
            data["headers"] = response_headers
            return reply.append
        # Set up the Flask request environment...
        with self.app.request_context(environ):
            # Then run the Flask handler
            try:
                wsgi_handler = self.app.full_dispatch_request()
            except Exception as e:
                wsgi_handler = self.app.make_response(self.app.handle_exception(e))
            # Read any yielded reply chunks into a buffer
            for item in wsgi_handler(environ, start_response):
                reply.append(item)
        # Adapt the WSGI response to tornado's RequestHandler API
        if "status" in data:
            code, human_desc = data["status"].split(" ", 1)
            self.set_status(int(code, 10), reason=human_desc)
        if "headers" in data:
            for header in data["headers"]:
                self.add_header(header[0], header[1])
        body = b"".join(reply)
        # Finally, write the response body to the client.
        self.write(body)

    @gen.coroutine
    def post(self, token):
        assert self.streaming_parser
        assert self.streaming_parser.state == "FINISHED"
        if not self.upload_handle:
            yield self.get_upload_handle()
        yield self.upload_handle.commit()
        # Redirect to success page
        success_uri = self.request.uri + '/success'
        self.redirect(success_uri)

    def url_uuid(self):
        self.request.uri
        m = re.match("/l/(.{32})", self.request.uri)
        if not m:
            raise ValueError("URI did not include a valid uuid")
        return m.groups(1)[0]

    @return_future
    def do_db_work(self, callback=None):
        with self.app.app_context():
            link = self.db.session.query(models.Link).filter_by(uuid=self.url_uuid(), deactivated=False).first()
            if not link:
                raise tornado.web.HTTPError(404)
            oauth_token = link.receiver.oauth_token
            #print ("OAuth token is:", oauth_token)
            callback(oauth_token)

    @gen.coroutine
    def prepare(self, callback=None):
        # queue the DB work and the access checks off-thread
        #print ("prepare", self.url_uuid())
        #print (self.request)
        self.db_work_future = DB_WORK_THREAD.submit(
            self.do_db_work
        )
        if callback is not None:
            self.db_work_future.add_done_callback(
                    lambda fut: tornado.ioloop.IOLoop.instance().add_callback(
                        partial(callback, fut)
                    )
            )
        oauth_token_future = yield self.db_work_future
        oauth_token = oauth_token_future.result()
        self.api_client = apiclient.APIClient(self.app.config['AEROFS_CONFIG'], oauth_token)
        # We should now have an oauth token and an api client
        # If this is a streaming POST, check that it's mime/multipart and
        # extract the Boundary from the headers
        if self.request.method == 'POST':
            content_type = self.request.headers.get("Content-Type", "")
            assert content_type.startswith("multipart/form-data")
            fields = content_type.split(";")
            for field in fields:
                k, sep, v = field.strip().partition("=")
                if k == "boundary" and v:
                    if v.startswith('"') and v.endswith('"'):
                        v = v[1:-1]
                    boundary = v.encode('utf-8')
            assert boundary
            #print ("boundary:", boundary)
            self.streaming_parser = StreamingMultipartParser(boundary, trigger=self.parser_has_data_callback)

    @gen.coroutine
    def parser_has_data_callback(self, part):
        disposition = part.headers.get("Content-Disposition", None)
        #print ("trigger", len(part.body.getbuffer()), disposition)
        if disposition and disposition.startswith('form-data'):
            #print ("form data found")
            piece = {}
            piece_str_list = [ piece.strip() for piece in disposition.split(';')[1:] ]
            for piece_str in piece_str_list:
                key, value = piece_str.split("=", 1)
                key = key.strip()
                value = value.strip()
                if value.startswith("'") or value.startswith('"'):
                    value = value[1:-1]
                piece[key.strip()] = value
            #print ("piece map:", piece)
            if 'name' in piece and piece['name'] == 'uploaded-file':
                desired_filename = piece['filename']
                #print ("desired filename:", desired_filename)

                upload_handle = self.upload_handle
                if upload_handle is None:
                    upload_handle = yield self.get_upload_handle(desired_filename)
                #print ("upload handle:", upload_handle)
                body_copy = part.body.getvalue()
                body_chunk = body_copy[:BACKEND_CHUNK_SIZE]
                body_remainder = body_copy[BACKEND_CHUNK_SIZE:]
                # N.B. : a newly-constructed BytesIO will have a write pointer of 0
                #        which will clobber the data you seeded it with on future writes
                part.body = BytesIO(body_remainder)
                part.body.seek(len(body_remainder))
                yield upload_handle.upload_chunk(body_chunk)

    @gen.coroutine
    def get_upload_handle(self, desired_filename='uploaded-file'):
        if self.upload_handle is None:
            # I'm not actually sure that this assertion can hold.
            # In particular, tornado docs mention that it's possible for
            # data_received() to be called any time after prepare() has
            # yielded.  However: if prepare() or data_received() return a
            # future, then that stream will be blocked until it completes.
            # Maybe I need to do the following first, if something goes awry?
            # yield self.db_work_future
            assert self.api_client
            if self.folder_res_future is None:
                upload_date = datetime.datetime.today()
                self.folder_res_future = self.api_client.create_folder("appdata", upload_date.isoformat())
            if self.folder_res is None:
                self.folder_res = yield self.folder_res_future
                #print ("Folder created is:", self.folder_res)
                #print (self)
            if self.file_res_future is None:
                self.file_res_future = self.api_client.create_file(self.folder_res["id"], desired_filename)
            if self.file_res is None:
                self.file_res = yield self.file_res_future
                #print ("File created is:", self.file_res)
                #print (self)
            if self.upload_handle_future is None:
                self.upload_handle_future = self.api_client.start_content_upload(self.file_res["id"])
                #print ("created upload handle for", desired_filename)
                #print (self)
            # we could have yielded, and this could have happened from another
            # coroutine, so check again
            if self.upload_handle is None:
                #print ("awaiting upload_handle_future")
                self.upload_handle = yield self.upload_handle_future
        return self.upload_handle

    @gen.coroutine
    def data_received(self, data):
        assert self.request.method == 'POST'
        assert self.streaming_parser

        # Do something with the data.
        #print ("got data {}".format(len(data)))
        yield self.streaming_parser.got_bytes(data)
