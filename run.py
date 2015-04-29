#!env/bin/python

import sys
from aeroup import create_app, create_tornado_app, migrate_database

from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop

def usage():
    print ("Usage: {} <debug|prod>".format(sys.argv[0]))
    sys.exit(1)

def run(debug):
    app = create_app()
    if debug:
        app.debug = True
    migrate_database(app)

    application = create_tornado_app(app)
    # Limit incoming per-connection memory buffer to 256kB.  This limit may need to be adjusted.
    buffer_limit = 256 * 1024
    http_server = HTTPServer(application, xheaders=True, max_buffer_size=buffer_limit)

    hostname = '127.0.0.1'
    port = 5000
    http_server.listen(port, address=hostname)
    print ("Listening on {}:{}".format(hostname, port))
    IOLoop.instance().start()

def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ['debug', 'prod']: usage()
    run(debug= True if sys.argv[1] == 'debug' else False)

if __name__ == '__main__':
    main()
