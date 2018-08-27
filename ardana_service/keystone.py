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

from flask import Blueprint
from flask import jsonify
from flask import request
from keystoneauth1 import session
from keystoneclient.v3 import client
import logging
from oslo_config import cfg

from . import policy

bp = Blueprint('keystone', __name__)
CONF = cfg.CONF
LOG = logging.getLogger(__name__)


@bp.route("/api/v2/endpoints", methods=['GET'])
@policy.enforce('lifecycle:get_endpoints')
def get_endpoints():
    """Returns the endpoint list from keystone.

    .. :quickref: Admin; Get endpoint list

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/endpoints HTTP/1.1

       Content-Type: application/json

       {
          "endpoints": [
            {
               'name': 'keystone',
               'type': 'identity',
               'description': 'OpenStack Identity',
               'enabled': true,
               'endpoints': [
                   {
                    'interface': 'admin',
                     'region': 'region1',
                     'url': 'http://localhost:35357/v3'
                   },
                   {
                    'interface': 'public',
                     'region': 'region1',
                     'url': 'http://localhost:5000/v3'
                   },
                   {
                    'interface': 'internal',
                     'region': 'region1',
                     'url': 'http://localhost:5000/v3'
                   }
                ]
            }
          ]
       }
    """
    # Obtain a keystone session using the auth plugin injected by the keystone
    # middleware
    sess = session.Session(auth=request.environ['keystone.token_auth'],
                           verify=not CONF.keystone_authtoken.insecure)
    keystone = client.Client(session=sess)
    endpoints = keystone.endpoints.list()
    services = keystone.services.list()

    results = []
    for service in services:

        # Populate item with several fields of interest from the service
        item = {
            'name': service.name,
            'type': service.type,
            'enabled': service.enabled,
            'description': getattr(service, 'description', '')
        }

        # Add list of endpoints for this service
        item['endpoints'] = \
            [{'interface': e.interface,
              'region': e.region,
              'url': e.url}
             for e in endpoints if e.service_id == service.id]

        results.append(item)

    return jsonify(results)
