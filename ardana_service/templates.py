import config.config as config
from flask import abort
from flask import Blueprint
from flask import jsonify
import logging
import model
import os

LOG = logging.getLogger(__name__)
bp = Blueprint('templates', __name__)
TEMPLATES_DIR = config.get_dir("templates_dir")


@bp.route("/api/v2/templates")
def get_all_templates():

    templates = []
    for name in os.listdir(TEMPLATES_DIR):

        readme = os.path.join(TEMPLATES_DIR, name, "README.html")
        try:
            with open(readme) as f:
                lines = f.readlines()
            overview = ''.join(lines)

            templates.append({
                'name': name,
                'href': '/'.join(('/api/v2/templates', name)),
                'overview': overview
            })

        except IOError:
            pass

    return jsonify(sorted(templates))


@bp.route("/api/v2/templates/<name>")
def get_template(name):

    model_dir = os.path.join(TEMPLATES_DIR, name)
    try:
        return jsonify(model.read_model(model_dir))
    except Exception as e:
        LOG.exception(e)
        abort(500)
