import json
import unittest

from .. import playbooks


class TestArgProcessing(unittest.TestCase):

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
