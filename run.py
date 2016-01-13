#!/usr/bin/env python
import sys

from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop

import aeroup


def run(debug=True):
    app = aeroup.create_app()
    app.debug = debug

    aeroup.migrate_database(app)

    application = aeroup.create_tornado_app(app)
    # Limit incoming per-connection memory buffer to 256kB.  This limit may
    # need to be adjusted.
    buffer_limit = 256 * 1024
    http_server = HTTPServer(application, xheaders=True,
                             max_buffer_size=buffer_limit)

    hostname = '127.0.0.1'
    port = 5000
    print 'Listening on {}:{}'.format(hostname, port)
    http_server.listen(port, address=hostname)

    IOLoop.instance().start()


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('debug', 'prod'):
        print 'Usage: {} <debug|prod>'.format(sys.argv[0])
        sys.exit(1)

    run(debug=(sys.argv[1] == 'debug'))


if __name__ == '__main__':
    main()
