from flask import Blueprint
from flask import jsonify
from flask import request
from flask_socketio import emit
from flask_socketio import join_room
import logging

from . import config
from . import socketio

LOG = logging.getLogger(__name__)

bp = Blueprint('listener', __name__)

room = 'ardanastatus'

@bp.route("/api/v2/listener/playbook/start/<path:name>",
          methods=['POST', 'GET'])
def playbook_has_started(name):
    """Event listener for playbook starts

    Will propagate the start event to listeners that are registered
    """
    opts = request.get_json() or {}
    socketio.emit('playbook-start', name, room=room)

    return jsonify(opts)


@bp.route("/api/v2/listener/playbook/stop/<path:name>",
          methods=['POST', 'GET'])
def playbook_has_stopped(name):
    """Event listener for playbook stops

    Will propagate the stop event to listeners that are registered
    """
    opts = request.get_json() or {}
    socketio.emit('playbook-stop', name, room=room)

    return jsonify(opts)


@socketio.on('ardanastatusroom')
def on_room():
    join_room(room)
