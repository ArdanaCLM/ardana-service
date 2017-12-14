import collections
from flask import abort
from flask import Blueprint
from flask import jsonify
from flask import request
import logging
import os
from oslo_config import cfg

LOG = logging.getLogger(__name__)
bp = Blueprint('service', __name__)
CONF = cfg.CONF


@bp.route("/api/v2/service/files", methods=['GET'])
def get_all_files():

    service_list = collections.defaultdict(list)
    for root, dirs, files in os.walk(CONF.paths.config_dir, followlinks=True):
        if root == CONF.paths.config_dir:
            continue
        for file in files:
            if file.endswith('.j2'):
                relname = os.path.relpath(os.path.join(root, file),
                                          CONF.paths.config_dir)
                (service, file_path) = relname.split('/', 1)
                service_list[service].append(file_path)
    result = [{'service': svc, 'files': files}
              for svc, files in service_list.items()]
    return jsonify(result)


@bp.route("/api/v2/service/files/<path:name>", methods=['GET', 'POST'])
def service_file(name):

    if request.method == 'GET':
        filename = os.path.join(CONF.paths.config_dir, name)
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

        filename = os.path.join(CONF.paths.config_dir, name)
        try:
            with open(filename, "w") as f:
                f.write(data)
            return 'Success'
        except Exception as e:
            LOG.exception(e)
            abort(400)
