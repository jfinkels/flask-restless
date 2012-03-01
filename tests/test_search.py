# -*- coding: utf-8; Mode: Python -*-
#
# Copyright 2012 Jeffrey Finkelstein <jefrey.finkelstein@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Unit tests for the :mod:`flaskext.restless.search` module."""
import os
from tempfile import mkstemp
import unittest

from elixir import create_all
from elixir import drop_all
from elixir import session
from sqlalchemy import create_engine

from flaskext.restless.search import create_query
from flaskext.restless.search import evaluate_functions
from flaskext.restless.search import search
from .models import setup
from .models import Computer
from .models import Person


class TestSupport(unittest.TestCase):
    """Base class for tests in this module."""

    def setUp(self):
        """Creates the database and all necessary tables."""
        # set up the database
        self.db_fd, self.db_file = mkstemp()
        setup(create_engine('sqlite:///%s' % self.db_file))
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


class QueryCreationTest(unittest.TestCase):
    """Unit tests for the :func:`flaskext.restless.search.create_query`
    function.

    """
    pass


class FunctionEvaluationTest(unittest.TestCase):
    """Unit tests for the :func:`flaskext.restless.search.evaluate_functions`
    function.

    """
    pass


class SearchTest(unittest.TestCase):
    """Unit tests for the :func:`flaskext.restless.search.search` function.

    """
    pass
