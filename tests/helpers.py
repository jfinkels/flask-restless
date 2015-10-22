"""
    tests.helpers
    ~~~~~~~~~~~~~

    Provides helper functions for unit tests in this package.

    :copyright: 2012, 2013, 2014, 2015 Jeffrey Finkelstein
                <jeffrey.finkelstein@gmail.com> and contributors.
    :license: GNU AGPLv3+ or BSD

"""
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
import functools
from json import JSONEncoder
import sys
import types

from flask import Flask
from flask import json
try:
    from flask.ext import sqlalchemy as flask_sqlalchemy
except ImportError:
    has_flask_sqlalchemy = False
else:
    has_flask_sqlalchemy = True
from nose import SkipTest
from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session as SessionBase

from flask.ext.restless import APIManager
from flask.ext.restless import CONTENT_TYPE

dumps = json.dumps
loads = json.loads

#: The User-Agent string for Microsoft Internet Explorer 8.
#:
#: From <http://blogs.msdn.com/b/ie/archive/2008/02/21/the-internet-explorer-8-user-agent-string.aspx>.
MSIE8_UA = 'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 6.0; Trident/4.0)'

#: The User-Agent string for Microsoft Internet Explorer 9.
#:
#: From <http://blogs.msdn.com/b/ie/archive/2010/03/23/introducing-ie9-s-user-agent-string.aspx>.
MSIE9_UA = 'Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)'

#: Boolean representing whether this code is being executed on Python 2.
IS_PYTHON2 = (sys.version_info[0] == 2)

#: Tuple of objects representing types.
CLASS_TYPES = (types.TypeType, types.ClassType) if IS_PYTHON2 else (type, )


def isclass(obj):
    """Returns ``True`` if and only if the specified object is a type (or a
    class).

    """
    return isinstance(obj, CLASS_TYPES)


def skip_unless(condition, reason=None):
    """Decorator that skips `test` unless `condition` is ``True``.

    This is a replacement for :func:`unittest.skipUnless` that works with
    ``nose``. The argument ``reason`` is a string describing why the test was
    skipped.

    This decorator can be applied to functions, methods, or classes.

    """
    def skip(test):
        message = 'Skipped {0}: {1}'.format(test.__name__, reason)

        if isclass(test):
            for attr, val in test.__dict__.items():
                if callable(val) and not attr.startswith('__'):
                    setattr(test, attr, skip(val))
            return test

        @functools.wraps(test)
        def inner(*args, **kw):
            if not condition:
                raise SkipTest(message)
            return test(*args, **kw)
        return inner

    return skip


def skip(reason=None):
    """Unconditionally skip a test.

    This is a convenience function for ``skip_unless(False, reason)``.

    """
    return skip_unless(False, reason)


def unregister_fsa_session_signals():
    """Unregisters Flask-SQLAlchemy session commit and rollback signal
    handlers.

    When a Flask-SQLAlchemy object is created, it registers signal handlers for
    ``before_commit``, ``after_commit``, and ``after_rollback`` signals. In
    case of using both a plain SQLAlchemy session and a Flask-SQLAlchemy
    session (as is happening in the tests in this package), we need to
    unregister handlers or there will be some exceptions during test
    executions like::

        AttributeError: 'Session' object has no attribute '_model_changes'

    """
    if not has_flask_sqlalchemy:
        return
    events = flask_sqlalchemy._SessionSignalEvents
    signal_names = ('before_commit', 'after_commit', 'after_rollback')
    for signal_name in signal_names:
        signal = getattr(events, 'session_signal_{0}'.format(signal_name))
        event.remove(SessionBase, signal_name, signal)


def force_json_contenttype(test_client):
    """Ensures that all requests made by the specified Flask test client
    have the correct ``Content-Type`` header.

    For :http:method:`patch` requests, this means
    ``application/json-patch+json``. For all other requests, the content
    type is set to ``application/vnd.api+json``, unless another content
    type is explicitly specified at the time the method is invoked.

    """
    # Create a decorator for the test client request methods that adds a
    # JSON Content-Type by default if none is specified.
    def set_content_type(func):
        @functools.wraps(func)
        def new_func(*args, **kw):
            #if 'content_type' not in kw:
            #    kw['content_type'] = CONTENT_TYPE
            if 'headers' not in kw:
                kw['headers'] = dict()
            headers = kw['headers']
            if (isinstance(headers, dict) and 'Accept' not in headers
                or isinstance(headers, list) and all(x[0] != 'Accept'
                                                     for x in headers)):
                headers['Accept'] = CONTENT_TYPE
            if 'content_type' not in kw and 'Content-Type' not in headers:
                kw['content_type'] = CONTENT_TYPE
            return func(*args, **kw)
        return new_func

    for methodname in ('get', 'patch', 'post', 'delete'):
        # Decorate the original test client request method.
        old_method = getattr(test_client, methodname)
        setattr(test_client, methodname, set_content_type(old_method))
    # # PATCH methods need to have `application/json-patch+json` content type.
    # test_client.patch = set_content_type(test_client.patch,
    #                                      'application/json-patch+json')


# In versions of Flask before 1.0, datetime and time objects are not
# serializable by default so we need to create a custom JSON encoder class.
#
# TODO When Flask 1.0 is required, remove this.
class BetterJSONEncoder(JSONEncoder):
    """Extends the default JSON encoder to serialize objects from the
    :mod:`datetime` module.

    """

    def default(self, obj):
        if isinstance(obj, (date, datetime, time)):
            return obj.isoformat()
        if isinstance(obj, timedelta):
            return int(obj.days * 86400 + obj.seconds)
        return super(BetterJSONEncoder, self).default(obj)


class FlaskTestBase(object):
    """Base class for tests which use a Flask application.

    The Flask test client can be accessed at ``self.app``. The Flask
    application itself is accessible at ``self.flaskapp``.

    """

    def setUp(self):
        """Creates the Flask application and the APIManager."""
        # create the Flask application
        app = Flask(__name__)
        app.config['DEBUG'] = True
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
        # This is required by `manager.url_for()` in order to construct
        # absolute URLs.
        app.config['SERVER_NAME'] = 'localhost'
        app.logger.disabled = True
        # Set the default JSON Encoder to serialize more things.
        app.json_encoder = BetterJSONEncoder
        self.flaskapp = app

        # create the test client
        self.app = app.test_client()

        force_json_contenttype(self.app)


class DatabaseTestBase(FlaskTestBase):
    """Base class for tests that use a SQLAlchemy database.

    The :meth:`setUp` method does the necessary SQLAlchemy initialization, and
    the subclasses should populate the database with models and then create the
    database (by calling ``self.Base.metadata.create_all()``).

    """

    def setUp(self):
        """Initializes the components necessary for models in a SQLAlchemy
        database.

        """
        super(DatabaseTestBase, self).setUp()
        # initialize SQLAlchemy
        app = self.flaskapp
        engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'],
                               convert_unicode=True)
        self.Session = sessionmaker(autocommit=False, autoflush=False,
                                    bind=engine)
        self.session = scoped_session(self.Session)
        self.Base = declarative_base()
        self.Base.metadata.bind = engine

    def tearDown(self):
        """Drops all tables from the temporary database."""
        self.session.remove()
        self.Base.metadata.drop_all()


class ManagerTestBase(DatabaseTestBase):
    """Base class for tests that use a SQLAlchemy database and an
    :class:`flask_restless.APIManager`.

    The :class:`flask_restless.APIManager` is accessible at ``self.manager``.

    """

    def setUp(self):
        """Initializes an instance of :class:`flask.ext.restless.APIManager`.

        """
        super(ManagerTestBase, self).setUp()
        self.manager = APIManager(self.flaskapp, session=self.session)
