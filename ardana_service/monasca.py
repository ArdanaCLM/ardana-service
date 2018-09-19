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

from . import keystone
from . import policy
from datetime import datetime
from datetime import timedelta
from flask import abort
from flask import Blueprint
from flask import jsonify
from flask import request
import json
from monascaclient.client import Client as Mon_client
from oslo_config import cfg
from oslo_log import log as logging
import requests

LOG = logging.getLogger(__name__)
bp = Blueprint('monasca', __name__)
CONF = cfg.CONF
mon_client = None
monasca_endpoint = None


def get_monasca_client():
    global mon_client
    global monasca_endpoint
    if mon_client:
        return mon_client

    # Figure out the monasca-internal endpoint
    service_list = json.loads(keystone.get_endpoints().data)
    for service in service_list:
        if service['name'] == 'monasca':
            eps = service['endpoints']
            for ep in eps:
                if ep['interface'] == 'internal':
                    monasca_endpoint = ep['url']
    if not monasca_endpoint:
        raise Exception("Unable to locate monasca internal endpoint")

    # Monasca client v1.7.1 used in pike is old, so get its client via
    # old-fashioned way (credentials)
    mon_client = Mon_client(
        api_version="2_0",
        endpoint=monasca_endpoint,
        auth_url=CONF.keystone_authtoken.auth_url,
        username=CONF.keystone_authtoken.username,
        password=CONF.keystone_authtoken.password,
        project_name=CONF.keystone_authtoken.project_name,
        project_domain_name=CONF.keystone_authtoken.project_domain_name,
        user_domain_name=CONF.keystone_authtoken.user_domain_name,
        insecure=CONF.keystone_authtoken.insecure
    )
    return mon_client


@bp.route("/api/v2/monasca/service_status", methods=['GET'])
@policy.enforce('lifecycle:get_measurements')
def get_service_statuses():
    """Get the latest monasca http_statuses for all available services

    Provides a list of monasca services that have the http_status metric.  It
    gets the last measurement in the list of measurements and uses that value
    as the status for the service.

    .. :quickref: monasca; Get a list of service statuses

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/monasca/service_status HTTP/1.1
       Content-Type: application/json

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       [
           {
               "name": "ardana",
               "status": "up"
           },
           {
               "name": "backup",
               "status": "down"
           },
           {
               "name": "block-storage",
               "status": "unknown"
           },
           ... <and so on>
       ]
    """

    # We'll collect the statuses for the service in a list.
    # Note: increasing the "minutes" value will reduce the chances of an
    #       getting no status, but also potentially might give a late result
    client = get_monasca_client()
    parms = {
        "name": "http_status",
        "start_time":
            (datetime.utcnow() - timedelta(minutes=1)).isoformat(),
        "group_by": "service"
    }

    measurements = None
    try:
        measurements = client.metrics.list_measurements(**parms)
        if not measurements:
            LOG.error("Empty measurements from Monasca")
            abort(404, "Unable to retrieve any statuses")
    except Exception as e:
        LOG.error("Unable to access Monasca: %s" % e)
        abort(503, "Monasca service unavailable")

    statuses = []
    for m in measurements:
        service = m['dimensions']['service']
        # we get the last measurement value, which is also the latest
        val_idx = m['columns'].index('value')
        if not m['measurements']:
            status = "unknown"
        else:
            value = m['measurements'][-1][val_idx]
            if value == 0:
                status = "up"
            else:
                status = "down"
        statuses.append({
            'name': service,
            'status': status
        })

    return jsonify(statuses)


@bp.route("/api/v2/monasca/passthru/<path:url>",
          methods=['GET', 'POST', 'PUT', 'DELETE'])
@policy.enforce('lifecycle:get_measurements')
def passthru(url):
    """Passes thru the request directly to monasca

    .. :quickref: monasca; passthru endpoint to monasca

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/monasca/passthru/alarms/count HTTP/1.1
    """
    # populate monasca_endpoint in case it has not yet been populated
    get_monasca_client()
    global monasca_endpoint
    req_url = monasca_endpoint + "/" + url

    req = requests.Request(method=request.method, url=req_url,
                           params=request.args, headers=request.headers,
                           data=request.data)

    resp = requests.Session().send(req.prepare(),
                                   verify=not CONF.keystone_authtoken.insecure)

    return (resp.text, resp.status_code, resp.headers.items())
