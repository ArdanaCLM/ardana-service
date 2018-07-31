# (c) Copyright 2017-2018 SUSE LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# When running the main program, reference to the ardana_service package
# will throw errors unless the current directory is added to the python path
if __name__ == "__main__":
    import sys
    sys.path.append('.')

from ardana_service import admin
from ardana_service import config  # noqa: F401
from ardana_service import config_processor
from ardana_service import encoder
from ardana_service import keystone
from ardana_service import listener
from ardana_service import model
from ardana_service import playbooks
from ardana_service import plays
from ardana_service import servers
from ardana_service import service
from ardana_service import socketio
from ardana_service import templates
from ardana_service import versions

from flask import Flask
from flask import request
from flask_cors import CORS
from keystonemiddleware import auth_token
# Load keystone options into global config object
from keystonemiddleware import opts  # noqa: F401
import os
from oslo_config import cfg
from oslo_log import log as logging
from oslo_middleware import healthcheck
import time

PROGRAM = 'ardana_service'
LOG = logging.getLogger(PROGRAM)
CONF = cfg.CONF
logging.register_options(CONF)

# The default level of INFO for engineio and socketio yields messages
# for every line of every log that is transferred through the socket.
# WARN avoids that.
extra_log_level_defaults = [
    'engineio=WARN',
    'socketio=WARN',
]
logging.set_defaults(default_log_levels=logging.get_default_log_levels() +
                     extra_log_level_defaults)


app = Flask(PROGRAM)
app.register_blueprint(admin.bp)
app.register_blueprint(config_processor.bp)
app.register_blueprint(playbooks.bp)
app.register_blueprint(plays.bp)
app.register_blueprint(keystone.bp)
app.register_blueprint(listener.bp)
app.register_blueprint(model.bp)
app.register_blueprint(servers.bp)
app.register_blueprint(service.bp)
app.register_blueprint(templates.bp)
app.register_blueprint(versions.bp)
# Flask logging is broken, and it is a time bomb: by default it does nothing,
# but the first time an exception happens, it creates a new logger that
# interferes with normal python logging, which messes up all subsequent log
# messages.  This bug was reported in
# https://github.com/pallets/flask/issues/641 and is expected to be fixed in
# the future when Flask 1.0 ships.  Referring to app.logger forces this
# creation via Flask's logger property handler.  We then clean up the mess it
# makes
app.logger                   # initialize flask logging (screwing up logging)
app.logger.handlers = []     # clear out the newly creating logger
app.logger.propagate = True  # let messages be handled by normal logging

app.json_encoder = encoder.CustomJSONEncoder   # use our custom json encoder


@app.before_request
def log_request():
    LOG.info(' '.join([
        request.remote_addr,
        '   ',
        request.method,
        request.url,
    ]))


@app.after_request
def log_response(response):
    LOG.info(' '.join([
        request.remote_addr,
        str(response.status_code),
        request.method,
        request.url,
    ]))
    return response


# Middleware function to permit unsecured functions to be called even
# when keystone authentication is being enforced
def enable_unsecured(handler):
    def _inner(environ, start_fn):
        unsecured = ['/api/v2/heartbeat',
                     '/api/v2/version',
                     '/api/v2/listener/playbook',  # For posts from playbooks
                     '/api/v2/is_secured',
                     '/api/v2/login']
        path = environ.get('PATH_INFO')

        if environ.get('HTTP_X_IDENTITY_STATUS') != 'Confirmed' and \
                path not in unsecured:

            LOG.info("Rejecting unauthorized call to %s", path)

            # Set response headers to signal to the keystone middleware that
            # this REST api must be authorized.  See
            # https://wiki.openstack.org/wiki/Openstack-authn
            start_fn('401 Unauthorized', [('WWW-Authenticate', 'Delegated')])
        else:
            return handler(environ, start_fn)
    return _inner


def main():

    # Load config options any config files specified on the command line
    CONF()
    logging.setup(CONF, PROGRAM)
    CORS(app)

    if config.requires_auth():
        # Wrap with keystone middleware if configured to do so
        if not CONF.keystone_authtoken.delay_auth_decision:
            msg = "The [keystone_authtoken] section in the config file " \
                "must have delay_auth_decision explicitly set to true. " \
                "The default value, false, will cause calls to " \
                "/api/v2/heartbeat to be rejected "
            LOG.error(msg)
            print(msg)  # print on the console for good measure
            sys.exit(1)

        # Use our our middleware function to permit unsecured apis to be called
        app.wsgi_app = enable_unsecured(app.wsgi_app)
        app.wsgi_app = auth_token.AuthProtocol(app.wsgi_app,
                                               {'oslo_config_config': CONF})

    # Use oslo healthcheck, which does not log its requests
    app.wsgi_app = healthcheck.Healthcheck(app.wsgi_app)

    # Note that any flask options that are to be exposed in our config file
    # have to be explicitly configured (in flask_opts above) and explicitly
    # placed into the following dict
    flask_config = {
        "JSONIFY_PRETTYPRINT_REGULAR": CONF.pretty_json
    }
    app.config.from_mapping(flask_config)

    trigger_file = os.path.join(CONF.paths.log_dir, 'trigger.txt')
    if not os.path.exists(trigger_file):
        with open(trigger_file, 'w') as f:
            f.write("Started at %s\n" % time.asctime())

    socketio.init_app(app)

    # The 'log' parameter avoids running in debug mode, which suppresses the
    # debug message that is emitted on *every* incoming request.
    socketio.run(app, host=CONF.host, port=CONF.port, use_reloader=True,
                 log=LOG,
                 extra_files=[trigger_file])


if __name__ == "__main__":
    main()
