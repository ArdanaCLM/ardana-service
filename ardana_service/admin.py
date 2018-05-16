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
import os
from oslo_config import cfg
import pbr.version
import pwd
import threading
import time

from . import policy

bp = Blueprint('admin', __name__)
CONF = cfg.CONF


@bp.route("/api/v2/version")
def version():
    """Returns the version of the service

    .. :quickref: Admin; Returns the version of the service

    **Example valid response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       0.0.1.dev16

    """
    version_info = pbr.version.VersionInfo('ardana-service')
    return version_info.version_string_with_vcs()


@bp.route("/api/v2/heartbeat")
def heartbeat():
    """Returns the epoch time

    Simple API to verify that the service is up and responding.  Returns
    the number of seconds since 1970-01-01 00:00:00 GMT.

    .. :quickref: Admin; Returns the epoch time

    **Example valid response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       1502745650

    """
    return jsonify(int(time.time()))


@bp.route("/api/v2/user")
@policy.enforce('lifecycle:get_user')
def user():
    """Returns the username the service is running under

    .. :quickref: Admin; Returns the username the service is running under

    **Example valid response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       {"username": "myusername"}

    """
    user_dict = {'username': pwd.getpwuid(os.getuid()).pw_name}
    return jsonify(user_dict)


def update_trigger_file():
    trigger_file = os.path.join(CONF.paths.log_dir, 'trigger.txt')
    with open(trigger_file, 'w') as f:
        f.write("Triggered restart at %s\n" % time.asctime())


@bp.route("/api/v2/restart", methods=['POST'])
@policy.enforce('lifecycle:restart')
def restart():
    """Requests the service to restart after a specified delay, in seconds

    .. :quickref: Admin; Requests a service restart after a delay

    **Example Request**:

    .. sourcecode:: http

       POST /api/v2/user HTTP/1.1

       Content-Type: application/json

       {
          "delay": 60
       }
    """
    info = request.get_json() or {}
    delay_secs = int(info.get('delay', 0))

    t = threading.Timer(delay_secs, update_trigger_file)
    t.start()

    return 'Success'
