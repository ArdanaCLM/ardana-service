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

from flask import abort
from flask import Blueprint
from flask import jsonify
from flask import request
import json
import os
from oslo_log import log as logging
import time

from . import policy
from . import socketio
from .playbooks import get_events_file

LOG = logging.getLogger(__name__)

bp = Blueprint('listener', __name__)


@bp.route("/api/v2/listener/playbook", methods=['POST'])
@policy.enforce('lifecycle:playbook_listener')
def playbook_event():
    """Event listener for playbook events

    Propagate events to socketio listeners

    .. :quickref: Playbook; Send event to playbook listener
    """
    opts = request.get_json() or {}
    if 'play_id' in opts:
        id = str(opts['play_id'])
        event = opts['event']
        name = opts['playbook']

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
