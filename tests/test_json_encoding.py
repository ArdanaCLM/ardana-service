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

import flask
import testtools


from ardana_service import encoder


class TestJSonEncoding(testtools.TestCase):

    def test_encoding_sets(self):
        path = '/some/path'  # use any arbitrary path here
        app = flask.Flask('unittest')

        s = set(['a', 'b'])

        # Illustrate that when using the default JSON Encoder, a TypeError
        # will be raised when trying to convert a set into JSON
        with app.test_request_context(path=path):
            # raises TypeError: set(['a', 'b']) is not JSON serializable
            self.assertRaises(TypeError, flask.json.jsonify, s)

        # Now use our custom encoder
        app.json_encoder = encoder.CustomJSONEncoder
        with app.test_request_context(path=path):
            # No exception should be raised now. If one is raised, it would
            # cause the unit test to fail.
            flask.json.jsonify(s)
