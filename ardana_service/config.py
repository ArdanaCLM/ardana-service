import os
from oslo_config import cfg

flask_opts = [
    cfg.IPOpt('host',
              default='127.0.0.1',
              help='IP address to listen on.'),
    cfg.PortOpt('port',
                default=9085,
                help='Port number to listen on.'),
    cfg.BoolOpt('pretty_json',
                default=False,
                help='Format json responses in a pretty way'),
]

path_opts = [
    cfg.StrOpt('config_dir',
               default=os.path.expanduser('~/openstack/my_cloud/config'),
               help='Location of openstack config files'),




    cfg.StrOpt('cp_output_dir',
               default=os.path.expanduser('~/scratch/cp/my_cloud/stage/info'),
               help='Config processor output dir'),
    cfg.StrOpt('cp_python_path',
               default='/opt/stack/service/config-processor/venv/bin/python',
               help='Python path used for running the config processor '
                    'directly, normally in the virtual environment '
                    'that has all config processor classes installed in it.'),
    cfg.StrOpt('cp_script_path',
               default='/opt/stack/service/config-processor/venv/share/' +
                       'ardana-config-processor/Driver/ardana-cp',
               help='Path to python script used to invoke the config '
                    'processor locally'),
    cfg.StrOpt('cp_ready_output_dir',
               default=os.path.expanduser(
                   '~/scratch/ansible/next/my_cloud/stage/info'),
               help='Directory into which the local config processor writes '
                    'its output'),
    cfg.StrOpt('cp_schema_dir',
               default='/opt/stack/service/config-processor/venv/share/' +
                       'ardana-config-processor/Data/Site',
               help='Config processor schema dir'),
    cfg.StrOpt('cp_services_dir',
               default=os.path.expanduser('~/openstack/ardana/services'),
               help='Config processor services dir'),


    cfg.StrOpt('log_dir',
               default='/var/log/ardana-service',
               help='Location of playbook run logs'),
    cfg.StrOpt('model_dir',
               default=os.path.expanduser('~/openstack/my_cloud/definition'),
               help='Location of customer''s data model'),
    cfg.StrOpt('playbooks_dir',
               default=os.path.expanduser(
                   '~/scratch/ansible/next/ardana/ansible'),
               help='Location where playbooks are, along with the group_vars '
                    'and other things produced by the config processor'),
    cfg.StrOpt('pre_playbooks_dir',
               default=os.path.expanduser('~/openstack/ardana/ansible'),
               help='Location of os install playbooks, which is where the '
                    'un-processed playbooks reside'),
    cfg.StrOpt('templates_dir',
               default=os.path.expanduser('~/openstack/examples'),
               help='Directory containing input model templates'),
    cfg.StrOpt('top_dir',
               default=os.path.expanduser('~/openstack/my_cloud'),
               help='Top-level directory containing all of the customer''s '
                    'files, which are managed by git operations'),
]

CONF = cfg.CONF
CONF.register_opts(flask_opts)
CONF.register_opts(path_opts, 'paths')


# This function is used by "tox -e genopts" to generate a config file
# containing for the ardana service
def list_opts():
    return [('DEFAULT', flask_opts), ('paths', path_opts)]
