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

import json
from oslo_config import cfg
from oslo_config import fixture as oslo_fixture
import testtools

from ardana_service import config  # noqa: F401
from ardana_service import playbooks

CONF = cfg.CONF


class TestArgProcessing(testtools.TestCase):

    def setUp(self):
        super(TestArgProcessing, self).setUp()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.config(group='paths', playbooks_dir='data/ardana-ansible')

    def test_dashes(self):
        args = playbooks.get_command_args({
            "key1": "val1",
            "--key2": "val2"})
        self.assertEqual("val1", args["--key1"])
        self.assertEqual("val2", args["--key2"])
        self.assertNotIn("key1", args)

    def test_extra_vars_as_a_list(self):
        args = playbooks.get_command_args({
            "extraVars": ["key1=var1", "key2=var2"]})

        expected = json.loads('{"key1": "var1", "key2": "var2"}')
        actual = json.loads(args["--extra-vars"])
        self.assertEqual(expected, actual)

    def test_extra_vars_as_a_dict(self):
        d = {"key1": "var1", "key2": "var2"}
        args = playbooks.get_command_args({"extraVars": d})
        actual = json.loads(args["--extra-vars"])
        self.assertEqual(d, actual)

    def test_default_inventory(self):
        args = playbooks.get_command_args({"foo": "bar"})
        self.assertEqual("hosts/verb_hosts", args['--inventory'])

    def test_pre_inventory(self):
        args = playbooks.get_command_args({"foo": "bar"},
                                          CONF.paths.pre_playbooks_dir)
        self.assertEqual("hosts/localhost", args['--inventory'])

    def test_force_omit_inventory(self):
        args = playbooks.get_command_args({'inventory': None})
        self.assertNotIn('--inventory', args)

    def test_override_inventory(self):
        args = playbooks.get_command_args({'--inventory': 'foo'})
        self.assertEqual("foo", args['--inventory'])

    def test_encryption_key(self):
        key = "blahblahblah"
        args = playbooks.get_command_args({'encryption-key': key})
        self.assertNotIn('--encryption-key', args)
        self.assertIn('--vault-password-file', args)

    def test_has_no_verbose(self):
        args = playbooks.get_command_args({"verbose": "0"})
        self.assertNotIn("--verbose", args)

    def test_has_verbose(self):
        args = playbooks.get_command_args({"verbose": "4"})
        self.assertEqual("4", args['--verbose'])

    def test_verbose_command(self):
        args = playbooks.get_command_args({"verbose": "3"})
        cmdline = playbooks.build_command_line('testcommand', 'testplaybook',
                                               args)

        num = cmdline.count('--verbose')
        self.assertTrue(num == 3)
