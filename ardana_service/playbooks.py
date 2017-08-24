import filelock
from flask import abort
from flask import Blueprint
from flask import jsonify
from flask import request
from flask import url_for
from flask_socketio import emit
from flask_socketio import join_room
import functools
import json
import logging
import os
import subprocess
import tempfile
import time

from . import config
from . import socketio
from .plays import get_metadata_file
from .plays import get_metadata_lockfile

LOG = logging.getLogger(__name__)

bp = Blueprint('playbooks', __name__)

PLAYBOOKS_DIR = config.get_dir("playbooks_dir")
PRE_PLAYBOOKS_DIR = config.get_dir("pre_playbooks_dir")
LOGS_DIR = config.get_dir("log_dir")

# Quiet down the socketIO library, which is far too chatty
logging.getLogger('socketio').setLevel(logging.WARNING)
logging.getLogger('engineio').setLevel(logging.WARNING)
logging.getLogger('filelock').setLevel(logging.WARNING)

# Dictionary of all running tasks
tasks = {}

# These playbooks are run from a directory that exists even before
# the ready-deployment has been done (PRE_PLAYBOOKS_DIR)
STATIC_PLAYBOOKS = {
    'config-processor-run',
    'config-processor-clean',
    'ready-deployment'}

# TODO(gary) Consider creating a function to archive old plays (create a tgz
#    of log and metadata).  This feature is not mentioned anywhere, but the
#    old version did something similar to this


@bp.route("/api/v2/playbooks")
def playbooks():
    """List available playbooks

    Lists the playbook names (without the trailing ``.yml`` extension) of the
    playbooks that are available to run.

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/playbooks HTTP/1.1
       Content-Type: application/json

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       [
          "ansible-init",
          "check-apt-configuration",
          "...",
          "venv-edit"
       ]

    **Changed for v2**:

    No mapping between '_' and '-' will take place; the playbook names
    returned match the names that are stored on disk.
    """

    playbooks = set(STATIC_PLAYBOOKS)
    try:
        for filename in os.listdir(PLAYBOOKS_DIR):
            if filename[0] != '_' and filename.endswith('.yml'):
                # Strip off extension
                playbooks.add(filename[:-4])
    except OSError as e:
        LOG.exception(e)
        LOG.warning("Playbooks directory %s doesn't exist. This could indicate"
                    " that the ready_deployment playbook hasn't been run yet. "
                    "The list of playbooks available will be reduced",
                    PLAYBOOKS_DIR)

    return jsonify(sorted(playbooks))


@bp.route("/api/v2/playbooks/<name>", methods=['POST'])
def run_playbook(name):
    """Run an ansible playbook

    JSON payload is an object that may contain key/value pairs that will be
    passed as command-line arguments to ``ansible playbook``.
    To simplify things a bit for the caller, the key may omit the leading
    dashes. For example::

       { 'limit' : 100 }

    will be converted to the command arguments ``--limit 100``

    **Example Request**:

    .. sourcecode:: http

       POST /api/v2/playbooks/show-hooks HTTP/1.1
       Content-Type: application/json

       {
          "limit": 100
       }

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 202 ACCEPTED
       Content-Type: application/json
       Location: http://localhost:9085/api/v2/plays/6858

       {
           "id": 6858
       }

    When running the ``config-processor-run`` playbook, no body is required
    unless you desire encryption.  If you want to enable encryption, pass the
    encryption and re-encryption keys in the extra-vars portion of the body:

    .. sourcecode:: http

       POST /api/v2/playbooks/config-processor-run HTTP/1.1
       Content-Type: application/json

       {
           "extra-vars": {
               "encrypt": "admin123456!",
               "rekey": ""
           }
       }

    If it is the first time you use encryption, you only need to set the
    ``encrypt`` value and leave ``rekey`` empty.  This will encrypt all ansible
    host and group variables on disk using Ansible vault.  Once an encrypted
    config processor output has been readied (by running the
    ``ready-deployment`` playbook) you can change the encryption key by
    specifying ``encrypt`` as your old key and ``rekey`` as the new key.
    Once encryption has been enabled, all other playbooks (e.g. ``status``,
    ``site``, etc.) will need to be tol the encryption key:

    .. sourcecode:: http

       POST /api/v2/playbooks/site HTTP/1.1
       Content-Type: application/json

       {
           "encryption-key": "admin123456!",
       }

    **Changes for v2**:

    * No mapping between '_' and '-' will take place in playbook names; the
      playbook names specified must match the name that is stored on disk.
    * The `clientid` header field is no longer supported
    * In the past, the server converted a few special arguments like
      remove_deleted_servers, free_unused_addresses, encrypt, and rekey
      into extra-vars arguments.  Clients are now required to specify these
      as part of extra-vars directly
    * A successful POST will return a json structure containing the ``id`` of
      the play, which can be used by the caller to obtain the log, etc.  The
      former version returned the value in a field called ``pRef``
    * The use of camel-case ``extraVars``, ``encryptionKey``, and
      ``inventoryFile`` are deprecated and will be removed in a future version.
      Use ``extra-vars``, ``encryption-key`` and ``inventory`` instead.
    """
    args = get_command_args()

    if name in STATIC_PLAYBOOKS:
        cwd = PRE_PLAYBOOKS_DIR
    else:
        cwd = PLAYBOOKS_DIR

    # Prevent some special playbooks from multiple concurrent invocations
    if name in ("site", "config-processor-run", "config-processor-clean",
                "ready-deployment"):
        if is_playbook_running(name):
            abort(403, "Already running")

    try:
        name += ".yml"
        for filename in os.listdir(PLAYBOOKS_DIR):
            if filename == name:
                break
        else:
            abort(404, "Playbook not found")

        playbook_name = os.path.join(PLAYBOOKS_DIR, name)

        # If we created a vault password file (in get_commands_args), then make
        # sure that it gets cleaned up after the playbook has run.
        # functools.partial is used to bind the vault_file to the function
        # parameter here since the place where the cleanup is called does not
        # have ready access to that filename
        cleanup = None
        vault_file = args.get('--vault-password-file')
        if vault_file:
            cleanup = functools.partial(remove_temp_vault_pwd_file, vault_file)

        return start_playbook(playbook_name,
                              args=args,
                              cwd=cwd,
                              cleanup=cleanup)

    except OSError as e:
        LOG.exception(e)
        abort(404)


def get_command_args(payload={}):
    # Process the body of the http request and extract and build the command
    # line arguments for the invocation of the ansible-playbook command.  For
    # testing, the payload can be given as an arg to this function
    body = payload or request.get_json() or {}

    # Normalize the keys by removing all of the leading dashes from the keys,
    # since they are optional
    body = {k.lstrip('-'): v for k, v in body.iteritems()}

    # Handle a couple of old key formats for backward compatibility
    if 'extraVars' in body:
        body['extra-vars'] = body.pop('extraVars')
    if 'inventoryFile' in body:
        body['inventory'] = body.pop('inventoryFile')
    if 'encryptionKey' in body:
        body['encryption-key'] = body.pop('encryptionKey')

    # The value of the extra-vars can be supplied either as a list of key-value
    # pairs, e.g.  ["key1=val1", "key2=val2"], or a nested object,
    # e.g., { "key1": "val1", "key2": "val2" }.  If it is in the former,
    # convert it to the latter.  In either case, the final version is
    # converted into a string for passing to `ansible-playbook`

    if 'extra-vars' in body:
        if type(body.get("extra-vars")) is list:
            extra_vars = {}
            for keyval in body["extra-vars"]:
                try:
                    (key, val) = keyval.split("=", 1)
                    extra_vars[key] = val
                except ValueError:
                    pass
            body["extra-vars"] = extra_vars

        # Convert to a json string
        body["extra-vars"] = json.dumps(body["extra-vars"])

    # Permit inventory file to be overriden
    if 'inventory' in body:
        if body['inventory'] is None:
            body.pop('inventory')
    else:
        body['inventory'] = "hosts/verb_hosts"

    # TODO(gary): Consider supporting force-color, which used to set the
    # env ANSIBLE_FORCE_COLOR=true and pop from args.  Since the installer
    # will now process the logs more intelligently, the need to supply
    # color-coded logs in the UI is diminished

    # If encryption-key is specified, store it in a temp file and adjust the
    # args accordingly
    if 'encryption-key' in body:
        encryption_key = body.pop('encryption-key')
        with tempfile.NamedTemporaryFile(suffix='', prefix='.vault-pwd',
                                         dir=PLAYBOOKS_DIR, delete=False) as f:
            f.write(encryption_key)
        body['vault-password-file'] = f.name

    # Finally normalize all keys to have the leading --
    args = {'--' + k: v for k, v in body.iteritems()}

    return args


def remove_temp_vault_pwd_file(filename):
    try:
        os.unlink(filename)
    except OSError as e:
        LOG.exception(e)
        pass


def start_playbook(playbook, args={}, cwd=None, cleanup=None):

    # Create processes with the subprocess module rather
    # than using a more advanced mechanism like Celery
    # (http://www.celeryproject.org/) in order to avoid introducing run-time
    # requirements on external systems (like REDIS, rabbitmq, etc.), since
    # this program will be used in an installation scenario where those sytems
    # are not yet running.

    cmd = build_command_line('ansible-playbook', playbook, args)

    # Prevent python programs from buffering their output.  Buffering causes
    # the output to be delayed, making it more difficult to determine the
    # real progress of the playbook
    env = {'PYTHONUNBUFFERED': '1'}

    ps = subprocess.Popen(cmd, cwd=cwd, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    start_time = int(1000 * time.time())
    id = str(ps.pid)
    meta_file = get_metadata_file(id)

    scrubbed = scrub_passwords(args)
    logged_cmd = build_command_line('ansible-playbook', playbook, scrubbed)

    play = {
        "id": id,
        "startTime": start_time,
        "commandString": ' '.join(logged_cmd),
        'killed': False
    }
    try:
        with open(meta_file, "w") as f:
            json.dump(play, f)
    except (IOError, OSError) as e:
        LOG.exception(e)
        abort(500, "Unable to write metadata")

    # Use a thread to read the pipe to avoid blocking this process.  Since
    # the thread will interact with socketio, we have to use that library's
    # function for creating threads
    tasks[id] = {'task': socketio.start_background_task(monitor_output,
                                                        ps, id, cleanup),
                 'playbook': playbook}

    LOG.debug("Spawned thread with task %s", id)

    return jsonify({"id": id}), 202, {'Location': url_for('plays.get_play',
                                                          id=id)}


def build_command_line(command, playbook=None, args={}):

    # Build the command line as a list of arguments to be passed to the

    cmdLine = []

    # For dev/testing, support using a mock script
    alt_command = config.get("testing", "mock_cmd")
    if alt_command:
        cmdLine.append(alt_command)

    cmdLine.append(command)

    if playbook:
        cmdLine.append(playbook)

    if isinstance(args, list):
        cmdLine.extend(args)
    elif isinstance(args, dict):
        for k, v in args.iteritems():
            cmdLine.append(k)
            cmdLine.append(v)
    elif args:
        cmdLine.append(args)

    return cmdLine


def scrub_passwords(args):
    # Build a sanitized version of the args dict that has passwords replaced
    # with asterisks.  This resulting list can be saved in files that are
    # readable

    scrubbed = {}
    for k, v in args.iteritems():
        if k in ('--encrypt', '--rekey'):
            scrubbed[k] = "****"
        else:
            scrubbed[k] = v
    return scrubbed


def monitor_output(ps, id, cleanup):
    # Monitor the piped output of the running process, forwarding each message
    # received to listening socketIO clients

    log_file = get_log_file(id)

    with open(log_file, 'w') as f:
        with ps.stdout:
            # Can use this in python3: for line in ps.stdout:
            # Using iter() per https://stackoverflow.com/a/17698359/190597
            for line in iter(ps.stdout.readline, b''):
                # python 2 returns bytes that must be converted to a string
                if isinstance(line, bytes):
                    line = line.decode("utf-8")

                f.write(line)
                f.flush()
                socketio.emit("log", line, room=id)

    # Notify listeners that the playbook has ended
    socketio.emit("end", room=id)
    socketio.close_room(id)
    ps.wait()

    # Update the metadata now that the process has finished.
    meta_file = get_metadata_file(id)
    lock = filelock.SoftFileLock(get_metadata_lockfile(id))
    tasks.pop(id, None)

    try:
        # Writes should be very fast
        with lock.acquire(timeout=3):
            with open(meta_file) as f:
                play = json.load(f)

            play['endTime'] = int(1000 * time.time())
            play['code'] = ps.returncode
            play['logSize'] = os.stat(log_file).st_size
            with open(meta_file, "w") as f:
                json.dump(play, f)

        # Call the cleanup function passed in, if any
        if cleanup:
            cleanup()

    except (IOError, OSError, filelock.Timeout):
        pass


# @socketio.on('connect')
# def on_connect():
#     LOG.info("Client connected")


# @socketio.on('disconnect')
# def on_disconnect():
#     LOG.info("Client disconnected")


@socketio.on('join')  # , namespace='/log')
def on_join(id):

    id = str(id)
    logfile = get_log_file(id)

    # replay existing log as messages before joining the room
    with open(logfile) as f:
        LOG.info("Replaying logs from %s", logfile)
        for line in f:
            emit("log", line)

    # It is possible that in the very short gap between reading the last line
    # in the file and the upcoming logic that a message may be generated by the
    # process.  In that case, the message may not be sent to the caller
    # (although it will still be logged).  If it is critical that absolutely no
    # message ever be dropped, then some thread synchronization needs to be
    # introduced (between this thread and the one reading the pipe).  That
    # would come at a cost in code complexity and performance.
    if id in tasks:
        LOG.info("Client joining room %s", id)
        join_room(id)
    else:
        emit("end")


def get_log_file(id):
    return os.path.join(LOGS_DIR, str(id) + ".log")


def is_playbook_running(playbook):
    # Determine whether the given playbook is running by looking through the
    # tasks dictionary

    wanted = os.path.join(PLAYBOOKS_DIR, playbook + ".yml")
    for task in tasks.values():
        if task['playbook'] == wanted:
            return True
