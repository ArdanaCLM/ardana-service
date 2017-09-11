import filelock
from flask import abort
from flask import Blueprint
from flask import jsonify
from flask import request
from flask import send_from_directory
import json
import logging
import os
import signal
import sys
import time

from . import config

LOG = logging.getLogger(__name__)

bp = Blueprint('plays', __name__)

LOGS_DIR = config.get_dir("log_dir")
META_EXT = ".json"

# Functions to deal with "plays".  Every time an ansible playbook is run,
# a play is created to track the progress and output of the run.

# Dictionary of all running plays
plays = {}


@bp.route("/api/v2/plays/<id>/log")
def get_log(id):
    """Returns the log for the given ansible play.

    This works on both live and finished plays.

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
    return send_from_directory(LOGS_DIR, str(id) + ".log")


@bp.route("/api/v2/plays")
def get_plays():
    """Returns the metadata about all ansible plays.

       The list can optionally be limited by specifying the following query
       parameters:
       * maxNumber=<N>
       * maxAge=<seconds>
       * live=true
       * playbook=<name>

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
            for filename in os.listdir(LOGS_DIR):
                if not filename.endswith(META_EXT):
                    continue

                path = os.path.join(LOGS_DIR, filename)
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
def get_play(id):
    """Returns the metadata about the given play

    The metadata will vary depending on whether the process has completed.  If
    the process is still running, the output will not contain ``code``,
    ``logSize``, or ``endTime``.

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
    return send_from_directory(LOGS_DIR, str(id) + META_EXT)


@bp.route("/api/v2/plays/<id>", methods=['DELETE'])
def kill_play(id):
    """Kills the playbook with the given id, if it is still running

    **Example Request**:

    .. sourcecode:: http

       DELETE /api/v2/plays/3587323 HTTP/1.1

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json
    """
    meta_file = get_metadata_file(id)
    lock = filelock.SoftFileLock(get_metadata_lockfile(id))

    try:
        # Writes should be very fast
        with lock.acquire(timeout=3):
            with open(meta_file) as f:
                play = json.load(f)

            os.kill(int(id), signal.SIGINT)
            play['killed'] = True
            with open(meta_file, "w") as f:
                json.dump(play, f)

            return "Success"

    except (IOError, OSError, filelock.Timeout):
        abort(404, "Unable to find process and metadata")


@bp.route("/api/v2/plays/<id>/events")
def get_events(id):
    """Returns the events received for an ansible play.

    This works on both live and finished plays.

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
    return send_from_directory(LOGS_DIR, str(id) + ".events",
                               mimetype="application/json")


def get_metadata_lockfile(id):
    return os.path.join(LOGS_DIR, str(id) + ".lock")


def get_metadata_file(id):
    return os.path.join(LOGS_DIR, str(id) + META_EXT)


def get_running_plays():
    return plays


def basename(playbook):
    # Handle playbooks that are missing or None
    if not playbook:
        return playbook

    return os.path.basename(playbook.rstrip(".yml"))
