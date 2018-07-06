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
from flask import make_response
from flask import request
import os
from oslo_config import cfg
from oslo_log import log as logging
import subprocess
import sys
import tempfile
import time

from . import model
from . import playbooks
from . import policy

LOG = logging.getLogger(__name__)
bp = Blueprint('config_processor', __name__)
CONF = cfg.CONF


@bp.route("/api/v2/config_processor", methods=['POST'])
@policy.enforce('lifecycle:run_config_processor')
def run_config_processor():
    """Validate the current input model

    No body is required

    This will run the configuration processor directly, not the playbook. This
    is a synchronous call which takes up to about 20 seconds. The HTTP response
    will be sent once the config processor has finished. If the model was
    deemed valid, the response will have a status code of 200 and the body will
    be the output of the config processor (Note: this is in fact the expanded
    input model and is quite large). If the model was invalid, the status code
    will be 400 and the body of the response will be contain the log of the
    Config Processor explaining why things failed.

    .. :quickref: Config Processor; Validate the current input model

    **Example valid response**:

    .. sourcecode:: http

       HTTP/1.1 201 CREATED

    **Example invalid response**:

    .. sourcecode:: http

       HTTP/1.1 400 Bad Request
       Content-Type: application/json

       {
         "errorCode": 254,
         "log": "Processing cloud model version 2.0####  ...."
         "startTime": 1457710327543,
         "endTime": 1457710330491,
       }

    """
    # TODO(gary): Remove this and modify the UI to avoid calling the back end
    req = request.json
    if req and "want_fail" in req:
        error = {"log": "woops", "errorCode": 254}
        abort(make_response(jsonify(error), 400))
    elif req and "want_pass" in req:
        return '', 201

    python = CONF.paths.cp_python_path or sys.executable

    tempdir = tempfile.mkdtemp()

    output_dir = os.path.join(tempdir, "clouds")
    log_dir = os.path.join(tempdir, "log")

    cmd = playbooks.build_command_line(python, CONF.paths.cp_script_path, [
        '-l', log_dir,
        '-c', os.path.join(CONF.paths.model_dir, 'cloudConfig.yml'),
        '-s', CONF.paths.cp_services_dir,
        '-r', CONF.paths.cp_schema_dir,
        '-o', output_dir])

    start_time = int(time.time())

    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT,
                                universal_newlines=True)
    except Exception as e:
        # Cannot get except subprocess.CalledProcessError to be caught, so
        # catch Exception
        LOG.exception(e)
        error = {
            'startTime': start_time,
            'endTime': int(time.time())
        }
        if hasattr(e, 'output'):
            error['log'] = e.output
        if hasattr(e, 'returncode'):
            error['errorCode'] = e.returncode
        abort(make_response(jsonify(error), 400))

    input_model = model.read_model()
    cloud_name = input_model['inputModel']['cloud']['name']

    generated = os.path.join(output_dir, cloud_name, '2.0', 'stage', 'info')
    if os.path.exists(generated):
        return '', 201

    msg = 'Unable to locate config processor output'
    error_file = os.path.join(log_dir, "errors.log")
    if os.path.exists(error_file):
        try:
            with open(error_file) as f:
                lines = f.readlines()
            msg = ''.join(lines)
        except IOError:
            pass

    error = {
        'startTime': start_time,
        'endTime': int(time.time()),
        'log': msg,
        'errorCode': 127
    }
    abort(make_response(jsonify(error), 400))
