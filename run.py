#!/usr/bin/env python
import sys

from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop

import aeroup


HOSTNAME = '127.0.0.1'
PORT = 5000
BUFFER_LIMIT = 1024 * 1024 *1024 * 4  # 4GB


def run(debug=True):
    app = aeroup.create_app(debug)

    application = aeroup.create_tornado_app(app)
    http_server = HTTPServer(application, xheaders=True,
                             max_buffer_size=BUFFER_LIMIT)

    print 'Listening on {}:{}'.format(HOSTNAME, PORT)
    http_server.listen(PORT, address=HOSTNAME)

    IOLoop.instance().start()


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('debug', 'prod'):
        print 'Usage: {} <debug|prod>'.format(sys.argv[0])
        sys.exit(1)

    run(debug=(sys.argv[1] == 'debug'))


if __name__ == '__main__':
    main()
