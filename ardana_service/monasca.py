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

# STATUS constants for server and service status
STATUS_UP = 'up'
STATUS_DOWN = 'down'
STATUS_UNKNOWN = 'unknown'


def get_monasca_endpoint():
    """Get the keystone endpoint for Monasca

       the client in Pike won't self-discover, and
       the endpoint is used for passthru calls as well
    """

    # load the service catalog listing out of the headers inserted
    # by the keystone middleware
    service_cat = json.loads(request.headers['X-Service-Catalog'])
    for service in service_cat:
        if service['name'] == 'monasca':
            # the endpoints object is a list of size 1 with the endpoint
            # dictionary inside of it
            endpoints = service['endpoints'][0]
            return endpoints['internalURL']


def get_monasca_client():
    """Instantiates and returns an instance of the monasca python client"""

    monasca_endpoint = get_monasca_endpoint()
    # Monasca client v1.7.1 used in pike is old, so get its client via
    # old-fashioned way (credentials)
    # the pike version also cannot reliably discover its own endpoint,
    # so it is specified here
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


@bp.route("/api/v2/monasca/is_installed", methods=['GET'])
@policy.enforce('lifecycle:get_measurements')
def is_monasca_installed():
    """Checks to see if Monasca is installed on the environment

        this check can be used to evaluate whether further
        monasca calls are useful
    """
    if get_monasca_endpoint():
        return jsonify({'installed': 'true'})

    return jsonify({'installed': 'false'})


def get_parse_host_measurements_for_status(params, client):
    """Makes the query to Monasca for the specified measurement

        requires a set of parameters to define the metric and dimension
        being queried, but assumes that the metric is compatible with
        the ping_check/host_alive_status. Assumes the metric specified
        is compatible with a ping_status check (validates against
        0.0 for 'up' , 1.0 for 'down', consistent with Monasca ping checks)

        the monasca client may optionally be provided to avoid loading
        a fresh monasca client instance for each call in a loop
    """
    status = STATUS_UNKNOWN
    if not client:
        client = get_monasca_client()
    ping_measurements = client.metrics.list_measurements(**params)
    for per_host_meas in ping_measurements:
        # check if there are any valid measurements
        # and if they show the host to be up
        (time, ping_value, value_meta) = per_host_meas['measurements'][-1]
        if ping_value == 0.0:
            status = STATUS_UP
        elif ping_value == 1.0 and status == STATUS_UNKNOWN:
            # if a previous check found the host to be up,
            # don't change it to down
            status = STATUS_DOWN

    return status


@bp.route("/api/v2/monasca/server_status/<path:name>", methods=['GET'])
@policy.enforce('lifecycle:get_measurements')
def get_server_status(name):
    """Get the latest monasca host_alive_status for the specified host

    Provides the result of the most recent host_alive_status for the host .  It
    gets the last measurement in the list of measurements and uses that value
    as the status for the host. If the host does not have a status as
    a target host, then a fallback check will be made to see if the host
    observed any other hosts for ping status successfully

    .. :quickref: monasca; Get a single host status

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/monasca/server_status/host001 HTTP/1.1
       Content-Type: application/json

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK


       {
           "status": "up"
       }
    """
    if not name:
        return jsonify({})

    client = get_monasca_client()
    # get the ping measurements for the host in question
    # for the last 5 minutes
    start_time = (datetime.utcnow() - timedelta(minutes=5)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    meas_parms = {
        'name': 'host_alive_status',
        "start_time": start_time,
        'group_by': "*",
        'dimensions': {
            'test_type': 'ping',
            'hostname': name
        }
    }

    status = get_parse_host_measurements_for_status(meas_parms, client)

    # if the host didnt have direct ping checks, see if
    # it observed any other hosts, as that necessitates being
    # up as well
    meas_parms = {
        'name': 'host_alive_status',
        "start_time": start_time,
        'group_by': "*",
        'dimensions': {
            'test_type': 'ping',
            'observer_host': name
        }
    }

    if status == STATUS_UNKNOWN:
        status = get_parse_host_measurements_for_status(meas_parms, client)

    return jsonify({'status': status})


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
    monasca_endpoint = get_monasca_endpoint()
    req_url = monasca_endpoint + "/" + url

    req = requests.Request(method=request.method, url=req_url,
                           params=request.args, headers=request.headers,
                           data=request.data)

    resp = requests.Session().send(req.prepare(),
                                   verify=not CONF.keystone_authtoken.insecure)

    return (resp.text, resp.status_code, resp.headers.items())
