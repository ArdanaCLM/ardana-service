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
from keystoneauth1 import loading
from keystoneauth1 import session
from neutronclient.v2_0 import client as neutronClient
from oslo_config import cfg
from oslo_log import log as logging

LOG = logging.getLogger(__name__)
bp = Blueprint('network', __name__)
CONF = cfg.CONF


def get_network_client(req):

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
        network_client = neutronClient.Client(session=sess)
        return network_client

    except Exception as e:
        LOG.error(e)
        abort(500, 'Failed to get network neutronclient')


def complete_with_errors_response(msg, contents):
    response = jsonify({'error_msg': msg, 'contents': contents})
    response.status_code = 500
    return response


@bp.route("/api/v2/network/agents/<hostname>/disable", methods=['PUT'])
@policy.enforce('lifecycle:update_network')
def network_disable_agents(hostname):
    """Disable network agents of a host

        .. :quickref: Compute; Disable network agents of a host

        **Example Request**:

        .. sourcecode:: http

           PUT /api/v2/network/agents/<hostname>/disable HTTP/1.1
           Content-Type: application/json

        **Example Response**:

        .. sourcecode:: http

            HTTP/1.1 200 OK

            [{
                "id": "60afd9e9-e2bf-4bf0-91ab-52187064206a",
                "type": "Metadata agent"
            }, {
                "id": "972001b9-e402-42e6-88af-1713f7854599",
                "type": "L3 agent"
            }, {
                "id": "bb59153e-e2e7-4dd4-ba04-0488a24bfd78",
                "type": "Open vSwitch agent"
            }, {
                "id": "c2ddc4f0-6917-4a6f-9d79-5cf91d94240d",
                "type": "Loadbalancerv2 agent"
            }]
    """

    network_client = get_network_client(request)

    response = network_client.list_agents(host=hostname)

    if len(response['agents']) == 0:
        msg = 'Unable to find network agents for %s' % hostname
        LOG.error(msg)
        abort(404, msg)

    failed = []
    disabled = []
    for agent in response['agents']:
        id = agent['id']
        agent_type = agent['agent_type']
        body = {'agent': {'admin_state_up': False}}
        try:
            network_client.update_agent(id, body)
            disabled.append({'id': id, 'type': agent_type})

        except Exception as ex:
            failed.append({
                'id': id, 'type': agent_type, 'error': str(ex)})
            LOG.error(
                'Failed to disable network agent for %s id = %s type = %s'
                % (hostname, id, agent_type))
            LOG.error(ex)

    if len(failed) > 0:
        return complete_with_errors_response(
            'Completed disabling network agents with errors',
            {'failed': failed, 'disabled': disabled})

    return jsonify(disabled)


@bp.route("/api/v2/network/agents/<hostname>", methods=['DELETE'])
@policy.enforce('lifecycle:update_network')
def network_delete_agents(hostname):
    """Delete network agents of a host

        .. :quickref: Compute; Delete network agents of a host

        **Example Request**:

        .. sourcecode:: http

           DELETE /api/v2/network/agents/<hostname> HTTP/1.1
           Content-Type: application/json

        **Example Response**:

        .. sourcecode:: http

            HTTP/1.1 200 OK

            [{
                "id": "60afd9e9-e2bf-4bf0-91ab-52187064206a",
                "type": "Metadata agent"
            }, {
                "id": "972001b9-e402-42e6-88af-1713f7854599",
                "type": "L3 agent"
            }, {
                "id": "bb59153e-e2e7-4dd4-ba04-0488a24bfd78",
                "type": "Open vSwitch agent"
            }, {
                "id": "c2ddc4f0-6917-4a6f-9d79-5cf91d94240d",
                "type": "Loadbalancerv2 agent"
            }]
    """
    network_client = get_network_client(request)

    response = network_client.list_agents(host=hostname)

    if len(response['agents']) == 0:
        msg = 'Unable to find network agents for %s' % hostname
        LOG.error(msg)
        abort(404, msg)

    failed = []
    deleted = []
    for agent in response['agents']:
        id = agent['id']
        agent_type = agent['agent_type']
        try:
            network_client.delete_agent(id)
            deleted.append({'id': id, 'type': agent_type})

        except Exception as ex:
            failed.append({
                'id': id, 'type': agent_type, 'error': str(ex)})
            LOG.error(
                'Failed to delete network agent for %s id = %s type = %s'
                % (hostname, id, agent_type))
            LOG.error(ex)

    if len(failed) > 0:
        return complete_with_errors_response(
            'Completed deleting network agents with errors',
            {'failed': failed, 'deleted': deleted})

    return jsonify(deleted)


@bp.route("/api/v2/network/agents/<hostname>", methods=['GET'])
@policy.enforce('lifecycle:get_network')
def network_get_agents(hostname):
    """Return network agents of a host

        .. :quickref: Network; Get network agents of a host

        **Example Request**:

        .. sourcecode:: http

           GET /api/v2/compute/instances/<hostname> HTTP/1.1
           Content-Type: application/json

        **Example Response**:

        .. sourcecode:: http

            HTTP/1.1 200 OK

            [{
                "admin_state_up": true,
                "agent_type": "Metadata agent",
                "alive": true,
                "id": "60afd9e9-e2bf-4bf0-91ab-52187064206a"
            }, {
                "admin_state_up": true,
                "agent_type": "L3 agent",
                "alive": true,
                "id": "972001b9-e402-42e6-88af-1713f7854599"
            }, {
                "admin_state_up": true,
                "agent_type": "Open vSwitch agent",
                "alive": true,
                "id": "bb59153e-e2e7-4dd4-ba04-0488a24bfd78"
            }, {
                "admin_state_up": true,
                "agent_type": "Loadbalancerv2 agent",
                "alive": true,
                "id": "c2ddc4f0-6917-4a6f-9d79-5cf91d94240d"
            }]
    """
    network_client = get_network_client(request)
    try:
        response = network_client.list_agents(host=hostname)
        ret_agents = [{
            'id': agent['id'], 'alive': agent['alive'],
            'agent_type': agent['agent_type'],
            'admin_state_up': agent['admin_state_up']
        } for agent in response['agents']]

        return jsonify(ret_agents)

    except Exception as e:
        msg = \
            'Failed to get network agents for %s ' % hostname
        LOG.error(msg)
        LOG.error(e)
        abort(500, msg)
