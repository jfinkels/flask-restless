# -*- coding: utf-8; Mode: Python -*-
#
# Copyright (C) 2011 Lincoln de Sousa <lincoln@comum.org>
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
"""Unit tests for the :mod:`flask_restless.model` module."""
from datetime import date
from datetime import datetime
from unittest2 import TestSuite

from elixir import session

from flask.ext.restless.model import ISO8601_DATE

from .helpers import TestSupport
from .models import Computer
from .models import Person


__all__ = ['EntityTestCase']


class EntityTestCase(TestSupport):
    """Unit tests for the :class:`flask_restless.model.Entity` class."""

    def setUp(self):
        """Creates a SQLite database in a temporary file and creates and sets
        up all the necessary tables.

        """
        super(EntityTestCase, self).setUp()
        self.model = Person

    def test_column_introspection(self):
        """Test for getting the names of columns as strings.

        """
        columns = self.model.get_columns()
        self.assertEqual(sorted(columns.keys()), sorted(['age', 'birth_date',
                                                         'computers', 'id',
                                                         'name', 'other']))
        relations = Person.get_relations()
        self.assertEqual(relations, ['computers'])

    def test_date_serialization(self):
        """Tests that date objects in the database are correctly serialized in
        the :meth:`flask_restless.model.Entity.to_dict` method.

        """
        person = self.model()
        person.birth_date = date(1986, 9, 15)
        session.commit()
        persondict = person.to_dict()
        self.assertIn('birth_date', persondict)
        self.assertEqual(persondict['birth_date'],
                         person.birth_date.strftime(ISO8601_DATE))

    def test_datetime_serialization(self):
        """Tests that datetime objects in the database are correctly serialized
        in the :meth:`flask_restless.model.Entity.to_dict` method.

        """
        computer = Computer()
        computer.buy_date = datetime.now()
        session.commit()
        computerdict = computer.to_dict()
        self.assertIn('buy_date', computerdict)
        self.assertEqual(computerdict['buy_date'],
                         computer.buy_date.strftime(ISO8601_DATE))

    def test_to_dict(self):
        """Test for serializing attributes of an instance of the model by the
        :meth:`flask_restless.model.Entity.to_dict` method.

        """
        me = self.model()
        me.name = u'Lincoln'
        me.age = 24
        me.birth_date = date(1986, 9, 15)
        session.commit()

        me_dict = me.to_dict()
        self.assertEqual(sorted(me_dict.keys()), sorted(['birth_date', 'age',
                                                         'id', 'name',
                                                         'other']))
        self.assertEqual(me_dict['name'], u'Lincoln')
        self.assertEqual(me_dict['age'], 24)
        self.assertEqual(me_dict['birth_date'],
                         me.birth_date.strftime(ISO8601_DATE))

    def test_to_dict_deep(self):
        """Tests that fields corresponding to related model instances are
        correctly serialized by the
        :meth:`flask_restless.model.Entity.to_dict` method.

        """
        someone = self.model()
        someone.name = u'John'
        someone.age = 25
        computer1 = Computer()
        computer1.name = u'lixeiro'
        computer1.vendor = u'Lemote'
        computer1.owner = someone
        computer1.buy_date = datetime.now()
        session.commit()

        relations = Person.get_relations()
        deep = dict(zip(relations, [{}] * len(relations)))

        computers = someone.to_dict(deep)['computers']
        self.assertEqual(len(computers), 1)
        self.assertEqual(computers[0]['name'], u'lixeiro')
        self.assertEqual(computers[0]['vendor'], u'Lemote')

    def test_get_or_create(self):
        """Test for :meth:`flask_restless.model.Entity.get_or_create()`."""
        # Here we're sure that we have a fresh table with no rows, so
        # let's create the first one:
        instance, created = self.model.get_or_create(name=u'Lincoln', age=24)
        self.assertTrue(created)
        self.assertEqual(instance.name, u'Lincoln')
        self.assertEqual(instance.age, 24)

        # Now that we have a row, let's try to get it again
        second_instance, created = self.model.get_or_create(name=u'Lincoln')
        self.assertFalse(created)
        self.assertEqual(second_instance.name, u'Lincoln')
        self.assertEqual(second_instance.age, 24)


def load_tests(loader, standard_tests, pattern):
    """Returns the test suite for this module."""
    suite = TestSuite()
    suite.addTest(loader.loadTestsFromTestCase(EntityTestCase))
    return suite
