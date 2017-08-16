from ardana_service import admin
from ardana_service import config
from ardana_service import config_processor
from ardana_service import cp_output
from ardana_service import model
from ardana_service import osinstall
from ardana_service import playbooks
from ardana_service import plays
from ardana_service import socketio
from ardana_service import tasks
from ardana_service import templates
from ardana_service import versions
import datetime
from flask import Flask
from flask import request
from flask_cors import CORS
import logging
logging.basicConfig(level=logging.DEBUG)

LOG = logging.getLogger('ardana_service')
app = Flask('ardana_service')
app.register_blueprint(admin.bp)
app.register_blueprint(config_processor.bp)
app.register_blueprint(cp_output.bp)
app.register_blueprint(playbooks.bp)
app.register_blueprint(plays.bp)
app.register_blueprint(tasks.bp)
app.register_blueprint(model.bp)
app.register_blueprint(osinstall.bp)
app.register_blueprint(templates.bp)
app.register_blueprint(versions.bp)
CORS(app)


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

    flask_config = config.get_flask_config()
    port = flask_config.pop('port', 9085)

    app.config.from_mapping(config.get_flask_config())

    # app.run(debug=True)
    socketio.init_app(app)
    socketio.run(app, port=port, use_reloader=True)
