"""
    Flask-Restless unit tests
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    Provides unit tests for modules in the :mod:`flask_restless` package.

    The :func:`suite` function returns a test suite containing all tests in
    this package.

    If you have Python 2.7, run the full test suite from the command-line like
    this::

        python -m tests

    If you have Python 2.6 or earlier, run the full test suite from the
    command-line like this::

        python -m tests.__main__

    Otherwise, you can just use the :file:`setup.py` script::

        python setup.py test

    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
from unittest2 import TestSuite
from unittest2 import defaultTestLoader

from . import test_exceptions
from . import test_helpers
from . import test_manager
from . import test_search
from . import test_validation
from . import test_views
from . import test_processors


def suite():
    """Returns the test suite for this module."""
    result = TestSuite()
    loader = defaultTestLoader
    result.addTest(loader.loadTestsFromModule(test_exceptions))
    result.addTest(loader.loadTestsFromModule(test_helpers))
    result.addTest(loader.loadTestsFromModule(test_manager))
    result.addTest(loader.loadTestsFromModule(test_search))
    result.addTest(loader.loadTestsFromModule(test_validation))
    result.addTest(loader.loadTestsFromModule(test_views))
    result.addTest(loader.loadTestsFromModule(test_processors))
    return result
