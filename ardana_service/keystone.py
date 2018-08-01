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
import logging
from oslo_config import cfg

from . import policy

bp = Blueprint('keystone', __name__)
CONF = cfg.CONF
LOG = logging.getLogger(__name__)


@bp.route("/api/v2/endpoints", methods=['GET'])
@policy.enforce('lifecycle:get_endpoints')
def get_endpoints():
    """Requests the endpoint list from keystone.

    .. :quickref: Admin; Requests endpoint list

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
               'region': 'region1',
               'endpoints': [
                   {'interface': 'admin', 'url': 'http://localhost:35357/v3'},
                   {'interface': 'public', 'url': 'http://localhost:5000/v3'},
                   {'interface': 'internal', 'url': 'http://localhost:5000/v3'}
                ]
            }
          ]
          "delay": 60
       }
    """
    # Obtain a keyston session using the auth plugin injected by the keystone
    # middleware
    sess = session.Session(auth=request.environ['keystone.token_auth'])

    resp = sess.get('/services', endpoint_filter={'service_type': 'identity'})
    services = resp.json()['services']

    resp = sess.get('/endpoints', endpoint_filter={'service_type': 'identity'})
    endpoints = resp.json()['endpoints']

    results = []
    for service in services:

        # Populate item with several fields of interest from the service
        want = ('name', 'type', 'enabled', 'description', 'region')
        item = dict([(k, v) for k, v in service.items() if k in want])

        # Add list of endpoints for this service
        item['urls'] = \
            [{'interface': e['interface'],
              'region': e['region'],
              'url': e['url']}
             for e in endpoints if e['service_id'] == service['id']]

        results.append(item)

    return jsonify(results)
