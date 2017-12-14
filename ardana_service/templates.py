from flask import abort
from flask import Blueprint
from flask import jsonify
import logging
import model
import os
from oslo_config import cfg


LOG = logging.getLogger(__name__)
bp = Blueprint('templates', __name__)
CONF = cfg.CONF


@bp.route("/api/v2/templates")
def get_all_templates():
    """Returns all available input model templates, aka examples

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/templates HTTP/1.1

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json

       [
         {
           "name": "entry-scale-esx-kvm-vsa",
           "href": "/api/v2/templates/entry-scale-esx-kvm-vsa",
           "overview": "...",
           "metadata": {"nodeCount": 30, "hypervisor": ["esx", "kvm"],
               "storage": "vsa"}
         },
         {
           "name": "entry-scale-ironic-flat-network",
           "href": "/api/v2/templates/entry-scale-ironic-flat-network",
           "overview": "...",
           "metadata": {"nodeCount": 30, "hypervisor": ["ironic"],
                "network": "flat"}
         },
         {
           "name": "mid-scale-kvm-vsa",
           "href": "/api/v2/templates/mid-scale-kvm-vsa",
           "overview": "...",
           "metadata": {"nodeCount": 200, "hypervisor": ["kvm"],
                "storage": "vsa"}
         },
         "..."
       ]
    """

    metadata_table = {
        'entry-scale-esx-kvm-vsa': {
            'nodeCount': 30, 'hypervisor': ['esx', 'kvm'], 'storage': 'vsa'
        },
        'entry-scale-ironic-flat-network': {
            'nodeCount': 30, 'hypervisor': ['ironic'], 'network': 'flat'
        },
        'entry-scale-ironic-multi-tenancy': {
            'nodeCount': 30, 'hypervisor': ['ironic'], 'network':
                'multi-tenant'
        },
        'entry-scale-kvm-ceph': {
            'nodeCount': 30, 'hypervisor': ['kvm'], 'storage': 'ceph'
        },
        'entry-scale-kvm-esx-vsa-mml': {
            'nodeCount': 30, 'hypervisor': ['esx', 'kvm'], 'storage': 'vsa'
        },
        'entry-scale-kvm-vsa': {
            'nodeCount': 30, 'hypervisor': ['kvm'], 'storage': 'vsa'
        },
        'entry-scale-kvm-vsa-mml': {
            'nodeCount': 30, 'hypervisor': ['kvm'], 'storage': 'vsa'
        },
        'entry-scale-swift': {
            'nodeCount': 30, 'hypervisor': [], 'storage': 'swift'
        },
        'mid-scale-kvm-vsa': {
            'nodeCount': 200, 'hypervisor': ['kvm'], 'storage': 'vsa'
        }
    }

    templates = []
    for name in os.listdir(CONF.paths.templates_dir):

        readme = os.path.join(CONF.paths.templates_dir, name, "README.html")
        try:
            with open(readme) as f:
                lines = f.readlines()
            overview = ''.join(lines)
            metadata = metadata_table[name] if name in metadata_table else ''

            templates.append({
                'name': name,
                'href': '/'.join(('/api/v2/templates', name)),
                'overview': overview,
                'metadata': metadata
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

    **Example Response**:

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

    model_dir = os.path.join(CONF.paths.templates_dir, name)
    try:
        return jsonify(model.read_model(model_dir))
    except Exception as e:
        LOG.exception(e)
        abort(400, "Unable to read model")
