# (c) Copyright 2017-2019 SUSE LLC
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
from oslo_config import cfg
import re
import subprocess
from tinydb import Query
from tinydb import TinyDB

from . import model
from . import policy
from . import util

bp = Blueprint('ui', __name__)
SUCCESS = {"success": True}
CONF = cfg.CONF


"""
Calls handled locally to support the UI
"""


@bp.route("/api/v2/progress", methods=['GET'])
@policy.enforce('lifecycle:get_server')
def get_progress():

    contents = ''
    try:
        with open(CONF.progress_file) as f:
            contents = json.load(f)

    except IOError:
        pass

    return jsonify(contents)


@bp.route("/api/v2/progress", methods=['POST'])
@policy.enforce('lifecycle:update_server')
def save_progress():

    data = request.get_json()

    try:
        with open(CONF.progress_file, "w") as f:
            json.dump(data, f)
        return jsonify(SUCCESS)
    except Exception:
        abort(400)


# /server CRUD operations
@bp.route("/api/v2/server", methods=['POST'])
@policy.enforce('lifecycle:update_server')
def insert_servers():
    """Inserts a list of servers to the server table.

    'uid' and 'source' fields must be unique

    **Example Request**:

    .. sourcecode:: http

    POST /api/v2/server HTTP/1.1
         where the body contains a list of server dictionaries
    """
    db = TinyDB(CONF.db_file)
    server_table = db.table('servers')
    server = Query()
    try:
        data = request.get_json()

        # Check for dupes and missing uid & server keys
        for entry in data:
            if not set(['id', 'uid', 'source']).issubset(entry):
                return jsonify(error="There is one or more entries missing "
                                     "id , uid or source"), 400
            sid = entry['uid']
            src = entry['source']
            if not set(src.split(',')).issubset(['sm', 'ov', 'manual']):
                return jsonify(error="source=%s for uid=%s is "
                                     "invalid" % (src, sid)), 400
            server_entries = server_table.search(
                (server.uid == sid) & (server.source == src))
            if server_entries:
                return jsonify(error="There is an entry already matching "
                                     "uid=%s and server=%s" % (sid, src)), 400

        server_table.insert_multiple(server for server in data)
        return jsonify(SUCCESS)
    except Exception:
        abort(400)


@bp.route("/api/v2/server", methods=['GET'])
@policy.enforce('lifecycle:get_server')
def get_servers():
    """Returns a list of server(s) given a list of 'source'

    'source' is a comma-delimited list joined by an OR statement

    **Example Request**:

    .. sourcecode:: http

    GET /api/v2/server?source=src1,src2 HTTP/1.1
    """
    db = TinyDB(CONF.db_file)
    server_table = db.table('servers')
    try:
        src = request.args.get('source', None)
        if not src:
            return jsonify(server_table.all())
        results = server_table.search(create_query(src))
        return jsonify(results)
    except Exception:
        abort(400)


@bp.route("/api/v2/server", methods=['PUT'])
@policy.enforce('lifecycle:update_server')
def update_server():
    """Update a single server entry (dict) into the server table.

    'id' and 'source' fields must be unique

    **Example Request**:

    .. sourcecode:: http

    PUT /api/v2/server HTTP/1.1
         where the body contains a dictionary containing a server's details
    """
    db = TinyDB(CONF.db_file)
    server_table = db.table('servers')
    server = Query()
    try:
        entry = request.get_json()
        if not set(['uid', 'source']).issubset(entry):
            return jsonify(error="There is one or more entries missing "
                                 "uid or source"), 400
        sid = entry['uid']
        src = entry['source']
        if not set(src.split(',')).issubset(['sm', 'ov', 'manual']):
            return jsonify(error="source=%s for uid=%s is "
                                 "invalid" % (src, sid)), 400
        server_entries = server_table.search(
            (server.uid == sid) & (server.source == src))
        if not server_entries:
            return jsonify(error="uid:%s; source:%s not found "
                                 "to be updated" % (sid, src)), 404
        server_table.remove(
            (server.uid == sid) & (server.source == src))
        server_table.insert(entry)
        return jsonify(SUCCESS)
    except Exception:
        abort(400)


@bp.route("/api/v2/server", methods=['DELETE'])
@policy.enforce('lifecycle:update_server')
def delete_server():
    """Removes servers given a set of search parameters.

    The search parameters used are the same as get_servers()

    **Example Request**:

    .. sourcecode:: http

    DELETE /api/v2/server?source=src1,src2&uid=1234 HTTP/1.1
    """
    db = TinyDB(CONF.db_file)
    server_table = db.table('servers')
    try:
        src = request.args.get('source', None)
        uid = request.args.get('uid', None)
        if not src:
            return jsonify(error="source must be specified"), 400
        server_table.remove(create_query(src, uid))
        return jsonify(SUCCESS)
    except Exception:
        abort(400)


def create_query(src, uid=None):
    q = Query()

    if uid:
        return (q.uid == uid)
    if src:
        if not set(src.split(',')).issubset(['sm', 'ov', 'manual']):
            return jsonify(error="specified sources are invalid"), 400

        query = None
        for source in src.split(','):
            if query is None:
                query = (q.source == source)
            else:
                query |= (q.source == source)

        return query


@bp.route("/api/v2/ips", methods=['GET'])
@policy.enforce('lifecycle:get_endpoints')
def get_ips():
    """Returns list of ip addresses of the local host

    **Example Request**:

    .. sourcecode:: http

    GET /api/v2/ips HTTP/1.1

    **Example Response**:

    .. sourcecode:: http
    HTTP/1.1 200 OK

    [
        "127.0.0.1",
        "192.168.1.200"
    ]
    """

    ips = []
    pattern = re.compile(r'inet +([0-9.]+)')

    try:
        lines = subprocess.check_output(["ip", "-o", "-4", "addr", "show"],
                                        universal_newlines=True)
        for line in lines.split('\n'):
            match = pattern.search(line)
            if match:
                ips.append(match.group(1))

    except subprocess.CalledProcessError:
        pass

    return jsonify(ips)


def _read_url(name, internal_model):
    control_planes = util.find('internal.control-planes', internal_model)
    for _, control_plane in control_planes.items():
        if name in control_plane['advertises'].keys():
            url = util.find('advertises.%s.public.url' % (name), control_plane)
            if 'myardana.test' in url:
                url = util.find(
                    'advertises.%s.admin.url' % (name),
                    control_plane
                )
            return url


@bp.route("/api/v2/external_urls", methods=['GET'])
@policy.enforce('lifecycle:get_endpoints')
def get_external_urls():
    """Returns list of external URLs

    Returns the list of external URLs that the customer can access via the
    browser once cloud deployment is complete

    **Example Request**:

    .. sourcecode:: http

    GET /api/v2/external_urls HTTP/1.1

    **Example Response**:

    .. sourcecode:: http
    HTTP/1.1 200 OK

    {
        "horizon": "https://192.168.245.6:443",
        "opsconsole": "https://192.168.245.5:9095",
        "ardana-service": "https://192.168.245.5:9085"
    }
    """
    internal_model = model.read_cp_internal_json('CloudModel.yaml')

    result = {
        'opsconsole': _read_url('ops-console-web', internal_model),
        'horizon': _read_url('horizon', internal_model),
        'ardana-service': _read_url('ardana-service', internal_model)
    }

    return jsonify(result)
