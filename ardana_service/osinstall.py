from flask import Blueprint
from oslo_log import log as logging

LOG = logging.getLogger(__name__)
bp = Blueprint('osinstall', __name__)


@bp.route("/api/v2/osinstall", methods=['POST'])
def start_os_install():
    return 'OS Install initiated', 201


@bp.route("/api/v2/osinstall", methods=['GET'])
def get_os_install_status():
    return 'Success'
