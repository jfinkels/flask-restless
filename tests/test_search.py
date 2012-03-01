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
from flaskext.restless.search import SearchParameters
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


class QueryCreationTest(TestSupport):
    """Unit tests for the :func:`flaskext.restless.search.create_query`
    function.

    """

    def setUp(self):
        """Creates some objects and adds them to the database."""
        super(QueryCreationTest, self).setUp()
        lincoln = Person(name=u'Lincoln', age=23, other=22)
        mary = Person(name=u'Mary', age=19, other=19)
        lucy = Person(name=u'Lucy', age=25, other=20)
        katy = Person(name=u'Katy', age=7, other=10)
        john = Person(name=u'John', age=28, other=10)
        self.people = [lincoln, mary, lucy, katy, john]
        for person in self.people:
            session.add(person)
        session.commit()

    def test_empty_search(self):
        """Tests that a query with no search parameters returns everything."""
        query = create_query(Person, {})
        self.assertEqual(query.all(), self.people)

    def test_dict_same_as_search_params(self):
        """Tests that creating a query using a dictionary results in the same
        query as creating one using a
        :class:`flaskext.restless.search.SearchParameters` object.

        """
        d = {'filters': [{'name': 'name', 'val': u'%y%', 'op': 'like'}]}
        s = SearchParameters.from_dictionary(d)
        query_d = create_query(Person, d)
        query_s = create_query(Person, s)
        self.assertEqual(query_d.all(), query_s.all())

    def test_basic_query(self):
        """Tests for basic query correctness."""
        d = {'filters': [{'name': 'name', 'val': u'%y%', 'op': 'like'}]}
        query = create_query(Person, d)
        self.assertEqual(query.count(), 3)  # Mary, Lucy and Katy

        d = {'filters': [{'name': 'name', 'val': u'Lincoln', 'op': 'equals'}]}
        query = create_query(Person, d)
        self.assertEqual(query.count(), 1)
        self.assertEqual(query.one().name, 'Lincoln')

        d = {'filters': [{'name': 'name', 'val': u'Bogus', 'op': 'equals'}]}
        query = create_query(Person, d)
        self.assertEqual(query.count(), 0)

        d = {'order_by': [{'field': 'age', 'direction': 'asc'}]}
        query = create_query(Person, d)
        ages = [p.age for p in query]
        self.assertEqual(ages, [7, 19, 23, 25, 28])

        d = {'filters': [{'name': 'age', 'val': [7, 28], 'op': 'in'}]}
        query = create_query(Person, d)
        ages = [p.age for p in query]
        self.assertEqual(ages, [7, 28])

    def test_query_related_field(self):
        """Test for making a query with respect to a related field."""
        # add a computer to person 1
        computer = Computer(name=u'turing', vendor=u'Dell')
        p1 = Person.get_by(id=1)
        p1.computers.append(computer)
        session.commit()

        d = {'filters': [{'name': 'computers__name', 'val': u'turing',
                          'op': 'any'}]}
        query = create_query(Person, d)
        self.assertEqual(query.count(), 1)
        self.assertEqual(query.one().computers[0].name, 'turing')

        d = {'filters': [{'name': 'age', 'op': 'lte', 'field': 'other'}],
            'order_by': [{'field': 'other'}]}
        query = create_query(Person, d)
        self.assertEqual(query.count(), 2)
        results = query.all()
        self.assertEqual(results[0].other, 10)
        self.assertEqual(results[1].other, 19)


class FunctionEvaluationTest(TestSupport):
    """Unit tests for the :func:`flaskext.restless.search.evaluate_functions`
    function.

    """
    pass


class SearchTest(TestSupport):
    """Unit tests for the :func:`flaskext.restless.search.search` function.

    """
    pass
