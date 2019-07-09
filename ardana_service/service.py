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
import yaml

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

    # If ses/settings.yml is present and it refers to a file that is not
    # already included in the list, then include it in the list of returned
    # config files
    ses_config_path = get_ses_config_path()
    if ses_config_path:

        if os.path.exists(ses_config_path):
            # Avoid listing the file twice in the case that ses_config_path
            # points to a file within CONF.paths.config_dir. This is probably a
            # corner case since the documentation suggests using
            # /var/lib/ardana/ses/.  If the ses_config_path relative to
            # CONF.paths.config_dir starts with .., then it is outside of
            # that directory tree
            if os.path.relpath(ses_config_path, CONF.paths.config_dir).\
                    startswith('..'):
                service_list['ses'].append(ses_config_path)

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

    filename = resolve_filename(name)
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

    filename = resolve_filename(name)
    try:
        with open(filename, "w") as f:
            f.write(data)
        return jsonify('Success')
    except Exception as e:
        LOG.exception(e)
        abort(400)


@bp.route("/api/v2/service/files/<path:name>", methods=['DELETE'])
@policy.enforce('lifecycle:update_service_file')
def delete_service_file(name):
    """Delete a service configuration file

    .. :quickref: Service Config; Delete a service configuration file

    :param path: service config file name
    """

    filename = resolve_filename(name)
    try:
        if os.path.exists(filename):
            os.remove(filename)
        return jsonify('Success')
    except OSError as e:
        LOG.exception(e)
        abort(400)


def resolve_filename(name):
    # resolve a service filename to its a path.  Usually this involves
    # prefixing it with CONF.paths.config_dir, but if it is under the ses
    # service, it may instead refer to an absolute filename

    if name.startswith('ses//'):
        # If the filename is an absolute reference in the ses service, then
        # it points to a ses config file and should be returned as-is
        return name[4:]

    return os.path.join(CONF.paths.config_dir, name)


def load_yaml(path):
    content = None
    try:
        with open(path) as f:
            content = yaml.safe_load(f)
    except Exception:
        LOG.error("Unable to read %s", path)
    return content


def get_ses_config_path():
    # Return the full path (including filename) of the ses configuration

    # Load settings from 'config/ses/settings.yml`
    ses_settings_path = os.path.join(CONF.paths.config_dir,
                                     'ses', 'settings.yml')
    ses_settings = load_yaml(ses_settings_path)
    if not ses_settings:
        return None

    if 'ses_config_path' not in ses_settings or \
            'ses_config_file' not in ses_settings:
        return None

    return os.path.join(ses_settings['ses_config_path'],
                        ses_settings['ses_config_file'])


@bp.route("/api/v2/ses/configure", methods=['GET'])
@policy.enforce('lifecycle:get_service_file')
def get_ses_config_status():
    """Returns the status of the SES configuration in my_cloud

    Returns on object including the ses config file name, and whether
    ses is correctly configured (the specified ses config file contains valid
    yaml)

    **Example Request**:

    .. sourcecode:: http

    GET /api/v2/ses/configure HTTP/1.1

    **Example Response**:

    .. sourcecode:: http
    HTTP/1.1 200 OK

    {
        "ses_configured": false,
        "ses_config_path": "/some/path"
    }
    """

    result = {
        'ses_configured': False,
        'ses_config_path': None
    }

    ses_config_path = get_ses_config_path()
    if not ses_config_path:
        return jsonify(result)

    result['ses_config_path'] = ses_config_path

    # ses is considered to be configured if the ses_config_path is specified,
    # the file exists, and the file contains valid yaml
    if load_yaml(ses_config_path):
        result['ses_configured'] = True
    return jsonify(result)
