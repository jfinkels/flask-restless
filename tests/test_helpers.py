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


def load_tests(loader, standard_tests, pattern):
    """Returns the test suite for this module."""
    suite = TestSuite()
    suite.addTest(loader.loadTestsFromTestCase(HelpersTest))
    return suite
