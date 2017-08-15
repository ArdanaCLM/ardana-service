from flask import abort
from flask import Blueprint
from flask import jsonify
from flask import request
from flask import send_from_directory
from flask import url_for
from flask_socketio import emit
from flask_socketio import join_room
import filelock
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time

from . import config
from . import socketio

LOG = logging.getLogger(__name__)

bp = Blueprint('playbooks', __name__)

PLAYBOOKS_DIR = config.get_dir("playbooks_dir")
LOGS_DIR = config.get_dir("log_dir")
METADATA = os.path.join(LOGS_DIR, "plays.yml")
LOCKFILE = os.path.join(LOGS_DIR, "plays.yml.lock")

# Dictionary of all running tasks
tasks = {}


@bp.route("/api/v2/playbooks")
def playbooks():

    playbooks = {'config-processor-run',
                 'config-processor-clean',
                 'ready-deployment'}

    try:
        for filename in os.listdir(PLAYBOOKS_DIR):
            if filename[0] != '_' and filename.endswith('.yml'):
                # Strip off extension
                playbooks.add(filename[:-4])
    except OSError:
        LOG.warning("Playbooks directory %s doesn't exist. This could indicate"
                    " that the ready_deployment playbook hasn't been run yet. "
                    "The list of playbooks available will be reduced",
                    PLAYBOOKS_DIR)

    return jsonify(sorted(playbooks))


def get_extra_vars(opts):

    # In the JSON request payload, the special key extraVars wil be converted
    # to the --extra-vars playbook argument, and it undergoes special
    # processing.  The supplied value will either be an array of key value
    # pairs, e.g.  ["key1=val1", "key2=val2"], or a nested object, e.g.,
    # { "key1": "val1", "key2": "val2" }
    if type(opts.get("extraVars")) is list:
        d = {}
        for keyval in opts["extraVars"]:
            try:
                (key, val) = keyval.split("=", 1)
                d[key] = val
            except ValueError:
                pass
        return d
    else:
        return opts.get("extraVars", {})


def run_site(opts, client_id):

    # Normalize the extraVars entry
    opts['extraVars'] = get_extra_vars(opts)

    # Extract relevant options
    # keep_dayzero = opts['extraVars'].pop('keep_dayzero', None)
    # destroy_on_success = opts.pop('destroyDayZeroOnSuccess', None)

    # TODO(gary): Handle things like reading passwords from an encrypted vault
    # TODO(gary): if successful and destory_on_success, then invoke
    # dayzero-stop playbook


def run_config_processor_clean(opts, client_id):
    pass


def run_config_processor(opts, client_id):
    pass


def run_ready_deployment(opts, client_id):
    pass


@bp.route("/api/v2/playbooks/<name>", methods=['POST'])
def run_playbook(name):
    """Run an ansible playbook

    JSON payload is an object that may contain key/value pairs that will be
    passed as command-line arguments to the ansible playbook.

    If the http header "clientid" is supplied, it will be passed as
    a command-line argument named ClientId.
    """
    opts = request.get_json() or {}

    client_id = request.headers.get('clientid')   # TODO(gary) Remove "hlm"

    if name == "site":
        return run_site(opts, client_id)
    elif name == "config-processor-run":
        return run_config_processor(opts, client_id)
    elif name == "config-processor-clean":
        return run_config_processor_clean(opts, client_id)
    elif name == "ready-deployment":
        return run_ready_deployment(opts, client_id)
    elif name == "blather":
        temp_name = os.path.join(os.curdir, 'blather')
        return spawn_process(temp_name)
    else:
        try:
            name += ".yml"
            for filename in os.listdir(PLAYBOOKS_DIR):
                if filename == name:
                    break
            else:
                abort(404)

            playbook_name = os.path.join(PLAYBOOKS_DIR, name)
            return spawn_process('ansible-playbook', [playbook_name])

        except OSError:
            LOG.warning("Playbooks directory %s doesn't exist. This could "
                        "indicate that the ready_deployment playbook hasn't "
                        "been run yet. The list of playbooks available will "
                        "be reduced", PLAYBOOKS_DIR)

    return jsonify(opts)


@bp.route("/api/v2/plays/<id>/log")
def get_log(id):
    """Returns the log for the given ansible plays.

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/plays/345835/log HTTP/1.1

    **Example Reponse**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       ... log file from the given play ...
    """
    # For security, send_from_directory avoids sending any files
    # outside of the specified directory
    return send_from_directory(LOGS_DIR, id + ".log")


@bp.route("/api/v2/plays")
def get_plays():
    """Returns the metadata about all ansible plays.

       The results can be limited with query parameters:
       * maxNumber=<N>
       * maxAge=<seconds>
       * live=true

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/plays HTTP/1.1

    **Example Reponse**:

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
           "id": 18697,
           "startTime": 1502161460385
         },
         {
           "code": 2,
           "commandString":
               "ansible-playbook -i hosts/localhost config-processor-run.yml",
           "endTime": 1501782351315,
           "killed": false,
           "logSize": 1905,
           "id": 23795,
           "startTime": 1501782349242
         }
       ]
    """
    max_number = int(request.args.get("maxNumber", sys.maxsize))
    max_age = int(request.args.get("maxAge", sys.maxsize))
    live_only = request.args.get("live") == "true"

    earliest_end_time = int(time.time()) - max_age

    results = []
    try:
        with open(METADATA) as f:
            plays = json.load(f)

        for play in plays:
            end_time = play.get('endTime')

            if live_only and end_time:
                continue

            if end_time and end_time < earliest_end_time:
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

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/plays/3587323 HTTP/1.1

    **Example Reponse**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json

       {
         "code": 254,
         "commandString": "validate input model",
         "endTime": 1502161466109,
         "killed": false,
         "logSize": 2735,
         "id": 3587323,
         "startTime": 1502161460385
       }
    """
    req_id = int(id)
    try:
        with open(METADATA) as f:
            plays = json.load(f)

        matches = [p for p in plays if p['id'] == req_id]
        if matches:
            return jsonify(matches[0])
    except IOError:
        pass

    abort(404)


@bp.route("/api/v2/plays/<id>", methods=['DELETE'])
def kill_play(id):
    """Kills the playbook with the given id, if it is still running

    **Example Request**:

    .. sourcecode:: http

       DELETE /api/v2/plays/3587323 HTTP/1.1

    **Example Reponse**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json
    """
    req_id = int(id)
    lock = filelock.FileLock(LOCKFILE)
    # Timeout after at most a brief wait.  Writes should be very fast

    try:
        with lock.acquire(timeout=3):
            with open(METADATA) as f:
                plays = json.load(f)

            for p in plays:
                if p['id'] == req_id:
                    os.kill(req_id, signal.SIGINT)
                    p['killed'] = True
                    with open(METADATA, "w") as f:
                        json.dump(plays, f)
                    return "Success"

    except (IOError, OSError, filelock.Timeout):
        pass

    abort(404)


def get_log_file(id):
    return os.path.join(LOGS_DIR, id + ".log")


def process_output(ps, id):

    with open(get_log_file(id), 'w') as f:
        with ps.stdout:
            # Can use this in python3: for line in ps.stdout:
            # Using iter() per https://stackoverflow.com/a/17698359/190597
            for line in iter(ps.stdout.readline, b''):
                # python 2 returns bytes that must be converted to a string
                if isinstance(line, bytes):
                    line = line.decode("utf-8")

                f.write(line)
                f.flush()
                msg = id + " " + line
                socketio.emit("log", msg, room=id)

    socketio.close_room(id)
    ps.wait()

    # TODO(gary): Need to read from stdout AND stderr
    # TODO(gary): write final state to status file


def spawn_process(command, args=[], cwd=None, opts={}):

    # The code explicitly create processes with the subprocess module rather
    # than using a more advanced mechanism like Celery
    # (http://www.celeryproject.org/) in order to avoid introducing run-time
    # requirements on external systems (like REDIS, rabbitmq, etc.), since
    # this program will be used in an installation scenario where those sytems
    # are not yet running.

    # TODO(gary): Add logic to avoid spawning duplicate playbooks when
    # indicated, by looking at all running playbooks for one with the same
    # command line

    cmdArgs = [command]
    if args:
        cmdArgs.extend(args)

    try:
        ps = subprocess.Popen(cmdArgs, cwd=cwd, env=opts.get('env', None),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        pass

    start_time = int(1000 * time.time())

    id = "%d_%d" % (start_time, ps.pid)

    # Use a thread to read the pipe to avoid blocking this process.  Since
    # the thread will interact with socketio, we have to use that library's
    # function for creating threads

    # Use a thread to read the pipe to avoid blocking this process
    use_threading = False
    if use_threading:
        tasks[id] = {'task': threading.Thread(target=process_output,
                                              args=(ps, id)),
                     'start_time': start_time}
        tasks[id]['task'].start()
    else:
        tasks[id] = {'task': socketio.start_background_task(process_output,
                                                            ps, id),
                     'start_time': start_time}

    LOG.debug("Spwaned thread with task %s", id)

    return '', 202, {'Location': url_for('tasks.get_task', id=id)}


@socketio.on('connect')
def on_connect():
    LOG.info("Connecting")


@socketio.on('disconnect')
def on_disconnect():
    LOG.info("Disconnecting")


@socketio.on('join')  # , namespace='/log')
def on_join(id):

    logfile = get_log_file(id)

    # replay existing log as messages before joining the room
    with open(logfile) as f:
        LOG.info("Replaying %s", logfile)
        for line in f:
            msg = id + " " + line + "from file"
            emit("log", msg)

    # If it is critical not to miss any messages, then thread synchronizcation
    # needs to be introduced so that if any thread is in this function, the
    # pipe reader will pause.  That comes at a cost in code complexity and
    # performance

    LOG.info("Joining room %s", id)

    join_room(id)
