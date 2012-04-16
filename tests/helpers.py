"""
    tests.helpers
    ~~~~~~~~~~~~~

    Provides helper functions for unit tests in this package.

    New test modules whose test classes inherit from :class:`TestSupport` must
    import the :func:`setUpModule` and :func:`tearDownModule` functions, which
    create and destroy a file for a test database, respectively, from this
    module::

        from .helpers import setUpModule
        from .helpers import tearDownModule

    This makes :mod:`unittest` execute these functions once per test module,
    which saves some disk usage and should theoretically cause the tests to run
    more quickly.

    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
import datetime
import os
import tempfile
from unittest2 import TestCase

from flask import Flask
from sqlalchemy import Column
from sqlalchemy import create_engine
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Unicode
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker

from flask.ext.restless import APIManager

#: The file descriptor and filename of the database which will be used in the
#: tests.
DB = dict(fd=None, filename=None)


def setUpModule():
    """Creates a temporary file which will contain the database to use in the
    tests.

    """
    DB['fd'], DB['filename'] = tempfile.mkstemp()


def tearDownModule():
    """Closes and unlinks the database file used in the tests."""
    if DB['fd']:
        os.close(DB['fd'])
        DB['fd'] = None
    if DB['filename']:
        os.unlink(DB['filename'])
        DB['filename'] = None


class FlaskTestBase(TestCase):
    """Base class for tests which use a Flask application."""

    def setUp(self):
        """Creates the Flask application and the APIManager."""
        super(FlaskTestBase, self).setUp()

        # create the Flask application
        app = Flask(__name__)
        app.config['DEBUG'] = True
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///%s' % DB['filename']
        self.flaskapp = app

        # create the test client
        self.app = app.test_client()


class TestSupport(FlaskTestBase):
    """Base class for tests which use a database and have an
    :class:`flask_restless.APIManager` with a :class:`flask.Flask` app object.

    The test client for the :class:`flask.Flask` application is accessible to
    test functions at ``self.app`` and the :class:`flask_restless.APIManager`
    is accessible at ``self.manager``.

    """

    def setUp(self):
        """Creates the Flask application and the APIManager."""
        super(TestSupport, self).setUp()

        # initialize SQLAlchemy and Flask-Restless
        app = self.flaskapp
        engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'],
                               convert_unicode=True)
        self.Session = sessionmaker(autocommit=False, autoflush=False,
                                    bind=engine)
        self.session = scoped_session(self.Session)
        self.Base = declarative_base()
        self.Base.metadata.bind = engine
        #Base.query = self.session.query_property()
        self.manager = APIManager(app, self.session)

        # declare the models
        class Computer(self.Base):
            __tablename__ = 'computer'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode, unique=True)
            vendor = Column(Unicode)
            buy_date = Column(DateTime)
            owner_id = Column(Integer, ForeignKey('person.id'))

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode, unique=True)
            age = Column(Float)
            other = Column(Float)
            birth_date = Column(Date)
            computers = relationship('Computer',
                                     backref=backref('owner', lazy='dynamic'))
        self.Person = Person
        self.Computer = Computer

        # create all the tables required for the models
        self.Base.metadata.create_all()

    def tearDown(self):
        """Drops all tables from the temporary database."""
        #self.session.remove()
        self.Base.metadata.drop_all()


class TestSupportPrefilled(TestSupport):
    """Base class for tests which use a database and have an
    :class:`flask_restless.APIManager` with a :class:`flask.Flask` app object.

    The test client for the :class:`flask.Flask` application is accessible to
    test functions at ``self.app`` and the :class:`flask_restless.APIManager`
    is accessible at ``self.manager``.

    The database will be prepopulated with five ``Person`` objects. The list of
    these objects can be accessed at ``self.people``.

    """

    def setUp(self):
        """Creates the database, the Flask application, and the APIManager."""
        # create the database
        super(TestSupportPrefilled, self).setUp()
        # create some people in the database for testing
        lincoln = self.Person(name=u'Lincoln', age=23, other=22,
                              birth_date=datetime.date(1900, 1, 2))
        mary = self.Person(name=u'Mary', age=19, other=19)
        lucy = self.Person(name=u'Lucy', age=25, other=20)
        katy = self.Person(name=u'Katy', age=7, other=10)
        john = self.Person(name=u'John', age=28, other=10)
        self.people = [lincoln, mary, lucy, katy, john]
        self.session.add_all(self.people)
        self.session.commit()
