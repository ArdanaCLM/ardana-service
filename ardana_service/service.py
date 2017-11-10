from flask import abort
from flask import Blueprint
from flask import jsonify
from flask import request
import logging
import os
import collections

from . import config

LOG = logging.getLogger(__name__)
CONFIG_DIR = config.get_dir("config_dir")

bp = Blueprint('service', __name__)

@bp.route("/api/v2/service/files", methods=['GET'])
def get_all_files():

    service_list = collections.defaultdict(list)
    for root, dirs, files in os.walk(CONFIG_DIR):
        if root == CONFIG_DIR:
            continue
        for file in files:
            if file.endswith('.j2'):
                relname = os.path.relpath(os.path.join(root, file), CONFIG_DIR)
                (service, file_path) = relname.split('/', 1)
                service_list[service].append(file_path)
    result = [
        {'service': service, 'files': files} for service, files in service_list.items()]
    return jsonify(result)


@bp.route("/api/v2/service/files/<path:name>", methods=['GET', 'POST'])
def service_file(name):

    if request.method == 'GET':
        filename = os.path.join(CONFIG_DIR, name)
        contents = ''
        try:
            with open(filename) as f:
                lines = f.readlines()
            contents = contents.join(lines)

        except IOError as e:
            LOG.exception(e)
            abort(400)

        return jsonify(contents)
    else:
        data = request.get_json()

        filename = os.path.join(CONFIG_DIR, name)
        try:
            with open(filename, "w") as f:
                f.write(data)
            return 'Success'
        except Exception as e:
            LOG.exception(e)
            abort(400)