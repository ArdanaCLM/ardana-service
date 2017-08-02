from flask import Blueprint
import logging

LOG = logging.getLogger(__name__)
bp = Blueprint('cp_output', __name__)


@bp.route("/api/v2/model/cp_output/<path>", methods=['GET'])
def get_cp_output(path):
    return 'Success'
