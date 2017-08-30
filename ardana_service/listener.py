from flask import Blueprint
from flask import jsonify
from flask import request
import logging

from . import socketio

LOG = logging.getLogger(__name__)

bp = Blueprint('listener', __name__)

connection_timeout = 86400  # 24 hours

connections = {}


@bp.route("/api/v2/listener/playbook/<event>/<path:name>", methods=['POST'])
def playbook_event(event, name):
    """Event listener for playbook events

    Will propagate the start event to listeners that are registered
    """
    opts = request.get_json() or {}
    if 'id' in opts:
        id = str(opts['id'])
        socketio.emit("playbook-" + event, name, room=id)
        return jsonify(id)
    else:
        return ('', 201)
