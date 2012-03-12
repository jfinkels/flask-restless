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
"""Helper functions for unit tests in this package."""
import os
import tempfile
from unittest2 import TestCase

from elixir import create_all
from elixir import drop_all
from elixir import metadata
from elixir import session
from elixir import setup_all
from flask import Flask
from sqlalchemy import create_engine

from flask.ext.restless import APIManager

from .models import Person


class TestSupport(TestCase):
    """Base class for tests which use a database."""

    def setUp(self):
        """Creates the database and all necessary tables.

        """
        # set up the database
        self.db_fd, self.db_file = tempfile.mkstemp()
        metadata.bind = create_engine('sqlite:///%s' % self.db_file)
        metadata.bind.echo = False
        setup_all()
        create_all()
        session.commit()

    def tearDown(self):
        """Drops all tables from the temporary database and closes and unlink
        the temporary file in which it lived.

        """
        drop_all()
        session.commit()
        os.close(self.db_fd)
        os.unlink(self.db_file)


class TestSupportWithManager(TestSupport):
    """Base class for tests which use a database and have an
    :class:`flask_restless.APIManager` with a :class:`flask.Flask` app object.

    The test client for the :class:`flask.Flask` application is accessible to
    test functions at ``self.app`` and the :class:`flask_restless.APIManager`
    is accessible at ``self.manager``.

    """

    def setUp(self):
        """Creates the database, the Flask application, and the APIManager."""
        # create the database
        super(TestSupportWithManager, self).setUp()

        # create the Flask application
        app = Flask(__name__)
        app.config['DEBUG'] = True
        app.config['TESTING'] = True
        self.app = app.test_client()

        # setup the URLs for the Person API
        self.manager = APIManager(app)


class TestSupportWithManagerPrefilled(TestSupport):
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
        super(TestSupportWithManagerPrefilled, self).setUp()

        # create the Flask application
        app = Flask(__name__)
        app.config['DEBUG'] = True
        app.config['TESTING'] = True
        self.app = app.test_client()

        # setup the URLs for the Person API
        self.manager = APIManager(app)

        # create some people in the database for testing
        lincoln = Person(name=u'Lincoln', age=23, other=22)
        mary = Person(name=u'Mary', age=19, other=19)
        lucy = Person(name=u'Lucy', age=25, other=20)
        katy = Person(name=u'Katy', age=7, other=10)
        john = Person(name=u'John', age=28, other=10)
        self.people = [lincoln, mary, lucy, katy, john]
        for person in self.people:
            session.add(person)
        session.commit()


class TestSupportPrefilled(TestSupport):
    """Base class for tests which require a database pre-filled with some
    initial instances of the :class:`models.Person` class.

    """

    def setUp(self):
        """Adds some initial people to the database after creating and
        initializing it.

        """
        super(TestSupportPrefilled, self).setUp()
        # create some people in the database for testing
        lincoln = Person(name=u'Lincoln', age=23, other=22)
        mary = Person(name=u'Mary', age=19, other=19)
        lucy = Person(name=u'Lucy', age=25, other=20)
        katy = Person(name=u'Katy', age=7, other=10)
        john = Person(name=u'John', age=28, other=10)
        self.people = [lincoln, mary, lucy, katy, john]
        for person in self.people:
            session.add(person)
        session.commit()
