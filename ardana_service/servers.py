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

from flask import abort
from flask import Blueprint
from flask import copy_current_request_context
from flask import jsonify
from flask import request
import os
from oslo_config import cfg
from oslo_log import log as logging
import time
import yaml

from . import model as model_api
from . import playbooks
from . import policy
from . import versions

LOG = logging.getLogger(__name__)

bp = Blueprint('servers', __name__)
CONF = cfg.CONF


@bp.route("/api/v2/servers/process", methods=['POST'])
@policy.enforce('lifecycle:run_playbook')
def add_server():
    """Add compute node

    Adds a compute node by performing the following steps:

    - update the customer model
    - commit changes to the model
    - run the config processor playbook
    - run the ready deployment playbook
    - run the site playbook
    - run the monasca-deploy playbook

    .. :quickref: Server; Add compute node

    **Example Request**:

    The request contains two objects: a `server` object containing the
    information to be stored in the input model, and a `process` object
    containing values relevant to the process of adding a new server.

    .. sourcecode:: http

       POST /api/v2/servers/process HTTP/1.1
       Content-Type: application/json

       {
           "server" : {
               "id": "ID"
           },
           "process" : {
               "encryption-key": "somekey",
               "commitMessage": "Adding a new server"
           }
       }


    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 202 ACCEPTED
       Content-Type: application/json
       Location: http://localhost:9085/api/v2/plays/6858

       {
           "id": 6858
       }

    **Changed for v2**:

    The `limitToId` field from the `process` object is no longer used.  It
    was used as a way to optionally supply the `--limit` parameter to certain
    playbooks, and it was *always* being supplied by the callers (because it
    makes no sense NOT to use it).  The `--limit` parameter will now
    automatically be supplied.
    """

    body = request.get_json()

    # Extract the keys of interest from the request body and normalize the
    # request arguments
    keys = ('commitMessage',
            'encryptionKey',
            'encryption-key')
    opts = pick(body.get('process'), keys)

    if 'encryptionKey' in opts:
        # this is a hack workaround for the fact that add-server requires
        # the encrypt extra-var, but the vast majority of playbook api
        # calls expect it as an excryption-key parameter
        # rekey is generally set to the empty string, though an option
        # to pass through an explicit value is added here as a precaution
        # against future usage
        opts['extra-vars'] = {
          'encrypt': opts.pop('encryption-key', ''),
          'rekey': opts.pop('rekey', '')
        }

    try:
        server_id = body['server']['id']
    except KeyError:
        abort(400, 'Server id missing')

    if 'commitMessage' not in opts:
        opts['commitMessage'] = 'Add server %s' % server_id

    # get the model
    model = model_api.read_model()

    servers = model['inputModel']['servers']
    # Make sure the server does not already exist in the model
    if server_id in [s['id'] for s in servers]:
        abort(400, 'Server %s already exists' % server_id)

    servers.append(body['server'])

    model_api.write_model(model)

    # commit the model
    versions.commit_model(message=opts['commitMessage'])

    play_id = int(1000 * time.time())

    # The following local functions are all steps that will be run
    # asynchronously in a series of promises.  In (some) other languages that
    # support promises, code blocks can be entered directly as an argument
    # to the 'then' function, but this is not easily done in python.  The
    # closest thing to them might be multi-line lambda functions, but these
    # are intentionally unsupported in python:
    # http://www.artima.com/weblogs/viewpost.jsp?thread=147358
    #
    # For clarity, the functions will be defined in the same order that they
    # are called.  The @copy_current_request_context decorator provided
    # by flask permits functions to access the http context supplied to the
    # parent function.
    @copy_current_request_context
    def run_config_processor_playbook():
        LOG.info("Running config processor playbook")

        payload = pick(opts, ('extra-vars',))
        result = playbooks.run_playbook('config-processor-run', payload,
                                        play_id)
        # return the entire result object, including the promise and
        # other data
        return result

    @copy_current_request_context
    def run_ready_deployment_playbook(prev):
        LOG.info("Running ready deployment playbook")

        result = playbooks.run_playbook('ready-deployment', play_id=play_id)
        return result['promise']

    @copy_current_request_context
    def retrieve_hostname(prev):
        LOG.info("Retrieving hostname from config processor output")

        # Read the CP output and get the hostname
        try:
            filename = os.path.join(CONF.paths.cp_ready_output_dir,
                                    'server_info.yml')

            with open(filename) as f:
                lines = f.readlines()
            raw = ''.join(lines)

            servers = yaml.safe_load(raw)

            if server_id in servers:
                if 'hostname' in servers[server_id]:
                    opts['limit'] = servers[server_id]['hostname']
                else:
                    LOG.info('Server %s has no hostname so skipping --limit' %
                             server_id)
            else:
                LOG.info('Unable to locate server %s so skipping --limit' %
                         server_id)

        except (OSError, IOError):
            message = "Unable to read %s" % filename
            LOG.error(message)
            raise Exception(message)

        except yaml.YAMLError:
            # If the generated file is not valid yml, there is some problem
            # with the config processor
            message = "%s is not a valid yaml file" % filename
            LOG.error(message)
            raise Exception(message)

    @copy_current_request_context
    def run_site_playbook(prev):
        LOG.info("Running site playbook")

        # run site playbook, limited to the given hostname if possible
        payload = pick(opts, ('encryption-key', 'limit'))
        result = playbooks.run_playbook('site', payload, play_id)
        return result['promise']

    @copy_current_request_context
    def generate_hosts_file(prev):
        LOG.info("Generating hosts file")

        payload = pick(opts, ('encryption-key', ))
        payload['tags'] = 'generate_hosts_file'

        result = playbooks.run_playbook('site', payload, play_id)
        return result['promise']

    @copy_current_request_context
    def update_monasca(prev):
        LOG.info("Running monasca-deploy playbook")

        payload = pick(opts, ('encryption-key', ))
        payload['tags'] = 'active_ping_checks'

        result = playbooks.run_playbook('monasca-deploy', payload, play_id)
        return result['promise']

    @copy_current_request_context
    def cleanup(prev):
        LOG.info("Server successfully added")

    @copy_current_request_context
    def failure(e):
        LOG.exception(e)

    # Perform all asynchronous functions above in order.  Capture the
    # promise and other initial results from the first playbook launch in
    # order to return that info immediately to the caller
    result = run_config_processor_playbook()
    result['promise'].then(run_ready_deployment_playbook) \
        .then(retrieve_hostname) \
        .then(run_site_playbook) \
        .then(generate_hosts_file) \
        .then(update_monasca) \
        .then(cleanup) \
        .catch(failure)

    # Note: this returns *before* all of the asynchronus tasks are performed.
    return jsonify({"id": result['id']}), 202, {'Location': result['url']}


@bp.route("/api/v2/servers/<id>/process", methods=['DELETE'])
@policy.enforce('lifecycle:run_playbook')
def remove_server(id):
    """Remove compute node

    Remove a compute node by performing the following steps:

    - update the customer model
    - commit changes to the model
    - run the config processor playbook

    .. :quickref: Server; Remove compute node

    **Example Request**:

    The request contains contains a `process` object containing values relevant
    to the process of deleting a server.

    .. sourcecode:: http

       DELETE /api/v2/servers/5935/process HTTP/1.1
       Content-Type: application/json

       {
           "process" : {
               "encryption-key": "somekey",
               "commitMessage": "Deleting an old server"
           }
       }


    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 202 ACCEPTED
       Content-Type: application/json
       Location: http://localhost:9085/api/v2/plays/6858

       {
           "id": 6858
       }
    """

    try:
        body = request.get_json()
    except Exception as e:
        body = {}
        LOG.debug('DELETE server got empty json payload - this is probably ok')

    # Extract the keys of interest from the request body and normalize the
    # request arguments
    keys = ('commitMessage',
            'encryptionKey',
            'encryption-key')
    opts = pick(body, keys)

    if 'encryptionKey' in opts:
        opts['encryption-key'] = opts.pop('encryptionKey')

    if 'commitMessage' not in opts:
        opts['commitMessage'] = 'Remove server %s' % id

    # get the model
    model = model_api.read_model()

    servers = model['inputModel']['servers']

    # Make sure the server does not already exist in the model
    if id not in [s['id'] for s in servers]:
        abort(404, 'Server %s does not exist' % id)

    # Filter out the server to delete
    model['inputModel']['servers'] = [s for s in servers if s['id'] != id]

    model_api.write_model(model)

    # commit the model
    versions.commit_model(message=opts['commitMessage'])

    play_id = int(1000 * time.time())

    # The following local functions are all steps that will be run
    # asynchronously in a series of promises.  In (some) other languages that
    # support promises, code blocks can be entered directly as an argument
    # to the 'then' function, but this is not easily done in python.  The
    # closest thing to them might be multi-line lambda functions, but these
    # are intentionally unsupported in python:
    # http://www.artima.com/weblogs/viewpost.jsp?thread=147358
    #
    # For clarity, the functions will be defined in the same order that they
    # are called.  The @copy_current_request_context decorator provided
    # by flask permits functions to access the http context supplied to the
    # parent function.
    @copy_current_request_context
    def run_config_processor_playbook():
        LOG.info("Running config processor playbook")

        payload = pick(opts, ('encryption-key',))
        result = playbooks.run_playbook('config-processor-run', payload,
                                        play_id)
        # return the entire result object, including the promise and
        # other data
        return result

    @copy_current_request_context
    def run_ready_deployment_playbook(prev):
        LOG.info("Running ready deployment playbook")

        result = playbooks.run_playbook('ready-deployment', play_id=play_id)
        return result['promise']

    @copy_current_request_context
    def cleanup(prev):
        LOG.info("Server successfully removed")

    @copy_current_request_context
    def failure(e):
        LOG.exception(e)

    # Perform all asynchronous functions above in order.  Capture the
    # promise and other initial results from the first playbook launch in
    # order to return that info immediately to the caller
    result = run_config_processor_playbook()
    result['promise'].then(run_ready_deployment_playbook) \
        .then(cleanup) \
        .catch(failure)

    # Note: this returns *before* all of the asynchronus tasks are performed.
    return jsonify({"id": result['id']}), 202, {'Location': result['url']}


def pick(source_dict, keys):
    # Return a new dictionary containing on the keys specified (and
    # corresponding values) from the source dictionary
    results = {}
    for k in keys:
        if k in source_dict:
            results[k] = source_dict[k]
    return results
