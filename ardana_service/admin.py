# (c) Copyright 2017-2019 SUSE LLC
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
from flask import request
from keystoneauth1 import exceptions as exc
from keystoneauth1 import session as ks_session
from keystoneclient.auth.identity import v3
from keystoneclient.v3 import client as ks_client
import logging
import os
from oslo_config import cfg
import pbr.version
import pwd
import threading
import time

from .util import ping

from . import config
from . import policy

bp = Blueprint('admin', __name__)
CONF = cfg.CONF
LOG = logging.getLogger(__name__)
USER_AGENT = 'Installer UI'


@bp.route("/api/v2/version")
def version():
    """Returns the version of the service

    .. :quickref: Admin; Returns the version of the service

    **Example valid response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       0.0.1.dev16

    """
    version_info = pbr.version.VersionInfo('ardana-service')
    return version_info.version_string_with_vcs()


@bp.route("/api/v2/heartbeat")
def heartbeat():
    """Returns the epoch time

    Simple API to verify that the service is up and responding.  Returns
    the number of seconds since 1970-01-01 00:00:00 GMT.

    .. :quickref: Admin; Returns the epoch time

    **Example valid response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       1502745650

    """
    return jsonify(int(time.time()))


@bp.route("/api/v2/user")
@policy.enforce('lifecycle:get_user')
def user():
    """Returns the username the service is running under

    .. :quickref: Admin; Returns the username the service is running under

    **Example valid response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK

       {"username": "myusername"}

    """
    user_dict = {'username': pwd.getpwuid(os.getuid()).pw_name}
    return jsonify(user_dict)


def update_trigger_file():
    trigger_file = os.path.join(CONF.paths.log_dir, 'trigger.txt')
    with open(trigger_file, 'w') as f:
        f.write("Triggered restart at %s\n" % time.asctime())


@bp.route("/api/v2/restart", methods=['POST'])
@policy.enforce('lifecycle:restart')
def restart():
    """Requests the service to restart after a specified delay, in seconds

    .. :quickref: Admin; Requests a service restart after a delay

    **Example Request**:

    .. sourcecode:: http

       POST /api/v2/user HTTP/1.1

       Content-Type: application/json

       {
          "delay": 60
       }
    """
    info = request.get_json() or {}
    delay_secs = int(info.get('delay', 0))

    t = threading.Timer(delay_secs, update_trigger_file)
    t.start()

    return jsonify('Success')


@bp.route("/api/v2/login", methods=['POST'])
def login():
    """Authenticates with keystone and returns a token

    .. :quickref: Admin; Authenticates with keystone

    **Example Request**:

    .. sourcecode:: http

       POST /api/v2/login HTTP/1.1
       Content-Type: application/json

       {
          "username": "admin",
          "password": "secret"
       }

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json

       {
          "token": "gAAAAABbEaruZDQGIH5KmKWHlDZIw7CLq",
          "expires": "2018-06-01T21:22:06+00:00"
       }

    :status 200: successful authentication
    :status 401: invalid credentials
    :status 403: authentication not permitted, or user not authorized for any
                 projects
    """

    if not config.requires_auth():
        abort(403,
              "authentication not permitted since service is in insecure mode")

    info = request.get_json() or {}
    username = info.get('username')
    password = info.get('password')
    user_domain_name = info.get('user_domain_name', 'Default')
    token = _authenticate(CONF.keystone_authtoken.auth_url,
                          username,
                          password,
                          user_domain_name)
    return jsonify(token)


def _authenticate(auth_url, username=None, password=None,
                  user_domain_name='Default'):
    """Authenticate with keystone

    Creates an unscoped token using the given credentials (which validates
    them), and then uses that token to get a project-scoped token.
    """

    unscoped_auth = v3.Password(auth_url,
                                username=username,
                                password=password,
                                user_domain_name=user_domain_name,
                                unscoped=True)

    session = ks_session.Session(user_agent=USER_AGENT,
                                 verify=not CONF.keystone_authtoken.insecure)
    try:
        # Trigger keystone to verify the credentials
        unscoped_auth_ref = unscoped_auth.get_access(session)

    except exc.connection.ConnectFailure as e:
        abort(503, str(e))

    except exc.http.HttpError as e:
        abort(e.http_status, e.message)

    except exc.ClientException as e:
        abort(401, str(e))

    except Exception as e:
        LOG.exception(e)
        abort(500, "Unable to authenticate")

    client = ks_client.Client(session=session,
                              auth=unscoped_auth,
                              user_agent=USER_AGENT)

    auth_url = unscoped_auth.auth_url

    projects = client.projects.list(user=unscoped_auth_ref.user_id)

    # Filter out disabled projects
    projects = [project for project in projects if project.enabled]

    # Prioritize the admin project by putting it at the beginning of the list
    for pos, project in enumerate(projects):
        if project.name == 'admin':
            projects.pop(pos)
            projects.insert(0, project)
            break

    # Return the first project token that we have the admin role on, otherwise
    # return the first project token we have any role on.
    fallback_auth_ref = None
    for project in projects:
        auth = v3.Token(auth_url=auth_url,
                        token=unscoped_auth_ref.auth_token,
                        project_id=project.id,
                        reauthenticate=False)
        try:
            auth_ref = auth.get_access(session)
            if 'admin' in auth_ref.role_names:
                return {'token': auth_ref.auth_token,
                        'expires': auth_ref.expires.isoformat()}
            elif not fallback_auth_ref:
                fallback_auth_ref = auth_ref

        except Exception as e:
            pass

    if fallback_auth_ref:
        return {'token': fallback_auth_ref.auth_token,
                'expires': fallback_auth_ref.expires.isoformat()}

    # TODO(gary): Consider as a secondary fallback to return a domain-scoped
    # token

    abort(403, "Not authorized for any project")


@bp.route("/api/v2/is_secured")
def get_secured():
    """Returns whether authentication is required

    Returns a json object indicating whether the service is configured to
    enforce authentication

    .. :quickref: Model; Returns whether authentication is required

    **Example Response**:

    .. sourcecode:: http

       HTTP/1.1 200 OK
       Content-Type: application/json

       {
           "isSecured": false
       }

    :status 200: success
    """
    return jsonify({'isSecured': config.requires_auth()})


@bp.route("/api/v2/connection_test", methods=['POST'])
def connection_test():
    body = request.get_json() or {}
    host = body['host']
    try:
        ping(host, 22)
        return jsonify('Success')
    except Exception as e:
        return jsonify(error=str(e)), 404
