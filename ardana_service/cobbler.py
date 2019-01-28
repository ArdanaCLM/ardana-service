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
from flask import jsonify
from distutils.spawn import find_executable
from oslo_config import cfg
from oslo_log import log as logging

import os
import re
import subprocess

LOG = logging.getLogger(__name__)
bp = Blueprint('cobbler', __name__)
CONF = cfg.CONF


@bp.route("/api/v2/cobbler", methods=['GET'])
@policy.enforce('lifecycle:get_cobbler')
def cobbler_is_installed():
    """Get availavilty of cobbler on this host

        .. :quickref: Cobbler is present

        **Example Request**:

        .. sourcecode:: http

           GET /api/v2/cobbler HTTP/1.1
           Content-Type: application/json

        **Example Response**:

        .. sourcecode:: http

            HTTP/1.1 200 OK

            {
                "cobbler": true
            }
    """
    return jsonify({'cobbler': find_executable('cobbler') is not None})


@bp.route("/api/v2/cobbler/servers", methods=['GET'])
@policy.enforce('lifecycle:get_cobbler')
def cobbler_get_servers():
    """Get list of server ids and addresses from cobbler

        .. :quickref: Cobbler; Get server list

        **Example Request**:

        .. sourcecode:: http

           GET /api/v2/cobbler/systems HTTP/1.1
           Content-Type: application/json

        **Example Response**:

        .. sourcecode:: http

            HTTP/1.1 200 OK

            [{
               'name': 'MXQ51906R2',
               'ip': '192.168.10.162'
             },
            {
               'name': 'MXQ51906R2',
               'ip': '192.168.10.163'
             }]
    """
    servers = []
    try:
        # mock for running without cobbler
        if cfg.CONF.testing.use_mock:
            mock_output = "tools/cobbler_report.txt"
            json_file = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), mock_output)
            with open(json_file) as f:
                servers_lines = f.readlines()

        else:
            p = subprocess.Popen(
                ['sudo', 'cobbler', 'system', 'report'],
                stdout=subprocess.PIPE)
            servers_lines = p.communicate()[0].decode('utf-8').split('\n')

        re_name = re.compile(r'^Name\s*:\s*(?P<name>\S+)')
        re_ip = re.compile(r'^IP Address\s*:\s*(?P<ip>\S+)')

        # extract the name and IP address from the output
        for line in servers_lines:
            name_match = re_name.match(line)
            if name_match:
                name = name_match.group('name')

            ip_match = re_ip.match(line)
            if ip_match:
                ip = ip_match.group('ip')
                if name:
                    servers.append({'name': name, 'ip': ip})

        return jsonify(servers)

    except Exception as ex:
        LOG.exception("Failed to obtain system report from cobbler")
        LOG.exception(ex)
        abort(500, "Failed to obtain system report from cobbler")


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
