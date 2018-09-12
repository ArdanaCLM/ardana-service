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

from .playbooks import run_playbook
from .plays import get_metadata_file
from flask import abort
from flask import Blueprint
from flask import jsonify
import itertools
import json
import os
from os.path import dirname
from os.path import exists
from os.path import join
from oslo_config import cfg
from oslo_log import log as logging
import re
import subprocess

from . import policy
from time import sleep

LOG = logging.getLogger(__name__)
bp = Blueprint('packages', __name__)
PKG_CACHE_FILE = cfg.CONF.paths.packages_cache
HOST_PKGS_FILE = cfg.CONF.paths.packages_hosts_data
PACKAGES_PLAY = "_ardana-service-get-pkgdata"


@bp.route("/api/v2/packages", methods=['GET'])
@policy.enforce('lifecycle:list_packages')
def get_packages():
    """Get installed venv packages and SUSE-Openstack-installed packages

    This caches the ardana and venv-openstack packages installed on the
    deployer and returns a list of ardana packages.

    .. :quickref: Packages; list ardana packages and openstack venv versions

    **Example Request**:

    .. sourcecode:: http

       GET /api/v2/packages HTTP/1.1
       Content-Type: application/json

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       {
           "cloud_installed_packages": [{
               "name": "ardana-logging",
               "versions": ["8.0+git.1531134017.565cede-102.1"]
           }, {
               "name": "ardana-nova",
               "versions": ["8.0+git.1528891405.336a954-103.6"]
           }, ... <and so on>],
           "openstack_venv_packages": [{
               "available": "2.2.1-19.116",
               "installed": ["2.2.1-9.1", "2.2.1-19.116"],
               "name": "monasca"
           }, {
               "available": "9.0.2-19.124",
               "installed": ["9.0.2-19.124"],
               "name": "ceilometer"
           }, ... <and so on>]
       }
    """

    if cfg.CONF.testing.use_mock:
        mock_json = "tools/packages.json"
        json_file = join(dirname(dirname(__file__)), mock_json)
        with open(json_file) as f:
            return jsonify(json.load(f))

    installed_os_pkgs, os_pkg_cache = update_openstack_pkg_cache()

    # Run the playbook to get package data from all the hosts in the model
    proc_info = {}
    try:
        vars = {
            "extra-vars": {
                "host_pkgs_file": HOST_PKGS_FILE
            }
        }
        play_id = run_playbook(PACKAGES_PLAY, vars)["id"]
        # Poll for "code" and ignore its value because some hosts may be down.
        while 'code' not in proc_info:
            with open(get_metadata_file(play_id)) as f:
                proc_info = json.load(f)
            if 'code' not in proc_info:
                sleep(1)
    except Exception as e:
        LOG.error("Could not get remote package information: %s" % e)
        abort(404, "Remote package information unavailable")

    # host_pkgs example structure created by PACKAGES_PLAY playbook run:
    # {
    #     "host1": {
    #         # list of installed timestamped openstack venv packages on host1
    #         "ts_os_pkgs": [
    #             "barbican-20180820T201055Z",
    #             "cinder-20180820T190043Z", ...
    #         ],
    #         # list of SUSE-Openstack-cloud packages installed on host1
    #         "zypper_cloud_pkgs": {
    #             "python-PasteDeploy": "1.5.2-1.52",
    #             "python-pymongo": "3.1.1-1.55", ...
    #         }
    #     },
    #     "host2": { ... }
    # }
    try:
        with open(HOST_PKGS_FILE) as f:
            host_pkgs = json.load(f)
    except Exception as e:
        LOG.error("Could not retrieve remote host pkg data from %s: %s"
                  % (HOST_PKGS_FILE, e))
        abort(404, "Remote package information unavailable")
    finally:
        if exists(HOST_PKGS_FILE):
            os.remove(HOST_PKGS_FILE)

    # Reconcile openstack timestamps to versions installed on each system
    all_ts_os_pkgs = [host['ts_os_pkgs'] for host in host_pkgs.values()]
    uniq_ts_pkgs = set(itertools.chain.from_iterable(all_ts_os_pkgs))
    re_name_ts = re.compile(r'(?P<name>[\w-]+)-\d+T\d+Z')
    for pkg in uniq_ts_pkgs:
        pkg_match = re_name_ts.match(pkg)
        if not pkg_match:
            LOG.warning('Unrecognized package format: %s' % pkg)
            continue
        name = pkg_match.group('name')

        if not installed_os_pkgs.get(name):
            LOG.warning('Unrecognized service name: %s' % name)
            continue

        version = os_pkg_cache.get(pkg)
        if version:
            installed_os_pkgs[name]['installed'].append(version)
        else:
            # We don't know what version this is, so we'll just add
            # the timestamped package name in there (should never happen)
            installed_os_pkgs[name]['installed'].append(pkg)

    ovp = [
        {
            'name': k,
            'installed': v['installed'],
            'available': v['available']
        } for k, v in installed_os_pkgs.items()]

    # Create a list of unique SUSE-Openstack installed packages across all
    # systems
    pkgs_dict = {}
    for host in host_pkgs.values():
        for name, version in host['zypper_cloud_pkgs'].iteritems():
            if name not in pkgs_dict:
                pkgs_dict[name] = [version]
            elif version not in pkgs_dict[name]:
                # this case might only occur during upgrade or partial upgrade
                pkgs_dict[name].append(version)
    cip = [
        {
            'name': name,
            'versions': versions
        } for name, versions in pkgs_dict.items()
    ]

    response = {
        'openstack_venv_packages': ovp,
        'cloud_installed_packages': cip
    }

    return jsonify(response)


def update_openstack_pkg_cache():
    re_openstack = re.compile(r'venv-openstack-(?P<name>[\w-]+)-')

    # contains current AND OLD openstack packages where
    # k: timestamped package  (i.e. monasca-20180820T190346Z)
    # v: version              (i.e. 2.2.1-19.155)
    # This will build up over time with patches and upgrades
    os_pkg_cache = {}

    # contains current/available openstack packages installed on the deployer
    # k: openstack name       (i.e. monasca)
    # v: version              (i.e. 2.2.1-19.155)
    installed_os_pkgs = {}

    # Load package cache
    try:
        with open(PKG_CACHE_FILE) as f:
            os_pkg_cache = json.load(f)
    except Exception as e:
        LOG.info("Could not load %s: %s." % (PKG_CACHE_FILE, e))

    # TODO(choyj): The code below could be simplified by using the zypper data
    # from the output of PACKAGES_PLAY.  But we do not know which model host is
    # the deployer other than via educated guess (only deployer has venv pkgs
    # installed).  So, for now:

    # See what openstack packages are installed on this deployer
    try:
        p = subprocess.Popen(['zypper', '--terse', 'packages', '--installed'],
                             stdout=subprocess.PIPE)
        zyp_lines = p.communicate()[0].decode('utf-8').split('\n')
    except OSError:
        LOG.error("zypper unavailable or not working on this system")
        abort(503, 'zypper unavailable on this host')

    for line in zyp_lines:
        fields = line.split('|')
        # if this is a valid line and the package is installed
        if len(fields) == 5 and 'i' in fields[0]:
            name = fields[2].strip()
            vers = fields[3].strip()
            os_match = re_openstack.match(name)
            if os_match:
                # a venv-openstack package, therefore figure out timestamped
                # package to update/add to os_pkg_cache
                name_vers = "%s-%s" % (name, vers)
                try:
                    p = subprocess.Popen(
                        ['rpm', '--query', '--list', name_vers],
                        stdout=subprocess.PIPE)
                    rpm_lines = p.communicate()[0].split('\n')
                    project = os_match.group('name')
                    re_ts_pkg = \
                        re.compile(r"/(?P<name_ts>%s-\d+T\d+Z).tgz$" % project)
                    for rpm_line in rpm_lines:
                        ts_pkg_match = re_ts_pkg.search(rpm_line)
                        if ts_pkg_match:
                            os_pkg_cache[ts_pkg_match.group('name_ts')] = vers
                            installed_os_pkgs[project] = {
                                'available': vers,
                                'installed': []
                            }
                            break
                except OSError as e:
                    LOG.warning("Could not determine timestamped package for"
                                " %s: %s" % (name_vers, e))

    # Save package cache
    try:
        with open(PKG_CACHE_FILE, 'w') as f:
            json.dump(os_pkg_cache, f, indent=4, sort_keys=True)
    except Exception as e:
        LOG.info("Could not save %s: %s." % (PKG_CACHE_FILE, e))

    return installed_os_pkgs, os_pkg_cache
