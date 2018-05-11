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
from flask import send_from_directory
import json
import os
from oslo_config import cfg
from oslo_log import log as logging
import signal
import sys
import time

from . import policy

LOG = logging.getLogger(__name__)
bp = Blueprint('plays', __name__)
CONF = cfg.CONF

META_EXT = ".json"

# Functions to deal with "plays".  Every time an ansible playbook is run,
# a play is created to track the progress and output of the run.

# Dictionary of all running plays
plays = {}


@bp.route("/api/v2/plays/<id>/log")
@policy.enforce('lifecycle:get_play')
def get_log(id):
    """Returns the log for the given ansible play.

    This works on both live and finished plays.

    .. :quickref: Play; Returns the log for the given ansible play

    :param id: play id

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/plays/345835/log HTTP/1.1

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       ... log file from the given play ...
    """
    # For security, send_from_directory avoids sending any files
    # outside of the specified directory
    return send_from_directory(get_log_dir_abs(), str(id) + ".log")


@bp.route("/api/v2/plays")
@policy.enforce('lifecycle:get_play')
def get_plays():
    """Returns the metadata about all ansible plays.

    The list can optionally be limited by specifying query parameters.

    :query int maxNumber: Maximum number of plays to return
    :query int maxAge: Maximum age in seconds
    :query boolean live: Whether to restrict results to running plays
    :query string playbook: Playbook name

    .. :quickref: Play; Returns the metadata about all ansible plays

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/plays HTTP/1.1

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json

       [
         {
           "code": 254,
           "commandString": "validate input model",
           "endTime": 1502161466109,
           "killed": false,
           "logSize": 2735,
           "id": 1502161460385,
           "pid": 18697,
           "startTime": 1502161460385
         },
         {
           "code": 2,
           "commandString":
               "ansible-playbook -i hosts/localhost config-processor-run.yml",
           "endTime": 1501782351315,
           "killed": false,
           "logSize": 1905,
           "id": 1501782349242,
           "startTime": 1501782349242
         }
       ]
    """
    max_number = int(request.args.get("maxNumber", sys.maxsize))
    max_age = int(request.args.get("maxAge", sys.maxsize))
    live_only = request.args.get("live") == "true"
    want_playbook = request.args.get("playbook")

    if want_playbook:
        want_playbook = basename(want_playbook)

    earliest_end_time = int(time.time()) - max_age

    results = []
    meta_files = []
    try:
        if live_only:
            for id, play in get_running_plays().iteritems():
                if not want_playbook or \
                        basename(play['playbook']) == want_playbook:
                    meta_files.append(get_metadata_file(id))

        else:
            for filename in os.listdir(CONF.paths.log_dir):
                if not filename.endswith(META_EXT):
                    continue

                path = os.path.join(CONF.paths.log_dir, filename)
                meta_files.append(path)

        for path in meta_files:

            with open(path) as f:
                play = json.load(f)

            end_time = play.get('endTime')

            if live_only and end_time:
                continue

            if end_time and end_time < earliest_end_time:
                continue

            if want_playbook and \
                    want_playbook != basename(play.get('playbook')):
                continue

            results.append(play)

            if len(results) >= max_number:
                break
    except IOError:
        pass

    return jsonify(results)


@bp.route("/api/v2/plays/<id>")
@policy.enforce('lifecycle:get_play')
def get_play(id):
    """Returns the metadata about the given play

    The metadata will vary depending on whether the process has completed.  If
    the process is still running, the output will not contain ``code``,
    ``logSize``, or ``endTime``.

    .. :quickref: Play; Returns the metadata about the given play

    :param id: play id

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/plays/3587323 HTTP/1.1

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json

       {
         "code": 254,
         "commandString": "validate input model",
         "endTime": 1502161466109,
         "killed": false,
         "logSize": 2736,
         "id": 3587323,
         "startTime": 1502161460385
       }
    """
    return send_from_directory(get_log_dir_abs(), str(id) + META_EXT)


def is_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@bp.route("/api/v2/plays/<id>", methods=['DELETE'])
@policy.enforce('lifecycle:run_playbook')
def kill_play(id):
    """Kills the play with the given id if it is still running

    .. :quickref: Play; Kills the given play

    :param id: play id

    **Example Request**:

    .. sourcecode:: http

       DELETE /api/v2/plays/3587323 HTTP/1.1

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json
    """
    meta_file = get_metadata_file(id)

    try:
        with open(meta_file) as f:
            play = json.load(f)

    except IOError:
        abort(404, "Unable to find play")

    # play['pid'] is always an int, but cast it just to be safe
    pid = int(play['pid'])
    if not is_running(pid):
        abort(410, 'Process is no longer running')

    try:
        tries = 5
        # Use SIGINT to give the process a chance to shut itself down
        while(is_running(pid) and tries > 0):
            os.kill(pid, signal.SIGINT)
            tries -= 1
            time.sleep(0.5)

        # It refuses to shut down, so use the big hammer (SIGKILL)
        if is_running(pid):
            os.kill(pid, signal.SIGKILL)

            tries = 5
            # Wait a little for the process to die
            while(is_running(pid) and tries > 0):
                tries -= 1
                time.sleep(0.5)

    except OSError as e:
        abort(404, "Unable to kill process %s" % e.message)

    play['killed'] = True

    # If the process has finally died, update the endTime
    if not is_running(pid):
        play['endTime'] = int(1000 * time.time())

    with open(meta_file, "w") as f:
        json.dump(play, f)

    return "Success"


@bp.route("/api/v2/plays/<id>/events")
@policy.enforce('lifecycle:get_play')
def get_events(id):
    """Returns the events received for an ansible play.

    Returns all events that have been received for a play.  This works on both
    live and finished plays.

    .. :quickref: Play; Returns the events received for an ansible play

    :param id: play id

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/plays/345835/log HTTP/1.1

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json

       [
         {
           "event": "playbook-start",
           "playbook": "site.yml",
           "timestamp": 1505151952
         },
         {
           "event": "playbook-stop",
           "playbook": "site.yml",
           "timestamp": 1505151986
         }
       ]
    """
    # For security, send_from_directory avoids sending any files
    # outside of the specified directory
    return send_from_directory(get_log_dir_abs(), str(id) + ".events",
                               mimetype="application/json")


def get_metadata_file(id):
    return os.path.join(CONF.paths.log_dir, str(id) + META_EXT)


def get_running_plays():
    return plays


def basename(playbook):
    # Handle playbooks that are missing or None
    if not playbook:
        return playbook

    return os.path.basename(playbook.rstrip(".yml"))


def get_log_dir_abs():
    """Get log_dir absolute path

    When flask serves log files directly with send_from_directory(), it expects
    relative pathnames to be relative to where the main.py resides, but
    relative pathnames in the config files are considered to be relative
    to the cwd of when flask was launched.  Return the absolute path of the
    log directory.

    Note that production config files specify absolute paths, so this
    function only modifies paths in development environments (where relative
    pathnames are used in config files)
    """
    log_dir = CONF.paths.log_dir
    if os.path.isabs(log_dir):
        return log_dir

    return os.path.normpath(os.path.join(os.getcwd(), CONF.paths.log_dir))
