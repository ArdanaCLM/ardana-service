from flask import Blueprint
from flask import jsonify
import logging

LOG = logging.getLogger(__name__)

bp = Blueprint('versions', __name__)


@bp.route("/api/v2/model/state", methods=['GET'])
def get_encrypted():
    return jsonify({"isEncrypted": False})


@bp.route("/api/v2/model/changes", methods=['GET', 'DELETE'])
def changes():
    return 'Success'


@bp.route("/api/v2/model/history", methods=['GET'])
def history():
    return 'Success'


@bp.route("/api/v2/model/commit", methods=['POST'])
def commit():
    return 'Success'
