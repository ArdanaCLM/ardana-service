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

import os
from oslo_serialization import jsonutils
import testtools

from ardana_service.monasca import bp
from flask import Flask

app = Flask(__name__)
app.register_blueprint(bp)


class TestMonasca(testtools.TestCase):

    def setUp(self):
        super(TestMonasca, self).setUp()
        self.TEST_DATA_DIR = os.path.join(os.path.dirname(__file__),
                                          'test_data/monasca_tests')

    def test_is_monasca_installed(self):
        test_app = app.test_client()
        mock_catalog_file = 'X-Service-Catalog-No-Monasca.json'
        file_path = os.path.join(self.TEST_DATA_DIR, mock_catalog_file)
        with open(file_path, 'r') as myfile:
            cat_content = myfile.read()

        # validate the installed response is false if Monasca is not present
        resp = test_app.get('/api/v2/monasca/is_installed',
                            environ_base={'HTTP_X_SERVICE_CATALOG':
                                          cat_content})
        x = jsonutils.loads(resp.data)
        self.assertEqual(x.get('installed'), 'false')

        mock_catalog_file = 'X-Service-Catalog.json'
        file_path = os.path.join(self.TEST_DATA_DIR, mock_catalog_file)
        with open(file_path, 'r') as myfile:
            cat_content = myfile.read()

        # validate the installed response is true if Monasca is present
        resp = test_app.get('/api/v2/monasca/is_installed',
                            environ_base={'HTTP_X_SERVICE_CATALOG':
                                          cat_content})
        x = jsonutils.loads(resp.data)
        self.assertEqual(x.get('installed'), 'true')
