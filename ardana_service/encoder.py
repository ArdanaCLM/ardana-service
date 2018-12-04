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

import datetime
from flask.json import JSONEncoder
import sys

if sys.version_info.major < 3:
    from xmlrpclib import DateTime
else:
    from xmlrpc.client import DateTime


# Some python constructs (especially sets) cannot be encoded into JSON directly
# since there is not such construct in JSON.  The following code, lifted
# directly from the flask documentation at
# http://flask.pocoo.org/docs/1.0/api/#flask.json.JSONEncoder will handle them,
# presuming that an iterator can be made from them.
class CustomJSONEncoder(JSONEncoder):
    def default(self, obj):
        try:
            if isinstance(obj, DateTime):
                return datetime.datetime.strptime(
                    obj.value, "%Y%m%dT%H:%M:%S").isoformat()
            iterable = iter(obj)
        except TypeError:
            pass
        else:
            return list(iterable)
        return JSONEncoder.default(self, obj)
