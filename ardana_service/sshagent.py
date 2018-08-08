# (c) Copyright 2018 SUSE LLC
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

from flask import Blueprint
from flask import jsonify
from flask import request
import os
from oslo_config import cfg
from oslo_log import log as logging
import paramiko
import pexpect
import psutil
import re
import subprocess

from . import policy

LOG = logging.getLogger(__name__)
bp = Blueprint('sshagent', __name__)
CONF = cfg.CONF

# This is the default private RSA key used by ardana-init which expands to
# /var/lib/ardana/.ssh/id_rsa
DEFAULT_KEY_PATH = os.path.expanduser('~/.ssh/id_rsa')
instance = None


# This class is a wrapper around the lifecycle of the ssh-agent process
class sshagent(object):
    def __init__(self, agent_env):
        self.agent_env = agent_env
        self.pid = agent_env['SSH_AGENT_PID']
        self.environ = {}
        self.environ.update(os.environ)
        self.environ.update(agent_env)
        self.pid_file = CONF.paths.ssh_agent_pid_file
        self.key_path = DEFAULT_KEY_PATH

        # Set system env var so paramiko can be used as a proxy to the running
        # ssh-agent
        os.environ['SSH_AUTH_SOCK'] = agent_env['SSH_AUTH_SOCK']

        # Save off the pid of the started ssh-agent
        try:
            with open(self.pid_file, "w") as f:
                f.write(self.pid)
        except Exception as e:
            LOG.error("Unable to save ssh-agent pid file at %s: %s" %
                      (self.pid_file, e))

    def __exit__(self, exc_type, exc_val, exc_tb):
        # On exit, such as a service stop, or a 'kill pid_of_ardana_service',
        # this method will be called to stop ssh-agent.
        # Note: Does not work in the tox development environment.
        # Note: This will not get run when the app is being reloaded by flask.
        #       But the old ssh-agent will be killed by looking up the pid in
        #       CONF.paths.ssh_agent_pid_file
        self.stop()

    @classmethod
    def start(cls):
        global instance
        if instance:
            return instance

        output = subprocess.check_output('ssh-agent')

        # get env vars from ssh-agent
        agent_env = {}
        for name, value in re.findall(r'([A-Z_]+)=([^;]+);', output.decode()):
            agent_env[name] = value
        LOG.info("Started ssh-agent at pid: %s" % agent_env['SSH_AGENT_PID'])

        instance = cls(agent_env)
        return instance

    def stop(self):
        global instance
        if self.pid != 0:
            LOG.info("Stopping ssh-agent at pid: %s" % self.pid)
            subprocess.check_call(['kill', self.pid])
            self.pid = 0
            instance = None
            return True
        return False

    def add_key(self, priv_key_path, password):
        # It does not appear as if paramiko has support for adding keys to
        # ssh-agent (https://github.com/paramiko/paramiko/issues/778), but if
        # they ever do, we should rewrite this function and remove the
        # pexpect dependency.
        self.key_path = priv_key_path
        if not os.path.exists(self.key_path) or \
                not os.path.isfile(self.key_path):
            err_msg = "Cannot add non-existent %s to ssh-agent" % self.key_path
            LOG.warning(err_msg)
            return 404, err_msg

        child = pexpect.spawn('ssh-add', [self.key_path], env=self.environ)
        try:
            result = child.expect(['Enter passphrase for .*: ',
                                   'Identity added: '], timeout=1)
            if result == 0:
                # The first phrase in the expect list requires a password entry
                if not password:
                    # empty passwords are not supported
                    raise ValueError("no password supplied")
                child.sendline(password)
                child.expect(pexpect.EOF, timeout=1)
                return 200, ""
            elif result == 1:
                # The second phrase shows it successfully added key without
                # password
                return 200, ""
            else:
                err_msg = "Attempt to add key to ssh-agent resulted in an " \
                          "unexpected result: %d" % result
                LOG.warning(err_msg)
                return 400, err_msg
        except pexpect.EOF:
            err_msg = "Could not add %s to ssh-agent.  " \
                      "Possibly bad file." % self.key_path
            LOG.warning(err_msg)
            return 400, err_msg
        except (pexpect.TIMEOUT, ValueError):
            err_msg = "Password supplied for ssh key is incorrect"
            LOG.warning(err_msg)
            return 401, err_msg
        finally:
            if child:
                child.close()

    @staticmethod
    def get_instance():
        return instance

    # Stop the previously running instance of ssh-agent if it's still running.
    @staticmethod
    def stop_old_instance():
        # If the service is being reloaded by flask, we will hit the state
        # where ssh-agent is orphaned and no longer have context to it.
        # Therefore, we need to kill it from the pid in the saved pid file.
        pid_file = CONF.paths.ssh_agent_pid_file
        try:
            with open(pid_file, "r") as f:
                pid_to_kill = f.read()
        except Exception as e:
            LOG.warning("Could not read pid from %s: %s" % (pid_file, e))
            return

        try:
            process = psutil.Process(int(pid_to_kill))
            if process.name() == 'ssh-agent':
                LOG.info("Killing old instance of ssh-agent pid: %s"
                         % pid_to_kill)
                subprocess.check_call(['kill', pid_to_kill])
                os.remove(pid_file)
        except psutil.NoSuchProcess:
            LOG.info('ssh-agent at pid: %s does not exist to be killed' %
                     pid_to_kill)
        except subprocess.CalledProcessError:
            LOG.warning('ssh-agent at pid: %s could not be killed' %
                        pid_to_kill)
        except ValueError:
            LOG.warning('ssh-agent pid: %s is not an integer' %
                        pid_to_kill)


@bp.route("/api/v2/sshagent/requires_password", methods=['GET'])
@policy.enforce('lifecycle:run_playbook')
def requires_password():
    """Check ssh key password requirement

    Checks to see if a passphrase/password is needed by the private ssh key.
    If it is needed and the user has not yet entered the passphrase for this
    key, it will return True.  If the user has already successfully entered the
    passphrase previously (by way of checking to see if there's already a key
    in the ssh-agent process) OR the private ssh key is not secured with a
    passphrase, then it will return False.

    Note: The ardana-service does not remember credentials across restarts.
          (i.e. ssh-agent will be reset when ardana-service restarts)

    .. :quickref: SSH Agent; does ssh key require password?

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/sshagent/requires_password HTTP/1.1
       Content-Type: application/json

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       {
           "requires_password": false
       }
    """

    if not instance:
        response = jsonify({"error_msg": "ssh-agent instance not running"})
        response.status_code = 400
        return response

    # If there's already a key in ssh-agent, assume there is no need to add
    # any keys because user already entered a passphrased key
    agent = paramiko.Agent()
    if len(agent.get_keys()):
        return jsonify({"requires_password": False})
    agent.close()

    try:
        paramiko.RSAKey.from_private_key_file(instance.key_path)
        return jsonify({"requires_password": False})
    except paramiko.ssh_exception.PasswordRequiredException:
        return jsonify({"requires_password": True})


@bp.route("/api/v2/sshagent/key", methods=['POST'])
@policy.enforce('lifecycle:run_playbook')
def add_key():
    """Add ssh key and password

    Adds a private ssh key to the ssh-agent with accompanying password.
    Returns a result whether they key was successfully added to ssh-agent.

    .. :quickref: SSH Agent; add ssh key and password

    :param private_key_path (optional):
           Location of the private ssh key.  If none is provide, the default,
           ~/.ssh/id_rsa, will be used.
    :param password (optional):
           Password for the key supplied by `private_key_path`.  If none is
           provided, no password will be used

    **Example Request**:

    .. sourcecode:: http

       POST /api/v2/sshagent/key HTTP/1.1
       Content-Type: application/json
       {
           "password": "my_bad_password"
       }

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 404 NOT FOUND

       {
           "error_msg": "Attempt to add a non-existent key to ssh-agent: /x"
       }

    :status 200: Key was successfully added to ssh-agent
    :status 400: Unexpected error while adding key to ssh-agent or key file
                 is bad
    :status 401: Incorrect password used for the supplied or default key
    :status 404: Specified private key file does not exist
    """

    data = request.get_json() or {}
    private_key_path = data.get('private_key_path', DEFAULT_KEY_PATH)
    password = data.get('password')
    status, value = instance.add_key(private_key_path, password)
    if status != 200:
        response = jsonify({"error_msg": value})
        response.status_code = status
        return response
    return jsonify('Success')
