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

from flask import abort
from flask import request
from functools import wraps
from oslo_config import cfg
from oslo_context import context
from oslo_policy import policy

from . import config

CONF = cfg.CONF
policy_file = CONF.paths.policy_file if hasattr(CONF, 'paths') else None
enforcer = policy.Enforcer(CONF, policy_file=policy_file)

# The default policies for all operations are defined here.  There are fewer
# policies defined than API entry points since it is common for two entry
# points to use the same policy; for example the api for deleting an entry from
# the model is protected by the same policy  as the api to update an entry
# since both operations can impact the deployed cloud in a similar way.
rules = [
    # admin_required is defined using the standard oslo_policy convention:
    #  https://docs.openstack.org/oslo.policy/1.23.0/usage.html#how-to-register
    policy.RuleDefault('admin_required', 'role:admin or is_admin:1'),

    # All policies used are defined here, and all use the admin_required rule
    # as the default
    policy.RuleDefault('lifecycle:get_model', 'rule:admin_required'),
    policy.RuleDefault('lifecycle:get_play', 'rule:admin_required'),
    policy.RuleDefault('lifecycle:get_service_file', 'rule:admin_required'),
    policy.RuleDefault('lifecycle:get_user', 'rule:admin_required'),
    policy.RuleDefault('lifecycle:list_packages', 'rule:admin_required'),
    policy.RuleDefault('lifecycle:list_playbooks', 'rule:admin_required'),
    policy.RuleDefault('lifecycle:playbook_listener', 'rule:admin_required'),
    policy.RuleDefault('lifecycle:restart', 'rule:admin_required'),
    policy.RuleDefault('lifecycle:run_config_processor',
                       'rule:admin_required'),
    policy.RuleDefault('lifecycle:run_playbook', 'rule:admin_required'),
    policy.RuleDefault('lifecycle:update_model', 'rule:admin_required'),
    policy.RuleDefault('lifecycle:update_service_file', 'rule:admin_required'),
    policy.RuleDefault('lifecycle:get_endpoints', 'rule:admin_required'),
    policy.RuleDefault('lifecycle:get_deployed_servers',
                       'rule:admin_required'),
]

enforcer.register_defaults(rules)


def enforce(rule):
    """Policy decorator

    Function decorator for declaring and enforcing the policy that is to be
    enforced
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Enforce the policy check only when configured for keystone auth
            if config.requires_auth() and not authorize(request, rule):
                abort(403, "%s is disallowed by policy" % rule)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def authorize(req, rule):
    """Checks that the action can be done by the given request

    Applies a check to ensure the request's project_id and user_id can be
    applied to the given action using the policy enforcement api.
    """

    # Create a context dictionary based in the CGI environment variables
    # (https://www.python.org/dev/peps/pep-0333/#environ-variables) that
    # are present on the request.  The keystone middleware injects more than 30
    # variables into the request (e.g. HTTP_X_USER_NAME) upon successful
    # authentication against keystone.  For more info, see
    # https://docs.openstack.org/keystonemiddleware/latest/api/\
    #   keystonemiddleware.auth_token.html#what-auth-token-adds-to-the\
    #  -request-for-use-by-the-openstack-service
    #
    ctx = context.RequestContext.from_environ(req.environ)
    target = {'project_id': ctx.project_id,
              'user_id': ctx.user_id}

    # Use oslo_policy's enforcer to authorize the user against the policy rules
    return enforcer.authorize(rule, target, ctx.to_policy_values())


def get_enforcer():
    """Returns the policy enforcer.

    This function is defined solely for use by the oslopolicy-sample-generator,
    which generates a sample policy file containing all of the rules defined in
    code.  For more information, see
    https://docs.openstack.org/oslo.policy/ \
        1.23.0/usage.html#registering-policy-defaults-in-code
    """
    return enforcer


def list_rules():
    """Returns a list of all rules

    Return a list of rules. This function is defined solely for use by the
    oslopolicy-sample-generator, which generates a sample policy file
    containing all of the rules defined in code.  For more information, see
    https://docs.openstack.org/oslo.policy/ \
        1.23.0/usage.html#registering-policy-defaults-in-code
    """
    return rules
