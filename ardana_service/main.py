from ardana_service import admin
from ardana_service import config  # noqa: F401
from ardana_service import config_processor
from ardana_service import listener
from ardana_service import model
from ardana_service import playbooks
from ardana_service import plays
from ardana_service import service
from ardana_service import socketio
from ardana_service import templates
from ardana_service import versions

import datetime
from flask import Flask
from flask import request
from flask_cors import CORS
from keystonemiddleware import auth_token
# Load keystone options into global config object
from keystonemiddleware import opts  # noqa: F401
import os
from oslo_config import cfg
from oslo_log import log as logging
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

app = Flask('ardana_service')
app.register_blueprint(admin.bp)
app.register_blueprint(config_processor.bp)
app.register_blueprint(playbooks.bp)
app.register_blueprint(plays.bp)
app.register_blueprint(listener.bp)
app.register_blueprint(model.bp)
app.register_blueprint(service.bp)
app.register_blueprint(templates.bp)
app.register_blueprint(versions.bp)


@app.before_request
def log_request():
    LOG.info(' '.join([
        datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S.%f'),
        request.remote_addr,
        '   ',
        request.method,
        request.url,
    ]))


@app.after_request
def log_response(response):
    LOG.info(' '.join([
        datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S.%f'),
        request.remote_addr,
        str(response.status_code),
        request.method,
        request.url,
    ]))
    return response


if __name__ == "__main__":

    # Load config options any config files specified on the command line
    CONF()
    logging.setup(CONF, PROGRAM)
    CORS(app)

    if 'keystone_authtoken' in CONF.list_all_sections():
        # Wrap with keystone middleware if configured to do so
        app.wsgi_app = auth_token.AuthProtocol(app.wsgi_app,
                                               {'oslo_config_config': CONF})

    # Note that any flask options that are to be exposed in our config file
    # have to be explicitly configured (in flask_opts above) and explicitly
    # placed into the following dict
    flask_config = {
        "JSONIFY_PRETTYPRINT_REGULAR": CONF.pretty_json
    }
    app.config.from_mapping(flask_config)

    trigger_file = os.path.join(CONF.paths.log_dir, 'trigger.txt')
    with open(trigger_file, 'w') as f:
        f.write("Started at %s\n" % time.asctime())

    socketio.init_app(app)
    socketio.run(app, host=CONF.host, port=CONF.port, use_reloader=True,
                 extra_files=[trigger_file])
