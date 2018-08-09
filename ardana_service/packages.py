# (c) Copyright 2018 SUSE LLC
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

from flask import Blueprint
from flask import jsonify
import json
from oslo_config import cfg
from oslo_log import log as logging
import re
import subprocess

from . import policy

LOG = logging.getLogger(__name__)
bp = Blueprint('packages', __name__)
pkg_file = cfg.CONF.paths.packages_file

# contains current AND OLD openstack packages where
# k: timestamped package
# v: dictionary containing name and version
pkg_cache = {}

# contains current(available) openstack packages installed on the deployer
# k: name
# v: version
os_avail_pkgs = {}

re_ardana = re.compile(r'\bardana\b')
re_openstack = re.compile(r'venv-openstack-(\w+?)-')


@bp.route("/api/v2/packages/ardana", methods=['GET'])
@policy.enforce('lifecycle:list_packages')
def get_deployer_packages():
    """Get installed packages on the deployer

    This caches the ardana and venv-openstack packages installed on the
    deployer and returns a list of ardana packages.

    .. :quickref: Packages; list ardana packages

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/packages/ardana HTTP/1.1
       Content-Type: application/json

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       [
           {
               "name": "ardana-logging",
               "version": "8.0+git.1531134017.565cede-102.1"
           },
           {
               "name": "ardana-nova",
               "version": "8.0+git.1528891405.336a954-103.6"
           },
           <and so on>
       ]
    """

    global pkg_cache
    global os_avail_pkgs
    ardana_pkgs = {}
    os_avail_pkgs = {}

    # Load package cache
    try:
        with open(pkg_file) as f:
            pkg_cache = json.loads(f)
    except Exception as e:
        LOG.info("Could not load %s: %s." % (pkg_file, e))

    # See what packages are installed on the deployer
    p = subprocess.Popen(['zypper', '--terse', 'packages', '--installed'],
                         stdout=subprocess.PIPE)
    zyp_lines = p.communicate()[0].split('\n')
    for line in zyp_lines:
        fields = line.split('|')
        # if this is a valid line and the package is installed
        if len(fields) == 5 and 'i' in fields[0]:
            name = fields[2].strip()
            vers = fields[3].strip()
            os_match = re_openstack.match(name)
            if os_match:
                # a venv-openstack package, therefore figure out timestamped
                # package to update/add to pkg_cache
                name_vers = "%s-%s" % (name, vers)
                try:
                    p = subprocess.Popen(
                        ['rpm', '--query', '--list', name_vers],
                        stdout=subprocess.PIPE)
                    rpm_lines = p.communicate()[0].split('\n')
                    project = os_match.group(1)
                    re_ts_pkg = re.compile(r"/(%s-\d+T\d+Z).tgz$" % project)
                    for rpm_line in rpm_lines:
                        ts_pkg_match = re_ts_pkg.search(rpm_line)
                        if ts_pkg_match:
                            pkg_cache[ts_pkg_match.group(1)] = {
                                'name': project,
                                'version': vers
                            }
                            os_avail_pkgs[project] = vers
                            break
                except OSError as e:
                    LOG.warning("Could not determine timestamped package for"
                                " %s: %s" % (name_vers, e))
            elif re_ardana.search(name):
                # packages with 'ardana' in the name
                ardana_pkgs[name] = vers

    # Save package cache
    try:
        with open(pkg_file, 'w') as f:
            json.dump(pkg_cache, f, indent=4, sort_keys=True)
    except Exception as e:
        LOG.info("Could not save %s: %s." % (pkg_file, e))

    return jsonify([{'name': k, 'version': v} for k, v in ardana_pkgs.items()])


@bp.route("/api/v2/packages/openstack", methods=['GET'])
@policy.enforce('lifecycle:list_packages')
def get_installed_packages():
    """Get installed venv-openstack packages on all machines known by the model

    Logs in to all machines in the model and gets installed openstack package
    information

    .. :quickref: Packages; get all installed venv packages on all machines

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/packages/openstack HTTP/1.1
       Content-Type: application/json

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       {
           "available": "2.2.1-19.116",
           "installed": ["2.2.1-9.1", "2.2.1-19.116"],
           "name": "monasca"
       },
       {
           "available": "9.0.2-19.124",
           "installed": ["9.0.2-19.124"],
           "name": "ceilometer"
       },
       < and so on >

    """

    get_deployer_packages()
    # TODO(choyj): This section needs to be reworked to call a playbook and
    #              gather data from all machines in the model
    pkgs = [
        {
            'name': k,
            'installed': [v],
            'available': v
        } for k, v in os_avail_pkgs.items()]

    return jsonify(pkgs)
