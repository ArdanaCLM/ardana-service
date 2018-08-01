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

import collections
from flask import abort
from flask import Blueprint
from flask import jsonify
from flask import request
import os
from oslo_config import cfg
from oslo_log import log as logging

from . import policy

LOG = logging.getLogger(__name__)
bp = Blueprint('service', __name__)
CONF = cfg.CONF


@bp.route("/api/v2/service/files", methods=['GET'])
@policy.enforce('lifecycle:get_service_file')
def get_all_files():
    """List available service configuration files

    .. :quickref: Service Config; List available service configuration files

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       [
            {
                "files": [
                    "cinder-monitor-cron.j2",
                    "cinderlm.conf.j2",
                    "api-paste.ini.j2",
                    "cinder-logging.conf.j2",
                    "block-monitor-periodic-cron.j2",
                    "api_audit_map.conf.j2",
                    "api.conf.j2",
                    "scheduler-logging.conf.j2",
                    "rootwrap.conf.j2",
                    "volume-logging.conf.j2",
                    "api-logging.conf.j2",
                    "backup.conf.j2",
                    "backup-logging.conf.j2",
                    "api-cinder.conf.j2",
                    "policy.json.j2",
                    "scheduler.conf.j2",
                    "volume.conf.j2",
                    "cinder.conf.j2"
                ],
                "service": "cinder"
            },
       ]

    """

    service_list = collections.defaultdict(list)
    for root, dirs, files in os.walk(CONF.paths.config_dir, followlinks=True):
        if root == CONF.paths.config_dir:
            continue
        for file in files:
            if file.endswith(('.j2', '.yml')):
                relname = os.path.relpath(os.path.join(root, file),
                                          CONF.paths.config_dir)
                (service, file_path) = relname.split('/', 1)
                service_list[service].append(file_path)
    result = [{'service': svc, 'files': files}
              for svc, files in service_list.items()]
    return jsonify(result)


@bp.route("/api/v2/service/files/<path:name>", methods=['GET'])
@policy.enforce('lifecycle:get_service_file')
def get_service_file(name):
    """Retrieve a service configuration file

    .. :quickref: Service Config; Retrieve the contents of a service config \
        file

    :param path: service config file name

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/service/files/neutron/dnsmasq-neutron.conf.j2 HTTP/1.1
       Content-Type: application/json

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       dhcp-option-force=26,1400

       # Create the "ipxe" tag if request comes from iPXE user class
       dhcp-userclass=set:ipxe,iPXE

    """

    filename = os.path.join(CONF.paths.config_dir, name)
    contents = ''
    try:
        with open(filename) as f:
            lines = f.readlines()
        contents = contents.join(lines)

    except IOError as e:
        LOG.exception(e)
        abort(400)

    return jsonify(contents)


@bp.route("/api/v2/service/files/<path:name>", methods=['POST'])
@policy.enforce('lifecycle:update_service_file')
def update_service_file(name):
    """Update a service configuration file

    Replace the contents of the given service configuration file with the
    request body

    .. :quickref: Service Config; Update the contents of a service config file

    :param path: service config file name
    """

    data = request.get_json()

    filename = os.path.join(CONF.paths.config_dir, name)
    try:
        with open(filename, "w") as f:
            f.write(data)
        return jsonify('Success')
    except Exception as e:
        LOG.exception(e)
        abort(400)
