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

from collections import OrderedDict
from flask import abort
from flask import Blueprint
from flask import jsonify
from flask import request
from flask import url_for
from flask_socketio import emit
from flask_socketio import join_room
import functools
import getopt
import json
import os
from oslo_config import cfg
from oslo_log import log as logging
from promise import Promise
import subprocess
import sys
import tempfile
import time

from . import plays
from . import policy
from . import socketio

LOG = logging.getLogger(__name__)

bp = Blueprint('playbooks', __name__)
CONF = cfg.CONF
test_opts = [
    cfg.BoolOpt('use_mock',
                default=False,
                help='Use a mocking tool to fake certain commands'),
    cfg.StrOpt('mock_cmd',
               default='tools/mock-cmd',
               help='Mock executable to execute in place of real command, '
                    'relative to the top-level directory'),
]
CONF.register_opts(test_opts, 'testing')

# These playbooks are run from a directory that exists even before
# the ready-deployment has been done (CONF.paths.pre_playbooks_dir)
STATIC_PLAYBOOKS = {
    'config-processor-run',
    'config-processor-clean',
    'ready-deployment',
    'dayzero-os-provision',
    'dayzero-pre-deployment'}

# TODO(jack) SCRD-2228 Refactor/rename the dayzero-* playbooks as installui-*

# TODO(gary) Consider creating a function to archive old plays (create a tgz
#    of log and metadata).  This feature is not mentioned anywhere, but the
#    old version did something similar to this


@bp.route("/api/v2/playbooks")
@policy.enforce('lifecycle:list_playbooks')
def playbooks():
    """List available playbooks

    Lists the playbook names (without the trailing ``.yml`` extension) of the
    playbooks that are available to run.

    .. :quickref: Playbook; List available playbooks

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
        for filename in os.listdir(CONF.paths.playbooks_dir):
            if filename[0] != '_' and filename.endswith('.yml'):
                # Strip off extension
                playbooks.add(filename[:-4])
    except OSError as e:
        LOG.exception(e)
        LOG.warning("Playbooks directory %s doesn't exist. This could indicate"
                    " that the ready_deployment playbook hasn't been run yet. "
                    "The list of playbooks available will be reduced",
                    CONF.paths.playbooks_dir)

    return jsonify(sorted(playbooks))


@bp.route("/api/v2/playbooks/<name>", methods=['POST'])
@policy.enforce('lifecycle:run_playbook')
def run_playbook_rest(name):
    """Run an ansible playbook

    JSON payload is an object that may contain key/value pairs that will be
    passed as command-line arguments to ``ansible playbook``.
    To simplify things a bit for the caller, the key may omit the leading
    dashes. For example::

       { 'limit' : 100 }

    will be converted to the command arguments ``--limit 100``

    .. :quickref: Playbook; Run a playbook by name

    :param name: playbook name, without the ``.yml`` suffix

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
    result = run_playbook(name, request.get_json())
    return jsonify({"id": result['id']}), 202, {'Location': result['url']}


def run_playbook(name, payload=None, play_id=None):
    # Run a playbook with the given payload  This function is separate from
    # the run_playbook_rest function in order to permit it to be called outside
    # of the context of a single REST call that returns immediately

    if name in STATIC_PLAYBOOKS:
        cwd = CONF.paths.pre_playbooks_dir
    else:
        cwd = CONF.paths.playbooks_dir

    args = get_command_args(payload, cwd)

    # Prevent some special playbooks from multiple concurrent invocations
    if name in ("site", "config-processor-run", "config-processor-clean",
                "ready-deployment", "dayzero-os-provision"):
        if get_running_playbook_id(name):
            abort(403, "Already running")

    try:
        name += ".yml"
        for filename in os.listdir(cwd):
            if filename == name:
                break
        else:
            abort(404, "Playbook not found")

        # If we created a vault password file (in get_commands_args), then make
        # sure that it gets cleaned up after the playbook has run.
        # functools.partial is used to bind the vault_file to the function
        # parameter here since the place where the cleanup is called does not
        # have ready access to that filename
        cleanup = None
        vault_file = args.get('--vault-password-file')
        if vault_file:
            cleanup = functools.partial(remove_temp_vault_pwd_file, vault_file)

        return start_playbook(name,
                              args=args,
                              cwd=cwd,
                              cleanup=cleanup,
                              play_id=play_id)

    except OSError as e:
        LOG.exception(e)
        abort(404)


def get_command_args(payload=None, cwd=None):
    # Process the body of the http request and extract and build the command
    # line arguments for the invocation of the ansible-playbook command.
    body = payload or {}

    # Normalize the keys by removing all of the leading dashes from the keys,
    # since they are optional
    body = {k.lstrip('-'): v for k, v in body.items()}

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
    elif cwd and cwd == CONF.paths.pre_playbooks_dir:
        body['inventory'] = "hosts/localhost"
    else:
        body['inventory'] = "hosts/verb_hosts"

    # Debug level
    if 'verbose' in body:
        if body['verbose'] == 0 or body['verbose'] == "0":
            body.pop('verbose')

    # TODO(gary): Consider supporting force-color, which used to set the
    # env ANSIBLE_FORCE_COLOR=true and pop from args.  Since the installer
    # will now process the logs more intelligently, the need to supply
    # color-coded logs in the UI is diminished

    # If encryption-key is specified, store it in a temp file and adjust the
    # args accordingly
    if 'encryption-key' in body:
        encryption_key = body.pop('encryption-key')
        with tempfile.NamedTemporaryFile(suffix='', prefix='.vault-pwd',
                                         dir=CONF.paths.playbooks_dir,
                                         delete=False) as f:
            f.write(encryption_key.encode('utf-8'))
        body['vault-password-file'] = f.name

    # Finally normalize all keys to have the leading --
    args = {'--' + k: v for k, v in body.items()}

    return args


def remove_temp_vault_pwd_file(filename):
    try:
        os.unlink(filename)
    except OSError as e:
        LOG.exception(e)
        pass


def start_playbook(playbook, args={}, cwd=None, cleanup=None, play_id=None):

    # Create processes with the subprocess module rather
    # than using a more advanced mechanism like Celery
    # (http://www.celeryproject.org/) in order to avoid introducing run-time
    # requirements on external systems (like REDIS, rabbitmq, etc.), since
    # this program will be used in an installation scenario where those sytems
    # are not yet running.

    cmd = build_command_line('ansible-playbook', playbook, args)

    start_time = int(1000 * time.time())
    id = play_id if play_id is not None else str(start_time)

    # Prevent python programs from buffering their output.  Buffering causes
    # the output to be delayed, making it more difficult to determine the
    # real progress of the playbook
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    env['PLAY_ID'] = str(id)

    if sys.version_info.major < 3:
        ps = subprocess.Popen(cmd, cwd=cwd, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    else:
        ps = subprocess.Popen(cmd, cwd=cwd, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              universal_newlines=True)

    meta_file = plays.get_metadata_file(id)

    scrubbed = scrub_passwords(args)
    logged_cmd = build_command_line('ansible-playbook', playbook, scrubbed)

    play = {
        "id": id,
        "startTime": start_time,
        "commandString": ' '.join(logged_cmd),
        'killed': False,
        'pid': ps.pid,
        'playbook': playbook
    }
    try:
        with open(meta_file, "w") as f:
            json.dump(play, f)
    except (IOError, OSError) as e:
        LOG.exception(e)
        abort(500, "Unable to write metadata")

    # Create a promise to be returned for clients interested in the promise
    promise = Promise()

    # Use a thread to read the pipe to avoid blocking this process.  Since
    # the thread will interact with socketio, we have to use that library's
    # function for creating threads
    running = plays.get_running_plays()
    running[id] = {'task': socketio.start_background_task(monitor_output,
                                                          ps, id, cleanup,
                                                          promise),
                   'playbook': playbook}

    LOG.debug("Spawned thread with play %s", id)

    return {"id": id,
            "url": url_for('plays.get_play', id=id),
            "promise": promise}


def build_command_line(command, playbook=None, args={}):

    # Build the command line as a list of arguments to be passed to the

    cmdLine = []

    # For dev/testing, support using a mock script
    if CONF.testing.use_mock:

        alt_command = CONF.testing.mock_cmd
        # Use the same python executable in order to be able to make
        # use of share libs like oslo_config
        cmdLine.append(sys.executable)

        # Relative path should be resolved w.r.t. the top-level dir
        if not os.path.isabs(alt_command):
            alt_command = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", alt_command))
        cmdLine.append(alt_command)

        # Append the --config-file and --config-dir args of the command line of
        # the ardana_server to the one being created for the mock_cmd so that
        # it can read and process the same config files. If any paths are
        # relative paths, resolve them to absolute paths since the command may
        # be launched with a different cwd than the parent.
        try:
            opts, others = getopt.getopt(sys.argv[1:], None,
                                         ['config-file=', 'config-dir='])
            for opt, path in opts:
                cmdLine.append(opt)
                if not os.path.isabs(path):
                    path = os.path.normpath(
                        os.path.join(
                            os.path.dirname(os.path.dirname(__file__)), path))
                cmdLine.append(path)

        except getopt.GetoptError as e:
            LOG.exception(e)
            abort(500)

    cmdLine.append(command)

    if playbook:
        cmdLine.append(playbook)

    if isinstance(args, list):
        cmdLine.extend(args)
    elif isinstance(args, dict):
        for k, v in args.items():
            if k == '--verbose':
                for i in range(0, int(v)):
                    cmdLine.append(k)
            else:
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
    for k, v in args.items():
        if k in ('--encrypt', '--rekey'):
            scrubbed[k] = "****"
        else:
            scrubbed[k] = v
    return scrubbed


def monitor_output(ps, id, cleanup, promise):
    # Monitor the piped output of the running process, forwarding each message
    # received to listening socketIO clients

    log_file = get_log_file(id)

    with open(log_file, 'a') as f:
        # Reading subprocess line by line varies in python2 vs python3.  See
        # https://stackoverflow.com/a/17698359/190597
        #
        # Can use this in python3: for line in ps.stdout:
        if sys.version_info.major < 3:
            with ps.stdout:
                for line in iter(ps.stdout.readline, b''):
                    if isinstance(line, bytes):
                        f.write(line)
                    else:
                        f.write(line.encode("utf-8"))
                    f.flush()
                    socketio.emit("log", line, room=id)
        else:
            for line in ps.stdout:
                f.write(line)
                f.flush()
                socketio.emit("log", line, room=id)

    # Notify listeners that the process has ended
    socketio.emit("end", room=id)
    socketio.close_room(id)
    ps.wait()

    # Update the metadata now that the process has finished.
    meta_file = plays.get_metadata_file(id)
    running = plays.get_running_plays()
    running.pop(id, None)

    try:
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

    except (IOError, OSError):
        pass

    if ps.returncode == 0:
        promise.do_resolve('Success')
    else:
        promise.do_reject(Exception("Play %s failed" % id))


@socketio.on('connect')
def on_connect():
    LOG.info("Client connected. sid: %s", request.sid)


@socketio.on('disconnect')
def on_disconnect():
    LOG.info("Client disconnected. sid: %s", request.sid)


@socketio.on('join')
def on_join(id):

    id = str(id)
    logfile = get_log_file(id)

    # replay existing log as a single message before joining the room
    LOG.info("Replaying logs from %s", logfile)
    with open(logfile) as f:
        lines = f.readlines()

    emit("log", ''.join(lines))

    # Replay existing events before joinging the room
    events_file = get_events_file(id)
    if os.path.exists(events_file):
        LOG.info("Replaying events from %s", events_file)
        try:
            with open(events_file) as f:
                events = json.load(f)

            # Avoid sending unnecessary events: send only the last event for
            # each playbook
            last_events = OrderedDict()
            for e in events:
                last_events[e['playbook']] = e['event']

            for playbook, event in last_events.items():
                emit(event, playbook)

        except IOError:
            pass

    # It is possible that in the short gap between reading the last line
    # in the logfile and the upcoming logic that a message may be generated by
    # the process.  In that case, the message may not be sent to the caller
    # (although it will still be logged).  If it is critical that absolutely no
    # message ever be dropped, then some thread synchronization needs to be
    # introduced (between this thread and the one reading the pipe).  That
    # would come at a cost in code complexity and performance.
    running = plays.get_running_plays()
    if id in running:
        LOG.info("Client joining room %s", id)
        join_room(id)
    else:
        emit("end")


def get_log_file(id):
    return os.path.join(CONF.paths.log_dir, str(id) + ".log")


def get_events_file(id):
    return os.path.join(CONF.paths.log_dir, str(id) + ".events")


def get_running_playbook_id(playbook):
    # Determine whether the given playbook is running by looking through the
    # plays dictionary

    # Just look at the basename of the playbook (without the the .yml suffix)
    wanted = plays.basename(playbook)

    running = plays.get_running_plays()
    for id, play in running.items():
        if plays.basename(play['playbook']) == wanted:
            return id
