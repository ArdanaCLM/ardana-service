from ardana_service import config  # noqa: F401
from ardana_service import admin
from ardana_service import config_processor
from ardana_service import listener
from ardana_service import model
from ardana_service import osinstall
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
from oslo_config import cfg
import logging
logging.basicConfig(level=logging.DEBUG)

LOG = logging.getLogger('ardana_service')
app = Flask('ardana_service')
app.register_blueprint(admin.bp)
app.register_blueprint(config_processor.bp)
app.register_blueprint(playbooks.bp)
app.register_blueprint(plays.bp)
app.register_blueprint(listener.bp)
app.register_blueprint(model.bp)
app.register_blueprint(osinstall.bp)
app.register_blueprint(service.bp)
app.register_blueprint(templates.bp)
app.register_blueprint(versions.bp)
CORS(app)


CONF = cfg.CONF
# Load config options any config files specified on the command line
CONF()


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
    # Note that any flask options that are to be exposed in our config file
    # have to be explicitly configured (in flask_opts above) and explicitly
    # placed into the following dict
    flask_config = {
        "JSONIFY_PRETTYPRINT_REGULAR": CONF.pretty_json
    }
    app.config.from_mapping(flask_config)

    socketio.init_app(app)
    socketio.run(app, host=CONF.host, port=CONF.port, use_reloader=True)
