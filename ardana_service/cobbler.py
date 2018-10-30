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

from . import policy

from flask import abort
from flask import Blueprint
from flask import json
from flask import jsonify
from oslo_config import cfg
from oslo_log import log as logging

import os
import subprocess

LOG = logging.getLogger(__name__)
bp = Blueprint('cobbler', __name__)
CONF = cfg.CONF


@bp.route("/api/v2/cobbler/servers", methods=['GET'])
@policy.enforce('lifecycle:get_cobbler')
def cobbler_get_servers():
    """Get Server ids list from cobbler

        .. :quickref: Cobbler; Get server ids

        **Example Request**:

        .. sourcecode:: http

           GET /api/v2/cobbler/systems HTTP/1.1
           Content-Type: application/json

        **Example Response**:

        .. sourcecode:: http

            HTTP/1.1 200 OK

            ['compute1', 'compute2', 'compute3']
    """
    # mock for running sudo cobbler system list command
    if cfg.CONF.testing.use_mock:

        mock_json = "tools/cobbler_systems.json"
        json_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), mock_json)
        with open(json_file) as f:
            return jsonify(json.load(f))

    servers = []
    try:
        p = subprocess.Popen(
            ['sudo', 'cobbler', 'system', 'list'],
            stdout=subprocess.PIPE)
        servers_lines = p.communicate()[0].decode('utf-8').split('\n')
        # clean up the output
        if servers_lines:
            servers = \
                [server.strip() for server in servers_lines
                 if len(server) > 0]
        return jsonify(servers)

    except Exception as ex:
        LOG.exception("Failed to run cobbler system list command")
        LOG.exception(ex)
        abort(500, "Failed to run cobbler system list command")


@bp.route("/api/v2/cobbler/servers/<serverid>", methods=['DELETE'])
@policy.enforce('lifecycle:update_cobbler')
def cobbler_delete_server(serverid):
    """Delete a server from cobbler

        .. :quickref: Cobbler; Delete a server by server id

        **Example Request**:

        .. sourcecode:: http

           DELETE /api/v2/cobbler/servers/<serverid> HTTP/1.1
           Content-Type: application/json

        **Example Response**:

        .. sourcecode:: http

            HTTP/1.1 200 OK

           'Success'
    """
    # mock for running sudo cobbler system remove --name=serverid command
    if cfg.CONF.testing.use_mock:
        return jsonify('Success')

    try:
        subprocess.check_call([
            'sudo', 'cobbler', 'system', 'remove', '--name=' + serverid])
        return jsonify('Success')

    except Exception as ex:
        msg = 'Unable to remove server %s from cobbler' % serverid
        LOG.error(msg)
        LOG.error(ex)
        abort(500, msg)
