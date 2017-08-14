from flask import Blueprint
from flask import jsonify
import pbr.version
import time

bp = Blueprint('admin', __name__)


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

       GET /api/v2/heartbbeat HTTP/1.1

    **Example valid response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       1502745650

    """
    return jsonify(int(time.time()))
