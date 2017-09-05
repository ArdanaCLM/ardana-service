from flask import abort
from flask import Blueprint
from flask import jsonify
from flask import request
import json
import logging
import os
import time

from . import config
from . import socketio
from .playbooks import get_events_file

LOG = logging.getLogger(__name__)

bp = Blueprint('listener', __name__)

LOGS_DIR = config.get_dir("log_dir")


@bp.route("/api/v2/listener/playbook/<event>/<path:name>", methods=['POST'])
def playbook_event(event, name):
    """Event listener for playbook events

    Propagate events to socketio listeners
    """
    opts = request.get_json() or {}
    if 'id' in opts:
        id = str(opts['id'])

        playbook_event = "playbook-" + event
        socketio.emit(playbook_event, name, room=id)

        # Record event to file so that it can be replayed back to any client
        # that joins while the playbook is already underway
        events_file = get_events_file(id)
        try:
            if os.path.exists(events_file):
                with open(events_file) as f:
                    events = json.load(f)
            else:
                events = []

            events.append({'event': playbook_event,
                           'playbook': name,
                           'timestamp': int(time.time())})

            with open(events_file, "w") as f:
                json.dump(events, f)

            return jsonify(id)

        except IOError as e:
            LOG.exception(e)
            abort(500, "Unable to write event")

    else:
        return ('', 201)
