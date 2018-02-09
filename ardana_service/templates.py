# (c) Copyright 2017-2018 SUSE LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from flask import abort
from flask import Blueprint
from flask import jsonify
import model
import os
from oslo_config import cfg
from oslo_log import log as logging


LOG = logging.getLogger(__name__)
bp = Blueprint('templates', __name__)
CONF = cfg.CONF


@bp.route("/api/v2/templates")
def get_all_templates():
    """Returns all available input model templates, aka examples

    .. :quickref: Templates; Return list of available input model templates

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json

       [
         {
           "name": "entry-scale-kvm-esx-ses",
           "href": "/api/v2/templates/entry-scale-kvm-esx-ses",
           "overview": "...",
           "metadata": {"nodeCount": 30, "hypervisor": ["esx", "kvm"],
               "storage": "ses"}
         },
         {
           "name": "entry-scale-ironic-flat-network",
           "href": "/api/v2/templates/entry-scale-ironic-flat-network",
           "overview": "...",
           "metadata": {"nodeCount": 30, "hypervisor": ["ironic"],
                "network": "flat"}
         },
         {
           "name": "mid-scale-kvm-ses",
           "href": "/api/v2/templates/mid-scale-kvm-ses",
           "overview": "...",
           "metadata": {"nodeCount": 200, "hypervisor": ["kvm"],
                "storage": "ses"}
         },
         "..."
       ]
    """

    metadata_table = {
        'entry-scale-kvm-ses': {
            'nodeCount': 30, 'hypervisor': ['kvm'], 'storage': 'ses'
        },
        'entry-scale-kvm-esx-ses': {
            'nodeCount': 30, 'hypervisor': ['esx', 'kvm'], 'storage': 'ses'
        },
        'entry-scale-kvm-esx-ses-mml': {
            'nodeCount': 30, 'hypervisor': ['esx', 'kvm'], 'storage': 'ses'
        },
        'entry-scale-kvm-ses-mml': {
            'nodeCount': 30, 'hypervisor': ['kvm'], 'storage': 'ses'
        },
        'entry-scale-ironic-flat-network': {
            'nodeCount': 30, 'hypervisor': ['ironic'], 'network': 'flat'
        },
        'entry-scale-ironic-multi-tenancy': {
            'nodeCount': 30, 'hypervisor': ['ironic'], 'network':
                'multi-tenant'
        },
        'entry-scale-swift': {
            'nodeCount': 30, 'hypervisor': [], 'storage': 'swift'
        },
        'mid-scale-kvm-ses': {
            'nodeCount': 200, 'hypervisor': ['kvm'], 'storage': 'ses'
        }
    }

    templates = []
    for name in os.listdir(CONF.paths.templates_dir):

        readme = os.path.join(CONF.paths.templates_dir, name, "README.md")
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

    Reads in YAML files from the selected example and returns them as a unified
    JSON object.

    .. :quickref: Templates; Return specified input model template

    :param name: template name

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/entry-scale-kvm-ses HTTP/1.1

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       {
         "name": "entry-scale-kvm-ses",
         "version": 2,
         "readme": {
           "html": "..."
         },
         "fileInfo": {"..."},
         "inputModel": {
           "cloud": {
             "name": "entry-scale-kvm-ses",
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
