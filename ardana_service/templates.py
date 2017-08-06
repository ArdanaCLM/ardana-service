from flask import abort
from flask import Blueprint
from flask import jsonify
import logging
import model
import os

from . import config

LOG = logging.getLogger(__name__)
bp = Blueprint('templates', __name__)
TEMPLATES_DIR = config.get_dir("templates_dir")


@bp.route("/api/v2/templates")
def get_all_templates():
    """Returns all available input model templates, aka examples

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/templates HTTP/1.1

    **Example Reponse**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json

       [
         {
           "name": "entry-scale-esx-kvm-vsa",
           "href": "/api/v2/templates/entry-scale-esx-kvm-vsa",
           "overview": "..."
         },
         {
           "name": "entry-scale-ironic-flat-network",
           "href": "/api/v2/templates/entry-scale-ironic-flat-network",
           "overview": "..."
         },
         "..."
       ]
    """

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
    """Returns a particular template by name

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/entry-scale-kvm-vsa HTTP/1.1

    **Example Reponse**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       {
         "name": "entry-scale-kvm-vsa",
         "version": 2,
         "readme": {
           "html": "..."
         },
         "fileInfo": {"..."},
         "inputModel": {
           "cloud": {
             "name": "entry-scale-kvm-vsa",
             "hostname-data": {
               "host-prefix": "helion",
               "member-prefix": "-m"
             },
            },
           "control-planes": [{
             "name": "control-plane-1",
             "control-plane-prefix": "cp1",
             "region-name": "region1",
             "failure-zones": "...",
             "configuration-data": [
               "OCTAVIA-CONFIG-CP1",
               "NEUTRON-CONFIG-CP1"
             ],
             "common-service-components": [
               "logging-producer",
               "monasca-agent",
               "freezer-agent",
               "stunnel",
               "lifecycle-manager-target"
             ],
             "clusters": [],
             "..."
           }],
          }
       }
    """

    model_dir = os.path.join(TEMPLATES_DIR, name)
    try:
        return jsonify(model.read_model(model_dir))
    except Exception as e:
        LOG.exception(e)
        abort(500)
