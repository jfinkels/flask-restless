"""
    tests.test_helpers
    ~~~~~~~~~~~~~~~~~~

    Provides unit tests for the :mod:`flask_restless.helpers` module.

    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
from unittest2 import TestCase
from unittest2 import TestSuite

from flask.ext.restless.helpers import partition
from flask.ext.restless.helpers import unicode_keys_to_strings
from flask.ext.restless.helpers import upper_keys


__all__ = ['HelpersTest']


class HelpersTest(TestCase):
    """Unit tests for the helper functions."""

    def test_partition(self):
        """Test for partitioning a list into two lists based on a given
        condition.

        """
        l = range(10)
        left, right = partition(l, lambda x: x < 5)
        self.assertEqual(list(range(5)), left)
        self.assertEqual(list(range(5, 10)), right)

    def test_unicode_keys_to_strings(self):
        """Test for converting keys of a dictionary from ``unicode`` to
        ``string`` objects.

        """
        for k in unicode_keys_to_strings({u'x': 1, u'y': 2, u'z': 3}):
            self.assertIsInstance(k, str)

    def test_upper_keys(self):
        """Test for converting keys in a dictionary to upper case."""
        for k, v in upper_keys(dict(zip('abc', 'xyz'))).items():
            self.assertTrue(k.isupper())
            self.assertFalse(v.isupper())


def load_tests(loader, standard_tests, pattern):
    """Returns the test suite for this module."""
    suite = TestSuite()
    suite.addTest(loader.loadTestsFromTestCase(HelpersTest))
    return suite
