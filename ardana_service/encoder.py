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

from flask.json import JSONEncoder


# Some python constructs (especially sets) cannot be encoded into JSON directly
# since there is not such construct in JSON.  The following code, lifted
# directly from the flask documentation at
# http://flask.pocoo.org/docs/1.0/api/#flask.json.JSONEncoder will handle them,
# presuming that an iterator can be made from them.
class CustomJSONEncoder(JSONEncoder):
    def default(self, o):
        try:
            iterable = iter(o)
        except TypeError:
            pass
        else:
            return list(iterable)
        return JSONEncoder.default(self, o)
