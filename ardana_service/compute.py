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
from flask import request
import json
from keystoneauth1 import loading
from keystoneauth1 import session
from novaclient import client as novaClient
import os
from oslo_config import cfg
from oslo_log import log as logging

LOG = logging.getLogger(__name__)
bp = Blueprint('compute', __name__)
CONF = cfg.CONF


def get_compute_client(req):

    try:
        loader = loading.get_plugin_loader('v3token')
        auth = loader.load_from_options(
            auth_url=CONF.keystone_authtoken.auth_url,
            token=req.headers.get('X-Auth-Token'),
            project_name=CONF.keystone_authtoken.project_name,
            project_domain_name=CONF.keystone_authtoken.project_domain_name
        )
        sess = session.Session(auth=auth,
                               verify=not CONF.keystone_authtoken.insecure)
        compute_client = novaClient.Client(
            # api version for live_migrate with block_migration='auto'
            '2.25',
            endpoint_type="internalURL",
            session=sess
        )
        return compute_client

    except Exception as e:
        LOG.error(e)
        abort(500, 'Failed to get compute novaclient')


def complete_with_errors_response(msg, contents):
    response = jsonify({'error_msg': msg, 'contents': contents})
    response.status_code = 500
    return response


@bp.route("/api/v2/compute/services/<hostname>", methods=['GET'])
@policy.enforce('lifecycle:get_compute')
def compute_services_status(hostname):
    """Get the compute services status for a compute host

        .. :quickref: Compute; Get the compute services status

        **Example Request**:

        .. sourcecode:: http

           GET /api/v2/compute/services/<hostname> HTTP/1.1
           Content-Type: application/json

        **Example Response**:

        .. sourcecode:: http

            HTTP/1.1 200 OK

            {
                "nova-compute": "enabled"
            }

    """
    # mock for getting nova service status for a compute host
    if cfg.CONF.testing.use_mock:
        mock_json = "tools/compute-mock-data.json"
        json_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), mock_json)
        with open(json_file) as f:
            return jsonify(json.load(f)['compute_services_status'])

    compute_client = get_compute_client(request)

    compute_services = compute_client.services.list(host=hostname)

    if len(compute_services) == 0:
        msg = 'No compute service for %s' % hostname
        LOG.error(msg)
        abort(410, msg)

    services = dict()

    for service in compute_services:
        binary = getattr(service, 'binary', None)
        if binary:
            services[binary] = \
                getattr(service, 'status', None) == 'enabled'

    return jsonify(services)


@bp.route("/api/v2/compute/services/<hostname>/disable", methods=['PUT'])
@policy.enforce('lifecycle:update_compute')
def compute_disable_services(hostname):
    """Disable the compute services for a compute host

        .. :quickref: Compute; Disable the compute services

        **Example Request**:

        .. sourcecode:: http

           PUT /api/v2/compute/services/<hostname>/disable HTTP/1.1
           Content-Type: application/json

        **Example Response**:

        .. sourcecode:: http

            HTTP/1.1 200 OK

            [{
                "binary": "nova-compute",
                "id": 1
            }]

    """
    # mock for running nova disable service for a compute host
    if cfg.CONF.testing.use_mock:
        mock_json = "tools/compute-mock-data.json"
        json_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), mock_json)
        with open(json_file) as f:
            return jsonify(json.load(f)['disable_compute_services'])

    compute_client = get_compute_client(request)

    compute_services = compute_client.services.list(host=hostname)

    if len(compute_services) == 0:
        msg = 'No compute service for %s' % hostname
        LOG.error(msg)
        abort(410, msg)

    failed = []
    disabled = []
    for service in compute_services:
        binary = getattr(service, 'binary', '')
        id = getattr(service, 'id')
        status = getattr(service, 'status', '')
        if status == 'enabled':
            try:
                compute_client.services.disable(hostname, binary)
                disabled.append({'id': id, 'binary': binary})
            except Exception as ex:
                failed.append({'id': id, 'binary': binary, 'error': str(ex)})
                LOG.error(
                    'Failed to disable compute service for %s id = %s' +
                    'binary = % s' % (hostname, id, binary))
                LOG.error(ex)
        else:
            # already disabled, will not call
            disabled.append({'id': id, 'binary': binary})

    if len(failed) > 0:
        return complete_with_errors_response(
            'Completed disabling compute services with errors',
            {'failed': failed, 'disabled': disabled})

    return jsonify(disabled)


@bp.route("/api/v2/compute/services/<hostname>/enable", methods=['PUT'])
@policy.enforce('lifecycle:update_compute')
def compute_enable_services(hostname):
    """Enable the compute services for a compute host

        .. :quickref: Compute; Enable the compute services

        **Example Request**:

        .. sourcecode:: http

           PUT /api/v2/compute/services/<hostname>/enable HTTP/1.1
           Content-Type: application/json

        **Example Response**:

        .. sourcecode:: http

            HTTP/1.1 200 OK

            [{
                "binary": "nova-compute",
                "id": 1
            }]

    """
    # mock for running nova disable service for a compute host
    if cfg.CONF.testing.use_mock:
        mock_json = "tools/compute-mock-data.json"
        json_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), mock_json)
        with open(json_file) as f:
            return jsonify(json.load(f)['enable_compute_services'])

    compute_client = get_compute_client(request)

    compute_services = compute_client.services.list(host=hostname)

    if len(compute_services) == 0:
        msg = 'No compute service for %s' % hostname
        LOG.error(msg)
        abort(410, msg)

    failed = []
    enabled = []
    for service in compute_services:
        binary = getattr(service, 'binary', '')
        id = getattr(service, 'id')
        status = getattr(service, 'status', '')
        if status == 'disabled':
            try:
                compute_client.services.enable(hostname, binary)
                enabled.append({'id': id, 'binary': binary})
            except Exception as ex:
                failed.append({'id': id, 'binary': binary, 'error': str(ex)})
                LOG.error(
                    'Failed to enable compute service for %s id = %s' +
                    'binary = % s' % (hostname, id, binary))
                LOG.error(ex)
        else:
            # already enabled, will not call
            enabled.append({'id': id, 'binary': binary})

    if len(failed) > 0:
        return complete_with_errors_response(
            'Completed enabling compute services with errors',
            {'failed': failed, 'enabled': enabled})

    return jsonify(enabled)


@bp.route("/api/v2/compute/services/<hostname>", methods=['DELETE'])
@policy.enforce('lifecycle:update_compute')
def compute_delete_services(hostname):
    """Delete the compute services for a compute host

        .. :quickref: Compute; Delete the compute services

        **Example Request**:

        .. sourcecode:: http

           DELETE /api/v2/compute/services/<hostname> HTTP/1.1
           Content-Type: application/json

        **Example Response**:

        .. sourcecode:: http

            HTTP/1.1 200 OK

             [{
                "binary": "nova-compute"
                "id": 1
            }]
    """
    # mock for running nova delete service for a compute host
    if cfg.CONF.testing.use_mock:
        mock_json = "tools/compute-mock-data.json"
        json_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), mock_json)
        with open(json_file) as f:
            return jsonify(json.load(f)['delete_compute_services'])

    compute_client = get_compute_client(request)

    compute_services = compute_client.services.list(host=hostname)

    if len(compute_services) == 0:
        msg = 'No compute service for %s' % hostname
        LOG.error(msg)
        abort(410, msg)

    failed = []
    deleted = []
    for service in compute_services:
        binary = getattr(service, 'binary', '')
        id = getattr(service, 'id')
        try:
            compute_client.services.delete(id)
            deleted.append({'id': id, 'binary': binary})
        except Exception as ex:
            failed.append({'id': id, 'binary': binary, 'error': str(ex)})
            LOG.error(
                'Failed to delete compute service for %s id = %s binary = %s'
                % (hostname, id, binary))
            LOG.error(ex)

    if len(failed) > 0:
        return complete_with_errors_response(
            'Completed deleting compute services with errors',
            {'failed': failed, 'deleted': deleted})

    return jsonify(deleted)


@bp.route("/api/v2/compute/aggregates/<hostname>", methods=['DELETE'])
@policy.enforce('lifecycle:update_compute')
def compute_delete_aggregates(hostname):
    """Delete the aggregates for a compute host

        .. :quickref: Compute; Delete aggregates for a compute host

        **Example Request**:

        .. sourcecode:: http

           DELETE /api/v2/compute/aggregates/<hostname> HTTP/1.1
           Content-Type: application/json

        **Example Response**:

        .. sourcecode:: http

            HTTP/1.1 200 OK

            [{
                "availability_zone": "test-az",
                "id": 3,
                "name": "agg_group3"
            }, {
                "availability_zone": null,
                "id": 1,
                "name": "agg_group1"
            }, {
                "availability_zone": null,
                "id": 2,
                "name": "agg_group2"
            }]
    """
    # mock for running nova delete aggregates for a compute host
    # mock contains partial failure
    if cfg.CONF.testing.use_mock:
        mock_json = "tools/compute-mock-data.json"
        json_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), mock_json)
        with open(json_file) as f:
            return complete_with_errors_response(
                'Completed deleting aggregates with errors',
                json.load(f)['delete_aggregates'])

    compute_client = get_compute_client(request)

    # list all the aggregates
    compute_aggregates = compute_client.aggregates.list()

    if len(compute_aggregates) == 0:
        msg = 'No aggregates found for %s ' % hostname
        LOG.info(msg)
        abort(410, msg)

    # get details so we can decide which one we need to
    # remove compute host
    aggregates = []
    for aggr in compute_aggregates:
        details = compute_client.aggregates.get(aggr)
        id = getattr(aggr, 'id')
        name = getattr(aggr, 'name')
        az = getattr(aggr, 'availability_zone')
        if hostname in getattr(details, 'hosts', []):
            aggregates.append({
                'id': id, 'name': name, 'availability_zone': az})

    if len(aggregates) == 0:
        msg = 'No aggregates found for %s ' % hostname
        LOG.info(msg)
        abort(410, msg)

    failed = []
    deleted = []
    for aggr in aggregates:
        id = aggr['id']
        name = aggr['name']
        az = aggr['availability_zone']
        try:
            compute_client.aggregates.remove_host(id, hostname)
            deleted.append({'id': id, 'name': name, 'availability_zone': az})
        except Exception as ex:
            failed.append({
                'id': id, 'name': name,
                'availability_zone': az, 'error': str(ex)})
            LOG.error(
                'Failed to delete aggregate for %s id = %s name = %s '
                'availability_zone = %s' % (hostname, id, name, az))
            LOG.error(ex)

    if len(failed) > 0:
        return complete_with_errors_response(
            'Completed deleting aggregates with errors',
            {'failed': failed, 'deleted': deleted})

    return jsonify(deleted)


@bp.route(
    "/api/v2/compute/instances/<src_hostname>/<target_hostname>/migrate",
    methods=['PUT'])
@policy.enforce('lifecycle:update_compute')
def compute_migrate_instances(src_hostname, target_hostname):
    """Migrate instances of a compute host to another compute host

        .. :quickref: Compute; Live migrate instances of a compute host

        **Example Request**:

        .. sourcecode:: http

           PUT
           /api/v2/compute/instances/<src_hostname>/<target_hostname>/migrate
           HTTP/1.1
           Content-Type: application/json

        **Example Response**:

        .. sourcecode:: http

            HTTP/1.1 200 OK


            [{
                "id": "8279e65d-6e87-4a50-b789-96edd753fbb2",
                "name": "test3"
            }, {
                "id": "1d51f18f-27fd-4c34-a0aa-c07a5e9462e7",
                "name": "test2"
            }]
    """
    # mock for running  nova instance live migrating for a compute host
    if cfg.CONF.testing.use_mock:
        mock_json = "tools/compute-mock-data.json"
        json_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), mock_json)
        with open(json_file) as f:
            return jsonify(json.load(f)['migrate_instances'])

    compute_client = get_compute_client(request)

    search_opts = {
        'all_tenants': 1,  # all tenants
        'host': src_hostname
    }
    instances = compute_client.servers.list(search_opts=search_opts)

    if len(instances) == 0:
        msg = 'No instances found for %s' % src_hostname
        LOG.info(msg)
        abort(410, msg)

    migrating = []  # list of migrating instance ids and names
    failed = []  # list of failed instance ids, names and errors
    for inst in instances:
        id = getattr(inst, 'id')
        name = getattr(inst, 'name')
        try:
            compute_client.servers.live_migrate(
                id, target_hostname, block_migration='auto')
            migrating.append({'id': id, 'name': name})

        except Exception as ex:
            failed.append({'id': id, 'name': name, 'error': str(ex)})
            LOG.error(
                'Failed to start migrating instance of %s id = %s name = %s' %
                (src_hostname, id, name))
            LOG.error(ex)

    if len(failed) > 0:
        return complete_with_errors_response(
            'Completed migrating instances with errors',
            {'failed': failed, 'migrating': migrating})

    return jsonify(migrating)


@bp.route("/api/v2/compute/instances/<hostname>", methods=['GET'])
@policy.enforce('lifecycle:get_compute')
def compute_get_instances(hostname):
    """Return instances of a compute host

        .. :quickref: Compute; Get instances of a compute host

        **Example Request**:

        .. sourcecode:: http

           GET /api/v2/compute/instances/<hostname> HTTP/1.1
           Content-Type: application/json

        **Example Response**:

        .. sourcecode:: http

           HTTP/1.1 200 OK

            [{
                "id": "ab3622db-648b-435d-b9af-f279e57bd8c9",
                "name": "test4",
                "status": "ACTIVE"
            }]
    """
    # mock for running  nova instance list indicating whether all instances for
    # a compute host are migrated
    if cfg.CONF.testing.use_mock:
        mock_json = "tools/compute-mock-data.json"
        json_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), mock_json)
        with open(json_file) as f:
            return jsonify(json.load(f)['get_instances'])

    compute_client = get_compute_client(request)
    try:
        search_opts = {
            'all_tenants': 1,  # all tenants
            'host': hostname
        }
        instances = compute_client.servers.list(search_opts=search_opts)

        ret_instances = [
            {'id': getattr(inst, 'id'), 'name': getattr(inst, 'name'),
             'status': getattr(inst, 'status')} for inst in instances
        ]

        return jsonify(ret_instances)

    except Exception as e:
        msg = \
            'Failed to get instances for compute host %s' % hostname
        LOG.error(msg)
        LOG.error(e)
        abort(500, msg)
