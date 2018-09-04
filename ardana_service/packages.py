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
HOST_TS_PKGS_FILE = cfg.CONF.paths.packages_hosts_data
PACKAGES_PLAY = "_ardana-service-get-pkgdata"

# contains current AND OLD openstack packages where
# k: timestamped package
# v: version
pkg_cache = {}

# contains current/available openstack packages installed on the deployer
# and installed packages on all the systems
# k: name
# v: version  i.e. {'available': vers, 'installed':[list of versions]}
all_pkgs = {}

re_ardana = re.compile(r'\bardana\b')
re_openstack = re.compile(r'venv-openstack-(?P<name>[\w-]+)-')
re_name_ts = re.compile(r'(?P<name>[\w-]+)-\d+T\d+Z')


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

    if cfg.CONF.testing.use_mock:
        mock_json = "tools/packages_ardana.json"
        json_file = join(dirname(dirname(__file__)), mock_json)
        with open(json_file) as f:
            return jsonify(json.load(f))

    global pkg_cache
    global all_pkgs
    ardana_pkgs = {}
    all_pkgs = {}

    # Load package cache
    try:
        with open(PKG_CACHE_FILE) as f:
            pkg_cache = json.load(f)
    except Exception as e:
        LOG.info("Could not load %s: %s." % (PKG_CACHE_FILE, e))

    # See what packages are installed on the deployer
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
                # package to update/add to pkg_cache
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
                            pkg_cache[ts_pkg_match.group('name_ts')] = vers
                            all_pkgs[project] = {
                                'available': vers,
                                'installed': []
                            }
                            break
                except OSError as e:
                    LOG.warning("Could not determine timestamped package for"
                                " %s: %s" % (name_vers, e))
            elif re_ardana.search(name):
                # packages with 'ardana' in the name
                ardana_pkgs[name] = vers

    # Save package cache
    try:
        with open(PKG_CACHE_FILE, 'w') as f:
            json.dump(pkg_cache, f, indent=4, sort_keys=True)
    except Exception as e:
        LOG.info("Could not save %s: %s." % (PKG_CACHE_FILE, e))

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
    if cfg.CONF.testing.use_mock:
        mock_json = "tools/packages_openstack.json"
        json_file = join(dirname(dirname(__file__)), mock_json)
        with open(json_file) as f:
            return jsonify(json.load(f))

    global all_pkgs

    # Get the mapping of time-stamped package names -> package details
    get_deployer_packages()

    # Run the playbook to get package data from all the hosts in the model
    proc_info = {}
    try:
        vars = {
            "extra-vars": {
                "host_ts_pkgs_file": HOST_TS_PKGS_FILE
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

    try:
        with open(HOST_TS_PKGS_FILE) as f:
            host_ts_pkgs = json.load(f)
    except Exception as e:
        LOG.error("Could not retrieve remote host pkg data from %s: %s"
                  % (HOST_TS_PKGS_FILE, e))
        abort(404, "Remote package information unavailable")
    finally:
        if exists(HOST_TS_PKGS_FILE):
            os.remove(HOST_TS_PKGS_FILE)

    uniq_pkgs = set(itertools.chain.from_iterable(host_ts_pkgs.values()))

    for pkg in uniq_pkgs:
        pkg_match = re_name_ts.match(pkg)
        if not pkg_match:
            LOG.warning('Unrecognized package format: %s' % pkg)
            continue
        name = pkg_match.group('name')

        if not all_pkgs.get(name):
            LOG.warning('Unrecognized service name: %s' % name)
            continue

        version = pkg_cache.get(pkg)
        if version:
            all_pkgs[name]['installed'].append(version)
        else:
            # We don't know what version this is, so we'll just add
            # the timestamped package name in there (should never happen)
            all_pkgs[name]['installed'].append(pkg)
    pkgs = [
        {
            'name': k,
            'installed': v['installed'],
            'available': v['available']
        } for k, v in all_pkgs.items()]

    return jsonify(pkgs)
