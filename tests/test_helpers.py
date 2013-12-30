"""
    tests.test_helpers
    ~~~~~~~~~~~~~~~~~~

    Provides unit tests for the :mod:`flask_restless.helpers` module.

    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
from datetime import date
from datetime import datetime
import uuid

from nose.tools import assert_raises
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Query, relationship
from sqlalchemy import Column, Integer, Unicode, ForeignKey

from flask.ext.restless.helpers import evaluate_functions
from flask.ext.restless.helpers import get_columns
from flask.ext.restless.helpers import get_relations
from flask.ext.restless.helpers import partition
from flask.ext.restless.helpers import primary_key_name
from flask.ext.restless.helpers import to_dict
from flask.ext.restless.helpers import upper_keys
from flask.ext.restless.helpers import session_query
from flask.ext.restless.helpers import get_by

from .helpers import TestSupport
from .helpers import TestSupportPrefilled
from .helpers import DatabaseTestBase


class TestSessionQuery(DatabaseTestBase):
    """Unit test for the session_query function"""

    def setUp(self):
        """Creates example tables to test the various behaviours of session_query()

        """
        super(TestSessionQuery, self).setUp()


        #declare models
        class WithCallable(self.Base):
            __tablename__ = 'with_callable'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode, unique=True)

            @classmethod
            def query(model):
              return WithCallable


        class WithoutCallable(self.Base):
            __tablename__ = 'without_callable'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode, unique=True)


        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode, unique=True)
            family_id = Column(Integer, ForeignKey('family.id'))
            family = relationship('Family')

            @classmethod
            def query(cls):
              return self.session.query(Person).join((Family, Person.family_id == Family.id))

        class Family(self.Base):
            __tablename__ = 'family'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode, unique=True)
            persons = relationship('Person')

        self.WithCallable = WithCallable
        self.WithoutCallable = WithoutCallable
        self.Person = Person
        self.Family = Family

        # create all the tables required for the models
        self.Base.metadata.create_all()

    def test_with_callable(self):
        assert session_query(self.session, self.WithCallable) == self.WithCallable

    def test_without_callable(self):
        assert type(session_query(self.session, self.WithoutCallable)) == Query

    def test_get_by(self):
        """Tests if get_by works correct given multiple types of queries

        """
        family = self.Family(name='Test Family')
        self.session.add(family)

        persons = map(lambda n: self.Person(name='Person %i' %n, family=family) ,range(0, 100))
        map(lambda person: self.session.add(person), persons)

        self.session.commit()

        person = persons[-1]
        assert person.id, "Person needs to exist in the database with a valid id"

        family_test = get_by(self.session, self.Family, family.id)

        assert family_test, "Family not found"
        assert family_test.name == family.name, "Family name needs to be the same"
        assert family_test.id == family.id, "Family id needs to be the same"


        person_test = get_by(self.session, self.Person, person.id)

        assert person_test, "No person found"
        assert person.id == person_test.id, "Person id must match, otherwise wrong match"
        assert person.name == person_test.name, "Should be the same name"

class TestHelpers(object):
    """Unit tests for the helper functions."""

    def test_partition(self):
        """Test for partitioning a list into two lists based on a given
        condition.

        """
        l = range(10)
        left, right = partition(l, lambda x: x < 5)
        assert list(range(5)) == left
        assert list(range(5, 10)) == right

    def test_upper_keys(self):
        """Test for converting keys in a dictionary to upper case."""
        for k, v in upper_keys(dict(zip('abc', 'xyz'))).items():
            assert k.isupper()
            assert not v.isupper()


class TestModelHelpers(TestSupport):
    """Provides tests for helper functions which operate on pure SQLAlchemy
    models.

    """

    def test_date_serialization(self):
        """Tests that date objects in the database are correctly serialized in
        the :func:`flask.ext.restless.helpers.to_dict` function.

        """
        person = self.Person(birth_date=date(1986, 9, 15))
        self.session.commit()
        d = to_dict(person)
        assert 'birth_date' in d
        assert d['birth_date'] == person.birth_date.isoformat()

    def test_datetime_serialization(self):
        """Tests that datetime objects in the database are correctly serialized
        in the :func:`flask.ext.restless.helpers.to_dict` function.

        """
        computer = self.Computer(buy_date=datetime.now())
        self.session.commit()
        d = to_dict(computer)
        assert 'buy_date' in d
        assert d['buy_date'] == computer.buy_date.isoformat()

    def test_uuid(self):
        """Tests for correct serialization of UUID objects."""
        exampleuuid = uuid.uuid1()
        vehicle = self.Vehicle(uuid=exampleuuid)
        self.session.commit()
        d = to_dict(vehicle)
        assert 'uuid' in d
        assert str(exampleuuid) == d['uuid']

    def test_to_dict(self):
        """Test for serializing attributes of an instance of the model by the
        :func:`flask.ext.restless.helpers.to_dict` function.

        """
        me = self.Person(name=u'Lincoln', age=24, birth_date=date(1986, 9, 15))
        self.session.commit()

        me_dict = to_dict(me)
        expectedfields = sorted(['birth_date', 'age', 'id', 'name',
                                 'other', 'is_minor'])
        assert sorted(me_dict) == expectedfields
        assert me_dict['name'] == u'Lincoln'
        assert me_dict['age'] == 24
        assert me_dict['birth_date'] == me.birth_date.isoformat()

    def test_primary_key_name(self):
        """Test for determining the primary attribute of a model or instance.

        """
        me = self.Person(name=u'Lincoln', age=24, birth_date=date(1986, 9, 15))
        assert 'id' == primary_key_name(me)
        assert 'id' == primary_key_name(self.Person)
        assert 'id' == primary_key_name(self.Star)

    def test_to_dict_dynamic_relation(self):
        """Tests that a dynamically queried relation is resolved when getting
        the dictionary representation of an instance of a model.

        """
        person = self.LazyPerson(name=u'Lincoln')
        self.session.add(person)
        computer = self.LazyComputer(name=u'lixeiro')
        self.session.add(computer)
        person.computers.append(computer)
        self.session.commit()
        person_dict = to_dict(person, deep={'computers': []})
        computer_dict = to_dict(computer, deep={'owner': None})
        assert sorted(person_dict), ['computers', 'id' == 'name']
        assert not isinstance(computer_dict['owner'], list)
        assert sorted(computer_dict) == ['id', 'name', 'owner', 'ownerid']
        expected_person = to_dict(person)
        expected_computer = to_dict(computer)
        assert person_dict['computers'] == [expected_computer]
        assert computer_dict['owner'] == expected_person

    def test_to_dict_deep(self):
        """Tests that fields corresponding to related model instances are
        correctly serialized by the :func:`flask.ext.restless.helpers.to_dict`
        function.

        """
        now = datetime.now()
        someone = self.Person(name=u'John', age=25)
        computer = self.Computer(name=u'lixeiro', vendor=u'Lemote',
                                 buy_date=now)
        someone.computers.append(computer)
        self.session.commit()

        deep = {'computers': []}
        computers = to_dict(someone, deep)['computers']
        assert len(computers) == 1
        assert computers[0]['name'] == u'lixeiro'
        assert computers[0]['vendor'] == u'Lemote'
        assert computers[0]['buy_date'] == now.isoformat()
        assert computers[0]['owner_id'] == someone.id

    def test_to_dict_hybrid_property(self):
        """Tests that hybrid properties are correctly serialized."""
        young = self.Person(name=u'John', age=15)
        old = self.Person(name=u'Sally', age=25)
        self.session.commit()

        assert to_dict(young)['is_minor']
        assert not to_dict(old)['is_minor']

    def test_to_dict_nested_object(self):
        """Tests that nested objects are correctly serialized."""
        person = self.Person(name=u'Test', age=10, other=20)
        computer = self.Computer(name=u'foo')
        person.computers.append(computer)

        data = to_dict(person, include_methods=['first_computer'])

        assert 'first_computer' in data
        assert 'foo' == data['first_computer']['name']

    def test_get_columns(self):
        """Test for getting the names of columns as strings."""
        columns = get_columns(self.Person)
        assert sorted(columns.keys()) == sorted(['age', 'birth_date',
                                                 'computers',
                                                 'id',
                                                 'is_minor',
                                                 'name',
                                                 'other'])

    def test_get_relations(self):
        """Tests getting the names of the relations of a model as strings."""
        relations = get_relations(self.Person)
        assert relations == ['computers']


class TestFunctionEvaluation(TestSupportPrefilled):
    """Unit tests for the :func:`flask.ext.restless.helpers.evaluate_functions`
    function.

    """

    def test_basic_evaluation(self):
        """Tests for basic function evaluation."""
        # test for no model
        result = evaluate_functions(self.session, None, [])
        assert result == {}

        # test for no functions
        result = evaluate_functions(self.session, self.Person, [])
        assert result == {}

        # test for summing ages
        functions = [{'name': 'sum', 'field': 'age'}]
        result = evaluate_functions(self.session, self.Person, functions)
        assert 'sum__age' in result
        assert result['sum__age'] == 102.0

        # test for multiple functions
        functions = [{'name': 'sum', 'field': 'age'},
                     {'name': 'avg', 'field': 'other'}]
        result = evaluate_functions(self.session, self.Person, functions)
        assert 'sum__age' in result
        assert result['sum__age'] == 102.0
        assert 'avg__other' in result
        assert result['avg__other'] == 16.2

    def test_count(self):
        """Tests for counting the number of rows in a query."""
        functions = [{'name': 'count', 'field': 'id'}]
        result = evaluate_functions(self.session, self.Person, functions)
        assert 'count__id' in result
        assert result['count__id'] == 5

    def test_poorly_defined_functions(self):
        """Tests that poorly defined functions raise errors."""
        # test for unknown field
        functions = [{'name': 'sum', 'field': 'bogus'}]
        assert_raises(AttributeError, evaluate_functions, self.session,
                      self.Person, functions)

        # test for unknown function
        functions = [{'name': 'bogus', 'field': 'age'}]
        assert_raises(OperationalError, evaluate_functions, self.session,
                      self.Person, functions)
