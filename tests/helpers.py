# -*- coding: utf-8; Mode: Python -*-
#
# Copyright 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
#
# This file is part of Flask-Restless.
#
# Flask-Restless is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# Flask-Restless is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Flask-Restless. If not, see <http://www.gnu.org/licenses/>.
"""Helper functions for unit tests in this package.

New test modules whose test classes inherit from :class:`TestSupport` must
import the :func:`setUpModule` and :func:`tearDownModule` functions, which
create and destroy a file for a test database, respectively, from this module::

    from .helpers import setUpModule
    from .helpers import tearDownModule

This makes :mod:`unittest` execute these functions once per test module, which
saves some disk usage and should theoretically cause the tests to run more
quickly.

"""
import datetime
import os
import tempfile
from unittest2 import TestCase

from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy

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


class TestSupport(TestCase):
    """Base class for tests which use a database and have an
    :class:`flask_restless.APIManager` with a :class:`flask.Flask` app object.

    The test client for the :class:`flask.Flask` application is accessible to
    test functions at ``self.app`` and the :class:`flask_restless.APIManager`
    is accessible at ``self.manager``.

    """

    def setUp(self):
        """Creates the Flask application and the APIManager."""
        # create the Flask application
        app = Flask(__name__)
        app.config['DEBUG'] = True
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///%s' % DB['filename']
        self.flaskapp = app

        # initialize Flask-SQLAlchemy and Flask-Restless
        self.db = SQLAlchemy(app)
        self.manager = APIManager(app, self.db)

        # for the sake of brevity...
        db = self.db

        # declare the models
        class Computer(db.Model):
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.Unicode, unique=True)
            vendor = db.Column(db.Unicode)
            buy_date = db.Column(db.DateTime)
            owner_id = db.Column(db.Integer, db.ForeignKey('person.id'))

        class Person(db.Model):
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.Unicode, unique=True)
            age = db.Column(db.Float)
            other = db.Column(db.Float)
            birth_date = db.Column(db.Date)
            computers = db.relationship('Computer',
                                        backref=db.backref('owner',
                                                           lazy='dynamic'))
        self.Person = Person
        self.Computer = Computer

        # create all the tables required for the models
        self.db.create_all()

        # create the test client
        self.app = app.test_client()

    def tearDown(self):
        """Drops all tables from the temporary database."""
        self.db.drop_all()


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
        self.db.session.add_all(self.people)
        self.db.session.commit()
