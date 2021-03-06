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
from flask import abort
from flask import Blueprint
from flask import jsonify
from flask import request
import json
import requests
from util import url_address, ping

from . import policy

bp = Blueprint('oneview', __name__)

"""
Calls to HPE OneView
"""


@bp.route("/api/v2/ov/connection_test", methods=['POST'])
@policy.enforce('lifecycle:update_server')
def connection_test():
    creds = request.get_json() or {}
    host = creds['host']
    try:
        ping(host, 443)
    except Exception as e:
        return jsonify(error=str(e)), 404

    verify = True
    secured = request.headers.get('Secured')
    if secured == 'false':
        verify = False
    try:
        url = "https://" + url_address(host) + "/rest/login-sessions"
        headers = {'X-Api-Version': '200', 'Content-Type': 'application/json'}
        data = {'userName': creds['username'], 'password': creds['password']}
        response = requests.post(url, data=json.dumps(data), headers=headers,
                                 verify=verify)
    except Exception as e:
        if 'SSLError' in str(e):
            return jsonify(error=str(e)), 403
        else:
            return jsonify(error=str(e)), 401

    if not response.status_code == 200:
        return jsonify(error=response.json()['message']), 400

    return jsonify(response.json())


@bp.route("/api/v2/ov/servers")
@policy.enforce('lifecycle:get_server')
def ov_server_list():
    verify = True
    secured = request.headers.get('Secured')
    if secured == 'false':
        verify = False

    key = request.headers.get('Auth-Token')
    url = request.headers.get('Ov-Url')
    try:
        request_url = url + \
            '/rest/server-hardware?start=0&count=-1&sort=position:desc'
        head = {'Auth': key, 'X-Api-Version': '200'}
        response = requests.get(request_url, headers=head, verify=verify)
        return jsonify(response.json())
    except Exception:
        abort(400)


@bp.route("/api/v2/ov/servers/<id>")
@policy.enforce('lifecycle:get_server')
def ov_server_details(id):
    verify = True
    secured = request.headers.get('Secured')
    if secured == 'false':
        verify = False

    key = request.headers.get('Auth-Token')
    url = request.headers.get('Ov-Url')
    try:
        request_url = url + '/rest/server-hardware/' + id
        head = {'Auth': key, 'X-Api-Version': '200'}
        response = requests.get(request_url, headers=head, verify=verify)
        return jsonify(response.json())
    except Exception:
        abort(400)
