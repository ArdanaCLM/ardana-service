from flask import Blueprint
from flask import jsonify
from flask import request
import os
from oslo_config import cfg
import pbr.version
import pwd
import threading
import time

bp = Blueprint('admin', __name__)
CONF = cfg.CONF


@bp.route("/api/v2/version")
def version():
    """Returns the epoch time

    Simple API to return the version of the service.

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/version HTTP/1.1

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
    the number of seconds since 1970-01-01 00:00:00 GMT

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/heartbeat HTTP/1.1

    **Example valid response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       1502745650

    """
    return jsonify(int(time.time()))


@bp.route("/api/v2/user")
def user():
    """Returns the username the service is running under

    Simple API to return the username the service is running under

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/user HTTP/1.1

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
def restart():
    """Requests the service to restart after a specified delay, in seconds

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
