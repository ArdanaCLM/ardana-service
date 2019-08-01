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

import testtools

from ardana_service import util


class TestUtils(testtools.TestCase):

    def test_is_ipv6(self):
        self.assertTrue(util.is_ipv6('ff::1'))
        self.assertTrue(
            util.is_ipv6('2001:0db8:85a3:0000:0000:8a2e:0370:7334'))
        self.assertFalse(util.is_ipv6('127.0.0.2'))
        self.assertFalse(util.is_ipv6(''))
        self.assertFalse(util.is_ipv6('foobar'))

    def test_url_address(self):
        self.assertEquals('[ff::1]', util.url_address('ff::1'))
        self.assertEquals('127.0.0.1', util.url_address('127.0.0.1'))
        self.assertEquals('somehost', util.url_address('somehost'))
