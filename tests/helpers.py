"""
    tests.helpers
    ~~~~~~~~~~~~~

    Provides helper functions for unit tests in this package.

    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
import datetime

from flask import Flask
from nose import SkipTest
from sqlalchemy import Column
from sqlalchemy import create_engine
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Boolean
from sqlalchemy import Unicode
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker

from flask.ext.restless import APIManager


def skip_unless(condition, reason=None):
    """Decorator that skips `test` unless `condition` is ``True``.

    This is a replacement for :func:`unittest.skipUnless` that works with
    ``nose``. The argument ``reason`` is a string describing why the test was
    skipped.

    """
    def skip(test):
        message = 'Skipped %s: %s' % (test.__name__, reason)

        # TODO Since we don't check the case in which `test` is a class, the
        # result of running the tests will be a single skipped test, although
        # it should show one skip for each test method within the class.
        def inner(*args, **kw):
            if not condition:
                raise SkipTest(message)
            return test(*args, **kw)
        inner.__name__ = test.__name__
        return inner
    return skip


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
        app.logger.disabled = True
        self.flaskapp = app

        # create the test client
        self.app = app.test_client()

        # Ensure that all requests have Content-Type set to "application/json"
        # unless otherwise specified.
        for methodname in ('get', 'put', 'patch', 'post', 'delete'):
            # Create a decorator for the test client request methods that adds
            # a JSON Content-Type by default if none is specified.
            def set_content_type(func):
                def new_func(*args, **kw):
                    if 'content_type' not in kw:
                        kw['content_type'] = 'application/json'
                    return func(*args, **kw)
                return new_func
            # Decorate the original test client request method.
            old_method = getattr(self.app, methodname)
            setattr(self.app, methodname, set_content_type(old_method))


class DatabaseTestBase(FlaskTestBase):
    """Base class for tests which use a database and have an
    :class:`flask_restless.APIManager`.

    The :meth:`setUp` method does the necessary SQLAlchemy initialization, and
    the subclasses should populate the database with models and then create the
    database (by calling ``self.Base.metadata.create_all()``).

    The :class:`flask_restless.APIManager` is accessible at ``self.manager``.

    """

    def setUp(self):
        """Initializes the components necessary for models in a SQLAlchemy
        database, as well as for Flask-Restless.

        """
        super(DatabaseTestBase, self).setUp()

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


class TestSupport(DatabaseTestBase):
    """Base class for test cases which use a database with some basic models.

    """

    def setUp(self):
        """Creates some example models and creates the database tables."""
        super(TestSupport, self).setUp()

        # declare the models
        class Program(self.Base):
            __tablename__ = 'program'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode, unique=True)

        class ComputerProgram(self.Base):
            __tablename__ = 'computer_program'
            computer_id = Column(Integer, ForeignKey('computer.id'),
                                                     primary_key=True)
            program_id = Column(Integer, ForeignKey('program.id'),
                                                    primary_key=True)
            licensed = Column(Boolean, default=False)
            program = relationship('Program')

        class Computer(self.Base):
            __tablename__ = 'computer'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode, unique=True)
            vendor = Column(Unicode)
            buy_date = Column(DateTime)
            owner_id = Column(Integer, ForeignKey('person.id'))
            owner = relationship('Person')
            programs = relationship('ComputerProgram', cascade="all, delete-orphan")

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode, unique=True)
            age = Column(Float)
            other = Column(Float)
            birth_date = Column(Date)
            computers = relationship('Computer')

            @hybrid_property
            def is_minor(self):
                return self.age < 18

        class LazyComputer(self.Base):
            __tablename__ = 'lazycomputer'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)
            ownerid = Column(Integer, ForeignKey('lazyperson.id'))
            owner = relationship('LazyPerson',
                                 backref=backref('computers', lazy='dynamic'))

        class LazyPerson(self.Base):
            __tablename__ = 'lazyperson'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)

        class Planet(self.Base):
            __tablename__ = 'planet'
            name = Column(Unicode, primary_key=True)

        class Star(self.Base):
            __tablename__ = 'star'
            id = Column("star_id", Integer, primary_key=True)
            inception_time = Column(DateTime, nullable=True)

        class CarModel(self.Base):
            __tablename__ = 'car_model'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)
            seats = Column(Integer)

            manufacturer_id = Column(Integer,
                                     ForeignKey('car_manufacturer.id'))
            manufacturer = relationship('CarManufacturer')

        class CarManufacturer(self.Base):
            __tablename__ = 'car_manufacturer'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)
            models = relationship('CarModel')

        self.Person = Person
        self.Program = Program
        self.ComputerProgram = ComputerProgram
        self.LazyComputer = LazyComputer
        self.LazyPerson = LazyPerson
        self.Computer = Computer
        self.Planet = Planet
        self.Star = Star
        self.CarManufacturer = CarManufacturer
        self.CarModel = CarModel

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
