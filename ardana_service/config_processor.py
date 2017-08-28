from flask import abort
from flask import Blueprint
from flask import jsonify
from flask import make_response
from flask import request
import logging
import os
import subprocess
import sys
import tempfile
import time

from . import config
from . import model
from . import playbooks

LOG = logging.getLogger(__name__)
bp = Blueprint('config_processor', __name__)

MODEL_DIR = config.get_dir("model_dir")
CP_SERVICES_DIR = config.get_dir("cp_services_dir")
CP_SCHEMA_DIR = config.get_dir("cp_schema_dir")
CP_SCRIPT_PATH = config.get_dir("cp_python_script_path")


@bp.route("/api/v2/config_processor", methods=['POST'])
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

    **Example Request**:

    .. sourcecode:: http

       POST /api/v2/config_processor HTTP/1.1

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

    python = config.get_dir('cp_python_path') or sys.executable

    tempdir = tempfile.mkdtemp()

    output_dir = os.path.join(tempdir, "clouds")

    cmd = playbooks.build_command_line(python, CP_SCRIPT_PATH, [
        '-l', os.path.join(tempdir, "log"),
        '-c', os.path.join(MODEL_DIR, 'cloudConfig.yml'),
        '-s', CP_SERVICES_DIR,
        '-r', CP_SCHEMA_DIR,
        '-o', os.path.join(tempdir, output_dir)])

    start_time = int(time.time())

    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except Exception as e:
        # Cannot get except subprocess.CalledProcessError to be caught, so
        # catch Exception
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
    else:
        error = {
            'startTime': start_time,
            'endTime': int(time.time()),
            'log': 'Unable to locate config processor output',
            'errorCode': 127
        }
        abort(make_response(jsonify(error), 400))
