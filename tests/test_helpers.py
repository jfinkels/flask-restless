"""
    tests.test_helpers
    ~~~~~~~~~~~~~~~~~~

    Provides unit tests for the :mod:`flask_restless.helpers` module.

    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
from __future__ import with_statement

from datetime import date
from datetime import datetime

from sqlalchemy.exc import OperationalError
from unittest2 import TestCase
from unittest2 import TestSuite

from flask.ext.restless.helpers import evaluate_functions
from flask.ext.restless.helpers import get_columns
from flask.ext.restless.helpers import get_relations
from flask.ext.restless.helpers import partition
from flask.ext.restless.helpers import primary_key_name
from flask.ext.restless.helpers import to_dict
from flask.ext.restless.helpers import unicode_keys_to_strings
from flask.ext.restless.helpers import upper_keys

from .helpers import TestSupport
from .helpers import TestSupportPrefilled


__all__ = ['HelpersTest', 'ModelHelpersTest', 'FunctionEvaluationTest']


class HelpersTest(TestCase):
    """Unit tests for the helper functions."""

    def test_unicode_keys_to_strings(self):
        """Test for converting keys of a dictionary from ``unicode`` to
        ``string`` objects.

        """
        for k in unicode_keys_to_strings({u'x': 1, u'y': 2, u'z': 3}):
            self.assertIsInstance(k, str)

    def test_partition(self):
        """Test for partitioning a list into two lists based on a given
        condition.

        """
        l = range(10)
        left, right = partition(l, lambda x: x < 5)
        self.assertEqual(list(range(5)), left)
        self.assertEqual(list(range(5, 10)), right)

    def test_upper_keys(self):
        """Test for converting keys in a dictionary to upper case."""
        for k, v in upper_keys(dict(zip('abc', 'xyz'))).items():
            self.assertTrue(k.isupper())
            self.assertFalse(v.isupper())


class ModelHelpersTest(TestSupport):
    """Provides tests for helper functions which operate on pure SQLAlchemy
    models.

    """

    def test_date_serialization(self):
        """Tests that date objects in the database are correctly serialized in
        the :meth:`flask_restless.model.Entity.to_dict` method.

        """
        person = self.Person(birth_date=date(1986, 9, 15))
        self.session.commit()
        d = to_dict(person)
        self.assertIn('birth_date', d)
        self.assertEqual(d['birth_date'], person.birth_date.isoformat())

    def test_datetime_serialization(self):
        """Tests that datetime objects in the database are correctly serialized
        in the :meth:`flask_restless.model.Entity.to_dict` method.

        """
        computer = self.Computer(buy_date=datetime.now())
        self.session.commit()
        d = to_dict(computer)
        self.assertIn('buy_date', d)
        self.assertEqual(d['buy_date'], computer.buy_date.isoformat())

    def testto_dict(self):
        """Test for serializing attributes of an instance of the model by the
        :meth:`flask_restless.model.Entity.to_dict` method.

        """
        me = self.Person(name=u'Lincoln', age=24, birth_date=date(1986, 9, 15))
        self.session.commit()

        me_dict = to_dict(me)
        expectedfields = sorted(['birth_date', 'age', 'id', 'name',
            'other', 'is_minor'])
        self.assertEqual(sorted(me_dict), expectedfields)
        self.assertEqual(me_dict['name'], u'Lincoln')
        self.assertEqual(me_dict['age'], 24)
        self.assertEqual(me_dict['birth_date'], me.birth_date.isoformat())

    def test_primary_key_name(self):
        """Test for determining the primary attribute of a model or instance.

        """
        me = self.Person(name=u'Lincoln', age=24, birth_date=date(1986, 9, 15))
        self.assertEqual('id', primary_key_name(me))
        self.assertEqual('id', primary_key_name(self.Person))
        self.assertEqual('id', primary_key_name(self.Star))

    def testto_dict_dynamic_relation(self):
        """Tests that a dynamically queried relation is resolved when getting
        the dictionary representation of an instance of a model.

        """
        person = self.LazyPerson(name='Lincoln')
        self.session.add(person)
        computer = self.LazyComputer(name='lixeiro')
        self.session.add(computer)
        person.computers.append(computer)
        self.session.commit()
        person_dict = to_dict(person, deep={'computers': []})
        computer_dict = to_dict(computer, deep={'owner': None})
        self.assertEqual(sorted(person_dict), ['computers', 'id', 'name'])
        self.assertFalse(isinstance(computer_dict['owner'], list))
        self.assertEqual(sorted(computer_dict), ['id', 'name', 'owner',
                                                 'ownerid'])
        expected_person = to_dict(person)
        expected_computer = to_dict(computer)
        self.assertEqual(person_dict['computers'], [expected_computer])
        self.assertEqual(computer_dict['owner'], expected_person)

    def testto_dict_deep(self):
        """Tests that fields corresponding to related model instances are
        correctly serialized by the
        :meth:`flask_restless.model.Entity.to_dict` method.

        """
        now = datetime.now()
        someone = self.Person(name=u'John', age=25)
        computer = self.Computer(name=u'lixeiro', vendor=u'Lemote',
                                 buy_date=now)
        someone.computers.append(computer)
        self.session.commit()

        deep = {'computers': []}
        computers = to_dict(someone, deep)['computers']
        self.assertEqual(len(computers), 1)
        self.assertEqual(computers[0]['name'], u'lixeiro')
        self.assertEqual(computers[0]['vendor'], u'Lemote')
        self.assertEqual(computers[0]['buy_date'], now.isoformat())
        self.assertEqual(computers[0]['owner_id'], someone.id)

    def testto_dict_hybrid_property(self):
        """Tests that hybrid properties are correctly serialized."""
        young = self.Person(name=u'John', age=15)
        old = self.Person(name=u'Sally', age=25)
        self.session.commit()

        self.assertTrue(to_dict(young)['is_minor'])
        self.assertFalse(to_dict(old)['is_minor'])

    def test_get_columns(self):
        """Test for getting the names of columns as strings."""
        columns = get_columns(self.Person)
        self.assertEqual(sorted(columns.keys()), sorted(['age', 'birth_date',
                                                         'computers', 'id',
                                                         'is_minor', 'name',
                                                         'other']))

    def test_get_relations(self):
        """Tests getting the names of the relations of a model as strings."""
        relations = get_relations(self.Person)
        self.assertEqual(relations, ['computers'])


class FunctionEvaluationTest(TestSupportPrefilled):
    """Unit tests for the :func:`flask.ext.restless.helpers.evaluate_functions`
    function.

    """

    def test_basic_evaluation(self):
        """Tests for basic function evaluation."""
        # test for no model
        result = evaluate_functions(self.session, None, [])
        self.assertEqual(result, {})

        # test for no functions
        result = evaluate_functions(self.session, self.Person, [])
        self.assertEqual(result, {})

        # test for summing ages
        functions = [{'name': 'sum', 'field': 'age'}]
        result = evaluate_functions(self.session, self.Person, functions)
        self.assertIn('sum__age', result)
        self.assertEqual(result['sum__age'], 102.0)

        # test for multiple functions
        functions = [{'name': 'sum', 'field': 'age'},
                     {'name': 'avg', 'field': 'other'}]
        result = evaluate_functions(self.session, self.Person, functions)
        self.assertIn('sum__age', result)
        self.assertEqual(result['sum__age'], 102.0)
        self.assertIn('avg__other', result)
        self.assertEqual(result['avg__other'], 16.2)

    def test_count(self):
        """Tests for counting the number of rows in a query."""
        functions = [{'name': 'count', 'field': 'id'}]
        result = evaluate_functions(self.session, self.Person, functions)
        self.assertIn('count__id', result)
        self.assertEqual(result['count__id'], 5)

    def test_poorly_defined_functions(self):
        """Tests that poorly defined functions raise errors."""
        # test for unknown field
        functions = [{'name': 'sum', 'field': 'bogus'}]
        with self.assertRaises(AttributeError):
            evaluate_functions(self.session, self.Person, functions)

        # test for unknown function
        functions = [{'name': 'bogus', 'field': 'age'}]
        with self.assertRaises(OperationalError):
            evaluate_functions(self.session, self.Person, functions)


def load_tests(loader, standard_tests, pattern):
    """Returns the test suite for this module."""
    suite = TestSuite()
    suite.addTest(loader.loadTestsFromTestCase(HelpersTest))
    suite.addTest(loader.loadTestsFromTestCase(ModelHelpersTest))
    suite.addTest(loader.loadTestsFromTestCase(FunctionEvaluationTest))
    return suite
