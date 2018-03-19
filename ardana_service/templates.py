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

from . import model
from flask import abort
from flask import Blueprint
from flask import jsonify
from operator import itemgetter
import os
from oslo_config import cfg
from oslo_log import log as logging

from . import policy

LOG = logging.getLogger(__name__)
bp = Blueprint('templates', __name__)
CONF = cfg.CONF


@bp.route("/api/v2/templates")
@policy.enforce('lifecycle:get_model')
def get_all_templates():
    """Returns all available input model templates, aka examples

    .. :quickref: Templates; Return list of available input model templates

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json

       [
         {
           "name": "entry-scale-kvm-esx",
           "href": "/api/v2/templates/entry-scale-kvm-esx",
           "overview": "...",
           "metadata": {"nodeCount": 30, "hypervisor": ["esx", "kvm"]}
         },
         {
           "name": "entry-scale-ironic-flat-network",
           "href": "/api/v2/templates/entry-scale-ironic-flat-network",
           "overview": "...",
           "metadata": {"nodeCount": 30, "hypervisor": ["ironic"],
                "network": "flat"}
         },
         {
           "name": "mid-scale-kvm",
           "href": "/api/v2/templates/mid-scale-kvm",
           "overview": "...",
           "metadata": {"nodeCount": 200, "hypervisor": ["kvm"]}
         },
         "..."
       ]
    """

    metadata_table = {
        'entry-scale-kvm': {
            'nodeCount': 30, 'hypervisor': ['kvm']
        },
        'entry-scale-kvm-esx': {
            'nodeCount': 30, 'hypervisor': ['esx', 'kvm']
        },
        'entry-scale-kvm-esx-mml': {
            'nodeCount': 30, 'hypervisor': ['esx', 'kvm']
        },
        'entry-scale-kvm-mml': {
            'nodeCount': 30, 'hypervisor': ['kvm']
        },
        'entry-scale-ironic-flat-network': {
            'nodeCount': 30, 'hypervisor': ['ironic'], 'network': 'flat'
        },
        'entry-scale-ironic-multi-tenancy': {
            'nodeCount': 30, 'hypervisor': ['ironic'], 'network':
                'multi-tenant'
        },
        'entry-scale-swift': {
            'nodeCount': 30, 'hypervisor': []
        },
        'mid-scale-kvm': {
            'nodeCount': 200, 'hypervisor': ['kvm']
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

    return jsonify(sorted(templates, key=itemgetter('name')))


@bp.route("/api/v2/templates/<name>")
@policy.enforce('lifecycle:get_model')
def get_template(name):
    """Returns a particular template by name

    Reads in YAML files from the selected example and returns them as a unified
    JSON object.

    .. :quickref: Templates; Return specified input model template

    :param name: template name

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/entry-scale-kvm HTTP/1.1

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       {
         "name": "entry-scale-kvm",
         "version": 2,
         "readme": {
           "html": "..."
         },
         "fileInfo": {"..."},
         "inputModel": {
           "cloud": {
             "name": "entry-scale-kvm",
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
