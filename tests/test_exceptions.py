"""
    tests.test_exceptions
    ~~~~~~~~~~~~~~~~~~~~~

    Provides unit tests for the :mod:`flask_restless.exceptions` module.

    :copyright: 2013 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
from flask import Flask

from flask.ext.restless.exceptions import json_abort


class TestHeaders(object):
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
        assert 404 == response.status_code
        assert 'application/json' == response.headers['Content-Type']
