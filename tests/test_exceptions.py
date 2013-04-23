"""
    tests.test_exceptions
    ~~~~~~~~~~~~~~~~~~~~~

    Provides unit tests for the :mod:`flask_restless.exceptions` module.

    :copyright: 2013 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
from unittest2 import TestSuite
from unittest2 import TestCase

from flask import Flask

from flask.ext.restless.exceptions import json_abort


class ExceptionsTest(TestCase):
    """Unit tests for the :mod:`flask_restless.exceptions` module."""

    def test_json_abort(self):
        """Tests that the :func:`flask_restless.exceptions.json_abort` function
        aborts with a JSON Content-Type.

        """
        app = Flask(__name__)

        @app.route('/')
        def test():
            json_abort(404)

        client = app.test_client()
        response = client.get('/')
        self.assertEqual(404, response.status_code)
        self.assertEqual('application/json', response.headers['Content-Type'])


def load_tests(loader, standard_tests, pattern):
    """Returns the test suite for this module."""
    suite = TestSuite()
    suite.addTest(loader.loadTestsFromTestCase(ExceptionsTest))
    return suite
