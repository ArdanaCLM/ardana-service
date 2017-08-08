from flask import Blueprint
from flask import jsonify
import pbr.version
import time

bp = Blueprint('admin', __name__)


@bp.route("/api/v2/version")
def version():
    version_info = pbr.version.VersionInfo('ardana-service')
    return version_info.version_string()


@bp.route("/api/v2/heartbeat")
def heartbeat():
    # return ms since epoch
    return jsonify(int(time.time()))
