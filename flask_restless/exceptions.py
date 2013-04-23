"""
    flask.ext.restless.exceptions
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Provides helper functions for creating exception responses.

    :copyright: 2013 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
from werkzeug.exceptions import default_exceptions
from flask import abort
from flask import make_response
from flask.exceptions import JSONHTTPException


# Adapted from http://flask.pocoo.org/snippets/97
def json_abort(status_code, body=None, headers=None):
    """Same as :func:`flask.abort` but with a JSON response."""
    bases = [JSONHTTPException]
    # Add Werkzeug base class.
    if status_code in default_exceptions:
        bases.insert(0, default_exceptions[status_code])
    error_cls = type('JSONHTTPException', tuple(bases), dict(code=status_code))
    abort(make_response(error_cls(body), status_code, headers or {}))
