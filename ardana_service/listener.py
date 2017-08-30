from flask import Blueprint
from flask import jsonify
from flask import request
from flask_socketio import emit
from flask_socketio import join_room
import logging
import time

from . import config
from . import socketio

from socketIO_client import SocketIO

LOG = logging.getLogger(__name__)

bp = Blueprint('listener', __name__)

connection_timeout = 86400  # 24 hours

connections = {}


@bp.route("/api/v2/listener/playbook/start/<path:name>",
          methods=['POST', 'GET'])
def playbook_has_started(name):
    """Event listener for playbook starts

    Will propagate the start event to listeners that are registered
    """
    opts = request.get_json() or {}
    connection_expiry_check()
    for connection in connections.values():
        connection.get('socket').emit('playbookstatus', 'playbook-start', name)

    return jsonify(opts)


@bp.route("/api/v2/listener/playbook/stop/<path:name>",
          methods=['POST', 'GET'])
def playbook_has_stopped(name):
    """Event listener for playbook stops

    Will propagate the stop event to listeners that are registered
    """
    opts = request.get_json() or {}
    connection_expiry_check()
    for connection in connections.values():
        connection.get('socket').emit('playbookstatus', 'playbook-stop', name)

    return jsonify(opts)


@bp.route("/api/v2/listener/playbook/error/<path:name>",
          methods=['POST', 'GET'])
def playbook_has_error(name):
    """Event listener for playbook errors

    Will propagate the error event to listeners that are registered
    """
    opts = request.get_json() or {}
    connection_expiry_check()
    for connection in connections.values():
        connection.get('socket').emit('playbookstatus', 'playbook-error', name)

    return jsonify(opts)


def connection_expiry_check():
    # to avoid endlessly adding to the connections list, expire any that are
    # older than the timeout intervale
    for connection_id, connection in connections.items():
        if(connection.get('connect_time') + connection_timeout < time.time()):
            connection.get('socket').disconnect()
            del connections[connection_id]


@bp.route("/api/v2/listener/addconnection/<id>/<room>/<host>/<port>",
          methods=['POST', 'GET'])
def add_listener_connection(id, room, host, port):
    connect_time = time.time()
    connections[id] = {'socket': SocketIO('http://' + host, port),
                       'connect_time': connect_time}
    connections[id].get('socket').emit('ardanasocketjoin', room)
    opts = request.get_json() or {}
    return jsonify(opts)
