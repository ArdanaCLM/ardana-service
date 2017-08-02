from flask import Blueprint
import logging

LOG = logging.getLogger(__name__)
bp = Blueprint('config_processor', __name__)


@bp.route("/api/v2/config_processor", methods=['POST'])
def run_config_processor():
    return 'Success'
