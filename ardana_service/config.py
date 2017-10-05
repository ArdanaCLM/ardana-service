from ConfigParser import NoOptionError
from ConfigParser import NoSectionError
from ConfigParser import SafeConfigParser
import logging
import os

LOG = logging.getLogger(__name__)

parser = SafeConfigParser()

default_config = os.path.normpath(os.path.join(os.path.dirname(__file__),
                                               'defaults.cfg'))

config_files = [default_config]
local_config = os.path.normpath(os.path.join(os.path.dirname(__file__), '..',
                                             'local.cfg'))
if os.path.exists(local_config):
    config_files.append(local_config)

LOG.info("Loading config files %s", config_files)
# This will fail with an exception if the config file cannot be loaded
parser.read(config_files)


def normalize(val):
    # Coerce value to an appropriate python type
    if val.lower() in ("yes", "true"):
        return True

    if val.lower() in ("no", "false"):
        return False

    try:
        return int(val)
    except ValueError:
        try:
            return float(val)
        except ValueError:
            pass

    return val


def get_flask_config():
    """Return all items in the [flask] section.

    The keys are converted to upercase as required by flask.  Since
    SafeConfigParser returns all values as strings
    """
    return {k.upper(): normalize(v) for k, v in parser.items('flask')}


def get(section, item, default=None):
    try:
        return normalize(parser.get(section, item))
    except (NoOptionError, NoSectionError):
        return default


def get_dir(dir_name):
    try:
        path = parser.get('paths', dir_name)
    except NoOptionError:
        return

    # Relative paths are resolved relative to the top-level directory
    if path[0] not in ('/', '~'):
        top_dir = os.path.normpath(os.path.join(os.path.dirname(__file__),
                                                ".."))
        path = os.path.abspath(os.path.join(top_dir, path))

    return path
