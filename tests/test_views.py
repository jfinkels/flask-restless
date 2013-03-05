"""
    tests.test_views
    ~~~~~~~~~~~~~~~~

    Provides unit tests for the :mod:`flask_restless.views` module.

    :copyright: 2011 by Lincoln de Sousa <lincoln@comum.org>
    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
from __future__ import with_statement

from datetime import date
from datetime import datetime
from unittest2 import TestSuite
from unittest2 import skipUnless

from flask import json
try:
    from flask.ext.sqlalchemy import SQLAlchemy
except:
    has_flask_sqlalchemy = False
else:
    has_flask_sqlalchemy = True
from sqlalchemy import Column
from sqlalchemy import Unicode
from sqlalchemy.exc import OperationalError

from flask.ext.restless.manager import APIManager
from flask.ext.restless.manager import IllegalArgumentError
from flask.ext.restless.views import _evaluate_functions as evaluate_functions
from flask.ext.restless.views import _get_columns
from flask.ext.restless.views import _get_or_create
from flask.ext.restless.views import _get_relations
from flask.ext.restless.views import _to_dict
from flask.ext.restless.views import AuthenticationException

from .helpers import FlaskTestBase
from .helpers import TestSupport
from .helpers import TestSupportPrefilled


__all__ = ['ModelTestCase', 'FunctionEvaluationTest', 'FunctionAPITestCase',
           'APITestCase', 'FSAModelTest']


dumps = json.dumps
loads = json.loads


class FSAModelTest(FlaskTestBase):
    """Tests for functions which operate on Flask-SQLAlchemy models."""

    def setUp(self):
        """Creates the Flask-SQLAlchemy database and models."""
        super(FSAModelTest, self).setUp()

        db = SQLAlchemy(self.flaskapp)

        class User(db.Model):
            id = db.Column(db.Integer, primary_key=True)

        class Pet(db.Model):
            id = db.Column(db.Integer, primary_key=True)
            ownerid = db.Column(db.Integer, db.ForeignKey(User.id))
            owner = db.relationship(User, backref=db.backref('pets'))

        class LazyUser(db.Model):
            id = db.Column(db.Integer, primary_key=True)

        class LazyPet(db.Model):
            id = db.Column(db.Integer, primary_key=True)
            ownerid = db.Column(db.Integer, db.ForeignKey(LazyUser.id))
            owner = db.relationship(LazyUser,
                                    backref=db.backref('pets', lazy='dynamic'))

        self.User = User
        self.Pet = Pet
        self.LazyUser = LazyUser
        self.LazyPet = LazyPet

        self.db = db
        self.db.create_all()

        self.manager = APIManager(self.flaskapp, flask_sqlalchemy_db=self.db)

    def tearDown(self):
        """Drops all tables."""
        self.db.drop_all()

    def test_get(self):
        """Test for the :meth:`views.API.get` method with models defined using
        Flask-SQLAlchemy with both dynamically loaded and static relationships.

        """
        # create the API endpoint
        self.manager.create_api(self.User)
        self.manager.create_api(self.LazyUser)
        self.manager.create_api(self.Pet)
        self.manager.create_api(self.LazyPet)

        response = self.app.get('/api/user')
        self.assertEqual(200, response.status_code)
        response = self.app.get('/api/lazy_user')
        self.assertEqual(200, response.status_code)
        response = self.app.get('/api/pet')
        self.assertEqual(200, response.status_code)
        response = self.app.get('/api/lazy_pet')
        self.assertEqual(200, response.status_code)

        # create a user with two pets
        owner = self.User()
        pet1 = self.Pet()
        pet2 = self.Pet()
        pet1.owner = owner
        pet2.owner = owner
        self.db.session.add_all([owner, pet1, pet2])
        self.db.session.commit()

        response = self.app.get('/api/user/%d' % owner.id)
        self.assertEqual(200, response.status_code)
        data = loads(response.data)
        self.assertEqual(2, len(data['pets']))
        for pet in data['pets']:
            self.assertEqual(owner.id, pet['ownerid'])

        response = self.app.get('/api/pet/1')
        self.assertEqual(200, response.status_code)
        data = loads(response.data)
        self.assertFalse(isinstance(data['owner'], list))
        self.assertEqual(owner.id, data['ownerid'])

        # create a lazy user with two lazy pets
        owner = self.LazyUser()
        pet1 = self.LazyPet()
        pet2 = self.LazyPet()
        pet1.owner = owner
        pet2.owner = owner
        self.db.session.add_all([owner, pet1, pet2])
        self.db.session.commit()

        response = self.app.get('/api/lazy_user/%d' % owner.id)
        self.assertEqual(200, response.status_code)
        data = loads(response.data)
        self.assertEqual(2, len(data['pets']))
        for pet in data['pets']:
            self.assertEqual(owner.id, pet['ownerid'])

        response = self.app.get('/api/lazy_pet/1')
        self.assertEqual(200, response.status_code)
        data = loads(response.data)
        self.assertFalse(isinstance(data['owner'], list))
        self.assertEqual(owner.id, data['ownerid'])


# skipUnless should be used as a decorator, but Python 2.5 doesn't have
# decorators.
FSATest = skipUnless(has_flask_sqlalchemy,
                     'Flask-SQLAlchemy not found.')(FSAModelTest)


class ModelTestCase(TestSupport):
    """Provides tests for helper functions which operate on pure SQLAlchemy
    models.

    """

    def test_get_columns(self):
        """Test for getting the names of columns as strings."""
        columns = _get_columns(self.Person)
        self.assertEqual(sorted(columns.keys()), sorted(['age', 'birth_date',
                                                         'computers', 'id',
                                                         'name', 'other']))

    def test_get_relations(self):
        """Tests getting the names of the relations of a model as strings."""
        relations = _get_relations(self.Person)
        self.assertEqual(relations, ['computers'])

    def test_date_serialization(self):
        """Tests that date objects in the database are correctly serialized in
        the :meth:`flask_restless.model.Entity.to_dict` method.

        """
        person = self.Person(birth_date=date(1986, 9, 15))
        self.session.commit()
        d = _to_dict(person)
        self.assertIn('birth_date', d)
        self.assertEqual(d['birth_date'], person.birth_date.isoformat())

    def test_datetime_serialization(self):
        """Tests that datetime objects in the database are correctly serialized
        in the :meth:`flask_restless.model.Entity.to_dict` method.

        """
        computer = self.Computer(buy_date=datetime.now())
        self.session.commit()
        d = _to_dict(computer)
        self.assertIn('buy_date', d)
        self.assertEqual(d['buy_date'], computer.buy_date.isoformat())

    def test_to_dict(self):
        """Test for serializing attributes of an instance of the model by the
        :meth:`flask_restless.model.Entity.to_dict` method.

        """
        me = self.Person(name=u'Lincoln', age=24, birth_date=date(1986, 9, 15))
        self.session.commit()

        me_dict = _to_dict(me)
        expectedfields = sorted(['birth_date', 'age', 'id', 'name',
            'other', 'is_minor'])
        self.assertEqual(sorted(me_dict), expectedfields)
        self.assertEqual(me_dict['name'], u'Lincoln')
        self.assertEqual(me_dict['age'], 24)
        self.assertEqual(me_dict['birth_date'], me.birth_date.isoformat())

    def test_to_dict_dynamic_relation(self):
        """Tests that a dynamically queried relation is resolved when getting
        the dictionary representation of an instance of a model.

        """
        person = self.LazyPerson(name='Lincoln')
        self.session.add(person)
        computer = self.LazyComputer(name='lixeiro')
        self.session.add(computer)
        person.computers.append(computer)
        self.session.commit()
        person_dict = _to_dict(person, deep={'computers': []})
        computer_dict = _to_dict(computer, deep={'owner': None})
        self.assertEqual(sorted(person_dict), ['computers', 'id', 'name'])
        self.assertFalse(isinstance(computer_dict['owner'], list))
        self.assertEqual(sorted(computer_dict), ['id', 'name', 'owner',
                                                 'ownerid'])
        expected_person = _to_dict(person)
        expected_computer = _to_dict(computer)
        self.assertEqual(person_dict['computers'], [expected_computer])
        self.assertEqual(computer_dict['owner'], expected_person)

    def test_to_dict_deep(self):
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
        computers = _to_dict(someone, deep)['computers']
        self.assertEqual(len(computers), 1)
        self.assertEqual(computers[0]['name'], u'lixeiro')
        self.assertEqual(computers[0]['vendor'], u'Lemote')
        self.assertEqual(computers[0]['buy_date'], now.isoformat())
        self.assertEqual(computers[0]['owner_id'], someone.id)

    def test_to_dict_hybrid_property(self):
        """Tests that hybrid properties are correctly serialized."""
        young = self.Person(name=u'John', age=15)
        old = self.Person(name=u'Sally', age=25)
        self.session.commit()

        self.assertTrue(_to_dict(young)['is_minor'])
        self.assertFalse(_to_dict(old)['is_minor'])

    def test_get_or_create(self):
        """Test for :meth:`flask_restless.model.Entity.get_or_create()`."""
        # Here we're sure that we have a fresh table with no rows, so
        # let's create the first one:
        instance, created = _get_or_create(self.session, self.Person,
                                           name=u'Lincoln', age=24)
        self.assertTrue(created)
        self.assertEqual(instance.name, u'Lincoln')
        self.assertEqual(instance.age, 24)

        # Now that we have a row, let's try to get it again
        second_instance, created = _get_or_create(self.session, self.Person,
                                                  name=u'Lincoln')
        self.assertFalse(created)
        self.assertEqual(second_instance.name, u'Lincoln')
        self.assertEqual(second_instance.age, 24)


class FunctionEvaluationTest(TestSupportPrefilled):
    """Unit tests for the :func:`flask_restless.view._evaluate_functions`
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


class FunctionAPITestCase(TestSupportPrefilled):
    """Unit tests for the :class:`flask_restless.views.FunctionAPI` class."""

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`testapp.Person` and
        :class:`testapp.Computer` models.

        """
        super(FunctionAPITestCase, self).setUp()
        self.manager.create_api(self.Person, allow_functions=True)

    def test_function_evaluation(self):
        """Test that the :http:get:`/api/eval/person` endpoint returns the
        result of evaluating functions.

        """
        functions = [{'name': 'sum', 'field': 'age'},
                     {'name': 'avg', 'field': 'other'},
                     {'name': 'count', 'field': 'id'}]
        query = dumps(dict(functions=functions))
        response = self.app.get('/api/eval/person?q=%s' % query)
        self.assertEqual(response.status_code, 200)
        data = loads(response.data)
        self.assertIn('sum__age', data)
        self.assertEqual(data['sum__age'], 102.0)
        self.assertIn('avg__other', data)
        self.assertEqual(data['avg__other'], 16.2)
        self.assertIn('count__id', data)
        self.assertEqual(data['count__id'], 5)

    def test_no_functions(self):
        """Tests that if no functions are defined, an empty response is
        returned.

        """
        # no data is invalid JSON
        response = self.app.get('/api/eval/person')
        self.assertEqual(response.status_code, 400)
        # so is the empty string
        response = self.app.get('/api/eval/person?q=')
        self.assertEqual(response.status_code, 400)

        # if we provide no functions, then we expect an empty response
        response = self.app.get('/api/eval/person?q=%s' % dumps(dict()))
        self.assertEqual(response.status_code, 204)

    def test_poorly_defined_functions(self):
        """Tests that poorly defined requests for function evaluations cause an
        error message to be returned.

        """
        # test for bad field name
        search = {'functions': [{'name': 'sum', 'field': 'bogusfieldname'}]}
        resp = self.app.get('/api/eval/person?q=%s' % dumps(search))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('message', loads(resp.data))
        self.assertIn('bogusfieldname', loads(resp.data)['message'])

        # test for bad function name
        search = {'functions': [{'name': 'bogusfuncname', 'field': 'age'}]}
        resp = self.app.get('/api/eval/person?q=%s' % dumps(search))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('message', loads(resp.data))
        self.assertIn('bogusfuncname', loads(resp.data)['message'])

    def test_jsonp(self):
        """Test for JSON-P callbacks."""
        person1 = self.Person(age=10)
        person2 = self.Person(age=20)
        person3 = self.Person(age=35)
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        functions = [{'name': 'sum', 'field': 'age'}]
        query = dumps(dict(functions=functions))
        response = self.app.get('/api/eval/person?q=%s&callback=baz' % query)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith('baz('))
        self.assertTrue(response.data.endswith(')'))


class APITestCase(TestSupport):
    """Unit tests for the :class:`flask_restless.views.API` class."""

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`testapp.Person` and
        :class:`testapp.Computer` models.

        """
        # create the database
        super(APITestCase, self).setUp()

        # setup the URLs for the Person and Computer API
        self.manager.create_api(self.Person,
                                methods=['GET', 'PATCH', 'POST', 'DELETE'])
        self.manager.create_api(self.Computer, methods=['GET', 'POST'])

        # to facilitate searching
        self.app.search = lambda url, q: self.app.get(url + '?q=%s' % q)

    def test_post(self):
        """Test for creating a new instance of the database model using the
        :http:method:`post` method.

        """
        # Invalid JSON in request data should respond with error.
        response = self.app.post('/api/person', data='Invalid JSON string')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(loads(response.data)['message'],
                         'Unable to decode data')

        # Now, let's test the validation stuff
        # response = self.app.post('/api/person', data=dumps({'name': u'Test',
        #                                                      'age': 'oi'}))
        # assert loads(response.data)['message'] == 'Validation error'
        # assert loads(response.data)['error_list'].keys() == ['age']

        response = self.app.post('/api/person',
                                 data=dumps({'name': u'Lincoln', 'age': 23}))
        self.assertEqual(response.status_code, 201)
        self.assertIn('id', loads(response.data))

        response = self.app.get('/api/person/1')
        self.assertEqual(response.status_code, 200)

        deep = {'computers': []}
        person = self.session.query(self.Person).filter_by(id=1).first()
        inst = _to_dict(person, deep)
        self.assertEqual(loads(response.data), inst)

    def test_post_bad_parameter(self):
        """Tests that attempting to make a :http:method:`post` request with a
        form parameter which does not exist on the specified model responds
        with an error message.

        """
        response = self.app.post('/api/person', data=dumps(dict(bogus=0)))
        self.assertEqual(400, response.status_code)

    def test_post_nullable_date(self):
        """Tests the creation of a model with a nullable date field."""
        self.manager.create_api(self.Star, methods=['GET', 'POST'])
        data = dict(inception_time=None)
        response = self.app.post('/api/star', data=dumps(data))
        self.assertEqual(response.status_code, 201)
        response = self.app.get('/api/star/1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['inception_time'], None)

    def test_post_empty_date(self):
        """Tests that attempting to assign an empty date string to a date field
        actually assigns a value of ``None``.

        """
        self.manager.create_api(self.Star, methods=['GET', 'POST'])
        data = dict(inception_time='')
        response = self.app.post('/api/star', data=dumps(data))
        self.assertEqual(response.status_code, 201)
        response = self.app.get('/api/star/1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['inception_time'], None)

    def test_post_with_submodels(self):
        """Tests the creation of a model with a related field."""
        data = {'name': u'John', 'age': 2041,
                'computers': [{'name': u'lixeiro', 'vendor': u'Lemote'}]}
        response = self.app.post('/api/person', data=dumps(data))
        self.assertEqual(response.status_code, 201)
        self.assertIn('id', loads(response.data))

        response = self.app.get('/api/person')
        self.assertEqual(len(loads(response.data)['objects']), 1)

    def test_post_with_single_submodel(self):
        data = {'vendor': u'Apple',  'name': u'iMac',
                'owner': {'name': u'John', 'age': 2041}}
        response = self.app.post('/api/computer', data=dumps(data))
        self.assertEqual(response.status_code, 201)
        self.assertIn('id', loads(response.data))
        # Test if owner was successfully created
        response = self.app.get('/api/person')
        self.assertEqual(len(loads(response.data)['objects']), 1)

    def test_delete(self):
        """Test for deleting an instance of the database using the
        :http:method:`delete` method.

        """
        # Creating the person who's gonna be deleted
        response = self.app.post('/api/person',
                                 data=dumps({'name': u'Lincoln', 'age': 23}))
        self.assertEqual(response.status_code, 201)
        self.assertIn('id', loads(response.data))

        # Making sure it has been created
        deep = {'computers': []}
        person = self.session.query(self.Person).filter_by(id=1).first()
        inst = _to_dict(person, deep)
        response = self.app.get('/api/person/1')
        self.assertEqual(loads(response.data), inst)

        # Deleting it
        response = self.app.delete('/api/person/1')
        self.assertEqual(response.status_code, 204)

        # Making sure it has been deleted
        people = self.session.query(self.Person).filter_by(id=1)
        self.assertEquals(people.count(), 0)

    def test_delete_absent_instance(self):
        """Test that deleting an instance of the model which does not exist
        fails.

        This should give us the same response as when there is an object there,
        since the :http:method:`delete` method is an idempotent method.

        """
        response = self.app.delete('/api/person/1')
        self.assertEqual(response.status_code, 204)

    def test_disallow_patch_many(self):
        """Tests that disallowing "patch many" requests responds with a
        :http:statuscode:`405`.

        """
        response = self.app.patch('/api/person', data=dumps(dict(name='foo')))
        self.assertEqual(response.status_code, 405)

    def test_put_same_as_patch(self):
        """Tests that :http:method:`put` requests are the same as
        :http:method:`patch` requests.

        """
        # recreate the api to allow patch many at /api/v2/person
        self.manager.create_api(self.Person, methods=['GET', 'POST', 'PUT'],
                                allow_patch_many=True, url_prefix='/api/v2')

        # Creating some people
        self.app.post('/api/v2/person',
                      data=dumps({'name': u'Lincoln', 'age': 23}))
        self.app.post('/api/v2/person',
                      data=dumps({'name': u'Lucy', 'age': 23}))
        self.app.post('/api/v2/person',
                      data=dumps({'name': u'Mary', 'age': 25}))

        # change a single entry
        resp = self.app.put('/api/v2/person/1', data=dumps({'age': 24}))
        self.assertEqual(resp.status_code, 200)

        resp = self.app.get('/api/v2/person/1')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['age'], 24)

        # Changing the birth date field of the entire collection
        day, month, year = 15, 9, 1986
        birth_date = date(year, month, day).strftime('%d/%m/%Y')  # iso8601
        form = {'birth_date': birth_date}
        self.app.put('/api/v2/person', data=dumps(form))

        # Finally, testing if the change was made
        response = self.app.get('/api/v2/person')
        loaded = loads(response.data)['objects']
        for i in loaded:
            self.assertEqual(i['birth_date'], ('%s-%s-%s' % (
                    year, str(month).zfill(2), str(day).zfill(2))))

    def test_patch_empty(self):
        """Test for making a :http:method:`patch` request with no data."""
        response = self.app.post('/api/person', data=dumps(dict(name='foo')))
        self.assertEqual(response.status_code, 201)
        personid = loads(response.data)['id']
        # here we really send no data
        response = self.app.patch('/api/person/' + str(personid))
        self.assertEqual(response.status_code, 400)
        # here we send the empty string (which is not valid JSON)
        response = self.app.patch('/api/person/' + str(personid), data='')
        self.assertEqual(response.status_code, 400)

    def test_patch_bad_parameter(self):
        """Tests that attempting to make a :http:method:`patch` request with a
        form parameter which does not exist on the specified model responds
        with an error message.

        """
        response = self.app.post('/api/person', data=dumps({}))
        self.assertEqual(201, response.status_code)
        response = self.app.patch('/api/person/1', data=dumps(dict(bogus=0)))
        self.assertEqual(400, response.status_code)

    def test_patch_many(self):
        """Test for updating a collection of instances of the model using the
        :http:method:`patch` method.

        """
        # recreate the api to allow patch many at /api/v2/person
        self.manager.create_api(self.Person, methods=['GET', 'POST', 'PATCH'],
                                allow_patch_many=True, url_prefix='/api/v2')

        # Creating some people
        self.app.post('/api/v2/person',
                      data=dumps({'name': u'Lincoln', 'age': 23}))
        self.app.post('/api/v2/person',
                      data=dumps({'name': u'Lucy', 'age': 23}))
        self.app.post('/api/v2/person',
                      data=dumps({'name': u'Mary', 'age': 25}))

        # Trying to pass invalid data to the update method
        resp = self.app.patch('/api/v2/person', data='Hello there')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(loads(resp.data)['message'], 'Unable to decode data')

        # Changing the birth date field of the entire collection
        day, month, year = 15, 9, 1986
        birth_date = date(year, month, day).strftime('%d/%m/%Y')  # iso8601
        form = {'birth_date': birth_date}
        self.app.patch('/api/v2/person', data=dumps(form))

        # Finally, testing if the change was made
        response = self.app.get('/api/v2/person')
        loaded = loads(response.data)['objects']
        for i in loaded:
            self.assertEqual(i['birth_date'], ('%s-%s-%s' % (
                    year, str(month).zfill(2), str(day).zfill(2))))

    def test_patch_many_with_filter(self):
        """Test for updating a collection of instances of the model using a
        :http:method:patch request with filters.

        """
        # recreate the api to allow patch many at /api/v2/person
        self.manager.create_api(self.Person, methods=['GET', 'POST', 'PATCH'],
                                allow_patch_many=True, url_prefix='/api/v2')
        # Creating some people
        self.app.post('/api/v2/person',
                      data=dumps({'name': u'Lincoln', 'age': 23}))
        self.app.post('/api/v2/person',
                      data=dumps({'name': u'Lucy', 'age': 23}))
        self.app.post('/api/v2/person',
                      data=dumps({'name': u'Mary', 'age': 25}))
        search = {
                     'filters': [
                         {'name': 'name', 'val': u'Lincoln', 'op': 'equals'}
                     ],
                 }
        # Changing the birth date field for objects where name field equals Lincoln
        day, month, year = 15, 9, 1986
        birth_date = date(year, month, day).strftime('%d/%m/%Y') # iso8601
        form = {'birth_date': birth_date, 'q': search}
        response = self.app.patch('/api/v2/person', data=dumps(form))
        num_modified = loads(response.data)['num_modified']
        self.assertEqual(num_modified, 1)

    def test_single_update(self):
        """Test for updating a single instance of the model using the
        :http:method:`patch` method.

        """
        resp = self.app.post('/api/person', data=dumps({'name': u'Lincoln',
                                                         'age': 10}))
        self.assertEqual(resp.status_code, 201)
        self.assertIn('id', loads(resp.data))

        # Trying to pass invalid data to the update method
        resp = self.app.patch('/api/person/1', data='Invalid JSON string')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(loads(resp.data)['message'], 'Unable to decode data')

        resp = self.app.patch('/api/person/1', data=dumps({'age': 24}))
        self.assertEqual(resp.status_code, 200)

        resp = self.app.get('/api/person/1')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['age'], 24)

    def test_patch_404(self):
        """Tests that making a :http:method:`patch` request to an instance
        which does not exist results in a :http:statuscode:`404`.

        """
        resp = self.app.patch('/api/person/1', data=dumps(dict(name='foo')))
        self.assertEqual(resp.status_code, 404)

    def test_patch_set_submodel(self):
        """Test for assigning a list to a relation of a model using
        :http:method:`patch`.

        """
        response = self.app.post('/api/person', data=dumps({}))
        self.assertEqual(response.status_code, 201)
        data = {'computers': [{'name': u'lixeiro', 'vendor': u'Lemote'},
                              {'name': u'foo', 'vendor': u'bar'}]}
        response = self.app.patch('/api/person/1', data=dumps(data))
        self.assertEqual(200, response.status_code)
        data = json.loads(response.data)
        self.assertEqual(2, len(data['computers']))
        self.assertEqual(u'lixeiro', data['computers'][0]['name'])
        self.assertEqual(u'foo', data['computers'][1]['name'])
        data = {'computers': [{'name': u'hey', 'vendor': u'you'},
                              {'name': u'big', 'vendor': u'money'},
                              {'name': u'milk', 'vendor': u'chocolate'}]}
        response = self.app.patch('/api/person/1', data=dumps(data))
        self.assertEqual(200, response.status_code)
        data = json.loads(response.data)
        self.assertEqual(3, len(data['computers']))
        self.assertEqual(u'hey', data['computers'][0]['name'])
        self.assertEqual(u'big', data['computers'][1]['name'])
        self.assertEqual(u'milk', data['computers'][2]['name'])

    def test_patch_new_single(self):
        """Test for adding a single new object to a one-to-one relationship
        using :http:method:`patch`.

        """
        # create the person
        data = {'name': u'Lincoln', 'age': 23}
        response = self.app.post('/api/person', data=dumps(data))
        self.assertEqual(response.status_code, 201)

        # patch the person with a new computer
        data = {'computers': {'add': {'name': u'lixeiro',
            'vendor': u'Lemote'}}}

        response = self.app.patch('/api/person/1', data=dumps(data))
        self.assertEqual(response.status_code, 200)

        # Let's check it out
        response = self.app.get('/api/person/1')
        loaded = loads(response.data)

        self.assertEqual(len(loaded['computers']), 1)
        self.assertEqual(loaded['computers'][0]['name'],
                         data['computers']['add']['name'])
        self.assertEqual(loaded['computers'][0]['vendor'],
                         data['computers']['add']['vendor'])

        # test that this new computer was added to the database as well
        computer = self.session.query(self.Computer).filter_by(id=1).first()
        self.assertIsNotNone(computer)
        self.assertEqual(data['computers']['add']['name'], computer.name)
        self.assertEqual(data['computers']['add']['vendor'],
                         computer.vendor)

    def test_patch_existing_single(self):
        """Test for adding a single existing object to a one-to-one
        relationship using :http:method:`patch`.

        """
        # create the person
        data = {'name': u'Lincoln', 'age': 23}
        response = self.app.post('/api/person', data=dumps(data))
        self.assertEqual(response.status_code, 201)

        # create the computer
        data = {'name': u'lixeiro', 'vendor': u'Lemote'}
        response = self.app.post('/api/computer', data=dumps(data))
        self.assertEqual(response.status_code, 201)

        # patch the person with the created computer
        data = {'computers': {'add': {'id': 1}}}
        response = self.app.patch('/api/person/1', data=dumps(data))
        self.assertEqual(response.status_code, 200)

        # Let's check it out
        response = self.app.get('/api/person/1')
        loaded = loads(response.data)

        self.assertEqual(len(loaded['computers']), 1)
        self.assertEqual(loaded['computers'][0]['id'],
                         data['computers']['add']['id'])

    def test_patch_add_submodels(self):
        """Test for updating a single instance of the model by adding a list of
        related models using the :http:method:`patch` method.

        """
        data = dict(name=u'Lincoln', age=23)
        response = self.app.post('/api/person', data=dumps(data))
        self.assertEqual(response.status_code, 201)

        data = {'computers':
                    {'add': [{'name': u'lixeiro', 'vendor': u'Lemote'},
                             {'name': u'foo', 'vendor': u'bar'}]}
                }
        response = self.app.patch('/api/person/1', data=dumps(data))
        self.assertEqual(response.status_code, 200)
        response = self.app.get('/api/person/1')
        loaded = loads(response.data)

        self.assertEqual(len(loaded['computers']), 2)
        self.assertEqual(loaded['computers'][0]['name'], u'lixeiro')
        self.assertEqual(loaded['computers'][0]['vendor'], u'Lemote')
        self.assertEqual(loaded['computers'][1]['name'], u'foo')
        self.assertEqual(loaded['computers'][1]['vendor'], u'bar')

        # test that these new computers were added to the database as well
        computer = self.session.query(self.Computer).filter_by(id=1).first()
        self.assertIsNotNone(computer)
        self.assertEqual(u'lixeiro', computer.name)
        self.assertEqual(u'Lemote', computer.vendor)
        computer = self.session.query(self.Computer).filter_by(id=2).first()
        self.assertIsNotNone(computer)
        self.assertEqual(u'foo', computer.name)
        self.assertEqual(u'bar', computer.vendor)

    def test_patch_remove_submodel(self):
        """Test for updating a single instance of the model by removing a
        related model using the :http:method:`patch` method.

        """
        # Creating the row that will be updated
        data = {
            'name': u'Lincoln', 'age': 23,
            'computers': [
                {'name': u'lixeiro', 'vendor': u'Lemote'},
                {'name': u'pidinti', 'vendor': u'HP'},
            ],
        }
        self.app.post('/api/person', data=dumps(data))

        # Data for the update
        update_data = {
            'computers': {
                'remove': [{'name': u'pidinti'}],
            }
        }
        resp = self.app.patch('/api/person/1', data=dumps(update_data))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['id'], 1)

        # Let's check it out
        response = self.app.get('/api/person/1')
        loaded = loads(response.data)
        self.assertEqual(len(loaded['computers']), 1)

    def test_patch_autodelete_submodel(self):
        """Tests the automatic deletion of entries marked with the
        ``__delete__`` flag on an update operation.

        It also tests adding an already created instance as a related item.

        """
        # Creating all rows needed in our test
        person_data = {'name': u'Lincoln', 'age': 23}
        resp = self.app.post('/api/person', data=dumps(person_data))
        self.assertEqual(resp.status_code, 201)
        comp_data = {'name': u'lixeiro', 'vendor': u'Lemote'}
        resp = self.app.post('/api/computer', data=dumps(comp_data))
        self.assertEqual(resp.status_code, 201)

        # updating person to add the computer
        update_data = {'computers': {'add': [{'id': 1}]}}
        self.app.patch('/api/person/1', data=dumps(update_data))

        # Making sure that everything worked properly
        resp = self.app.get('/api/person/1')
        self.assertEqual(resp.status_code, 200)
        loaded = loads(resp.data)
        self.assertEqual(len(loaded['computers']), 1)
        self.assertEqual(loaded['computers'][0]['name'], u'lixeiro')

        # Now, let's remove it and delete it
        update2_data = {
            'computers': {
                'remove': [
                    {'id': 1, '__delete__': True},
                ],
            },
        }
        resp = self.app.patch('/api/person/1', data=dumps(update2_data))
        self.assertEqual(resp.status_code, 200)

        # Testing to make sure it was removed from the related field
        resp = self.app.get('/api/person/1')
        self.assertEqual(resp.status_code, 200)
        loaded = loads(resp.data)
        self.assertEqual(len(loaded['computers']), 0)

        # Making sure it was removed from the database
        resp = self.app.get('/api/computer/1')
        self.assertEqual(resp.status_code, 404)

    def test_search(self):
        """Tests basic search using the :http:method:`get` method."""
        # Trying to pass invalid params to the search method
        resp = self.app.get('/api/person?q=Test')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(loads(resp.data)['message'], 'Unable to decode data')

        create = lambda x: self.app.post('/api/person', data=dumps(x))
        create({'name': u'Lincoln', 'age': 23, 'other': 22})
        create({'name': u'Mary', 'age': 19, 'other': 19})
        create({'name': u'Lucy', 'age': 25, 'other': 20})
        create({'name': u'Katy', 'age': 7, 'other': 10})
        create({'name': u'John', 'age': 28, 'other': 10})

        search = {
            'filters': [
                {'name': 'name', 'val': '%y%', 'op': 'like'}
             ]
        }

        # Let's search for users with that above filter
        resp = self.app.search('/api/person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        loaded = loads(resp.data)
        self.assertEqual(len(loaded['objects']), 3)  # Mary, Lucy and Katy

        # Tests searching for a single row
        search = {
            'single': True,      # I'm sure we have only one row here
            'filters': [
                {'name': 'name', 'val': u'Lincoln', 'op': 'equals'}
            ],
        }
        resp = self.app.search('/api/person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['name'], u'Lincoln')

        # Looking for something that does not exist on the database
        search['filters'][0]['val'] = 'Sammy'
        resp = self.app.search('/api/person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['message'], 'No result found')

        # We have to receive an error if the user provides an invalid
        # data to the search, like this:
        search = {
            'filters': [
                {'name': 'age', 'val': 'It should not be a string', 'op': 'gt'}
            ]
        }
        resp = self.app.search('/api/person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        #assert loads(resp.data)['error_list'][0] == \
        #    {'age': 'Please enter a number'}
        self.assertEqual(len(loads(resp.data)['objects']), 0)

        # Testing the order_by stuff
        search = {'order_by': [{'field': 'age', 'direction': 'asc'}]}
        resp = self.app.search('/api/person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        loaded = loads(resp.data)['objects']
        self.assertEqual(loaded[0][u'age'], 7)
        self.assertEqual(loaded[1][u'age'], 19)
        self.assertEqual(loaded[2][u'age'], 23)
        self.assertEqual(loaded[3][u'age'], 25)
        self.assertEqual(loaded[4][u'age'], 28)

        # Test the IN operation
        search = {
            'filters': [
                {'name': 'age', 'val': [7, 28], 'op': 'in'}
            ]
        }
        resp = self.app.search('/api/person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        loaded = loads(resp.data)['objects']
        self.assertEqual(loaded[0][u'age'], 7)
        self.assertEqual(loaded[1][u'age'], 28)

        # Testing related search
        update = {
            'computers': {
                'add': [{'name': u'lixeiro', 'vendor': u'Lenovo'}]
            }
        }
        resp = self.app.patch('/api/person/1', data=dumps(update))
        self.assertEqual(resp.status_code, 200)

        # TODO document this
        search = {
            'single': True,
            'filters': [
                {'name': 'computers__name',
                 'val': u'lixeiro',
                 'op': 'any'}
            ]
        }
        resp = self.app.search('/api/person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['computers'][0]['name'], 'lixeiro')

        # Testing the comparation for two fields. We want to compare
        # `age' and `other' fields. If the first one is lower than or
        # equals to the second one, we want the object
        search = {
            'filters': [
                {'name': 'age', 'op': 'lte', 'field': 'other'}
            ],
            'order_by': [
                {'field': 'other'}
            ]
        }
        resp = self.app.search('/api/person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        loaded = loads(resp.data)['objects']
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]['other'], 10)
        self.assertEqual(loaded[1]['other'], 19)

    def test_search2(self):
        """Testing more search functionality."""
        create = lambda x: self.app.post('/api/person', data=dumps(x))
        create({'name': u'Fuxu', 'age': 32})
        create({'name': u'Everton', 'age': 33})
        create({'name': u'Lincoln', 'age': 24})

        # Let's test the search using an id
        search = {
            'single': True,
            'filters': [{'name': 'id', 'op': 'equal_to', 'val': 1}]
        }
        resp = self.app.search('/api/person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['name'], u'Fuxu')

        # Testing limit and offset
        search = {'limit': 1, 'offset': 1}
        resp = self.app.search('/api/person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(1, len(loads(resp.data)['objects']))
        self.assertEqual(loads(resp.data)['objects'][0]['name'], u'Everton')

        # Testing multiple results when calling .one()
        resp = self.app.search('/api/person', dumps({'single': True}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['message'], 'Multiple results found')

    def test_search_bad_arguments(self):
        """Tests that search requests with bad parameters respond with an error
        message.

        """
        # missing argument
        d = dict(filters=[dict(name='name', op='==')])
        resp = self.app.search('/api/person', dumps(d))
        self.assertEqual(resp.status_code, 400)

        # missing operator
        d = dict(filters=[dict(name='name', val='Test')])
        resp = self.app.search('/api/person', dumps(d))
        self.assertEqual(resp.status_code, 400)

        # missing fieldname
        d = dict(filters=[dict(op='==', val='Test')])
        resp = self.app.search('/api/person', dumps(d))
        self.assertEqual(resp.status_code, 400)

    def test_authentication(self):
        """Tests basic authentication using custom authentication functions."""
        # must provide authentication function if authentication is required
        # for some HTTP methods
        with self.assertRaises(IllegalArgumentError):
            self.manager.create_api(self.Person, methods=['GET', 'POST'],
                                    authentication_required_for=['POST'])
        # function always raise AuthenticationException
        def check_permission():
            raise AuthenticationException(status_code=401,
                                          message='Permission denied')

        # test for authentication always failing
        self.manager.create_api(self.Person, methods=['GET', 'POST'],
                                url_prefix='/api/v2',
                                authentication_required_for=['POST'],
                                authentication_function=check_permission)

        # a slightly more complicated function; all odd calls are authenticated
        class everyother(object):
            """Stores the number of times this object has been called."""

            def __init__(self):
                """Initialize the number of calls to 0."""
                self.count = 0

            def __call__(self):
                """Increment the call count and return its parity."""
                self.count += 1
                if not self.count % 2:
                    raise AuthenticationException(status_code=401,
                                                  message='Permission denied')

        self.manager.create_api(self.Person, methods=['GET'],
                                url_prefix='/api/v3',
                                authentication_required_for=['GET'],
                                authentication_function=everyother())

        # requests which expect authentication always fails
        for i in range(3):
            response = self.app.get('/api/v2/person')
            self.assertEqual(response.status_code, 200)
            response = self.app.post('/api/v2/person')
            self.assertEqual(response.status_code, 401)

        # requests which fail on every odd request
        for i in range(3):
            response = self.app.get('/api/v3/person')
            self.assertEqual(response.status_code, 200)
            response = self.app.get('/api/v3/person')
            self.assertEqual(response.status_code, 401)

    def test_pagination(self):
        """Tests for pagination of long result sets."""
        self.manager.create_api(self.Person, url_prefix='/api/v2',
                                results_per_page=5)
        self.manager.create_api(self.Person, url_prefix='/api/v3',
                                results_per_page=0)
        for i in range(25):
            d = dict(name=unicode('person%s' % i))
            response = self.app.post('/api/person', data=dumps(d))
            self.assertEqual(response.status_code, 201)

        response = self.app.get('/api/person')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['page'], 1)
        self.assertEqual(len(loads(response.data)['objects']), 10)
        self.assertEqual(loads(response.data)['total_pages'], 3)

        response = self.app.get('/api/person?page=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['page'], 1)
        self.assertEqual(len(loads(response.data)['objects']), 10)
        self.assertEqual(loads(response.data)['total_pages'], 3)

        response = self.app.get('/api/person?page=2')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['page'], 2)
        self.assertEqual(len(loads(response.data)['objects']), 10)
        self.assertEqual(loads(response.data)['total_pages'], 3)

        response = self.app.get('/api/person?page=3')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['page'], 3)
        self.assertEqual(len(loads(response.data)['objects']), 5)
        self.assertEqual(loads(response.data)['total_pages'], 3)

        response = self.app.get('/api/v2/person?page=3')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['page'], 3)
        self.assertEqual(len(loads(response.data)['objects']), 5)
        self.assertEqual(loads(response.data)['total_pages'], 5)

        response = self.app.get('/api/v3/person')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['page'], 1)
        self.assertEqual(len(loads(response.data)['objects']), 25)
        self.assertEqual(loads(response.data)['total_pages'], 1)

        response = self.app.get('/api/v3/person?page=2')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['page'], 1)
        self.assertEqual(len(loads(response.data)['objects']), 25)
        self.assertEqual(loads(response.data)['total_pages'], 1)

    def test_num_results(self):
        """Tests that a request for (a subset of) all instances of a model
        includes the total number of results as part of the JSON response.

        """
        self.manager.create_api(self.Person)
        for i in range(25):
            d = dict(name=unicode('person%s' % i))
            response = self.app.post('/api/person', data=dumps(d))
            self.assertEqual(response.status_code, 201)
        response = self.app.get('/api/person')
        self.assertEqual(response.status_code, 200)
        data = loads(response.data)
        self.assertIn('num_results', data)
        self.assertEqual(data['num_results'], 25)

    def test_alternate_primary_key(self):
        """Tests that models with primary keys which are not ``id`` columns are
        accessible via their primary keys.

        """
        self.manager.create_api(self.Planet, methods=['GET', 'POST'])
        response = self.app.post('/api/planet', data=dumps(dict(name='Earth')))
        self.assertEqual(response.status_code, 201)
        response = self.app.get('/api/planet/1')
        self.assertEqual(response.status_code, 404)
        response = self.app.get('/api/planet')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(loads(response.data)['objects']), 1)
        response = self.app.get('/api/planet/Earth')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data), dict(name='Earth'))

    def test_post_form_preprocessor(self):
        """Tests POST method decoration using a custom function."""
        def decorator_function(params):
            if params:
                # just add a new attribute
                params['other'] = 7
            return params

        # test for function that decorates parameters with 'other' attribute
        self.manager.create_api(self.Person, methods=['POST'],
                                url_prefix='/api/v2',
                                post_form_preprocessor=decorator_function)

        response = self.app.post('/api/v2/person',
                                 data=dumps({'name': u'Lincoln', 'age': 23}))
        self.assertEqual(response.status_code, 201)

        personid = loads(response.data)['id']
        person = self.session.query(self.Person).filter_by(id=personid).first()
        self.assertEquals(person.other, 7)

    def test_results_per_page(self):
        """Tests that the client can correctly specify the number of results
        appearing per page, in addition to specifying which page of results to
        return.

        """
        self.manager.create_api(self.Person, methods=['POST', 'GET'])
        for n in range(150):
            response = self.app.post('/api/person', data=dumps({}))
            self.assertEqual(201, response.status_code)
        response = self.app.get('/api/person?results_per_page=20')
        self.assertEqual(200, response.status_code)
        data = loads(response.data)
        self.assertEqual(20, len(data['objects']))
        # Fall back to default number of results per page on bad requests.
        response = self.app.get('/api/person?results_per_page=-1')
        self.assertEqual(200, response.status_code)
        data = loads(response.data)
        self.assertEqual(10, len(data['objects']))
        # Only return max number of results per page.
        response = self.app.get('/api/person?results_per_page=120')
        self.assertEqual(200, response.status_code)
        data = loads(response.data)
        self.assertEqual(100, len(data['objects']))

    def test_get_string_pk(self):
        """Tests for getting a row which has a string primary key, including
        the possibility of a string representation of a number.

        """
        # create a model and an instance of the model
        class StringID(self.Base):
            __tablename__ = 'stringid'
            name = Column(Unicode, primary_key=True)
        self.Base.metadata.create_all()
        self.manager.create_api(StringID)

        foo = StringID(name='1')
        self.session.add(foo)
        self.session.commit()
        response = self.app.get('/api/stringid/1')
        self.assertEqual(200, response.status_code)
        data = loads(response.data)
        self.assertIn('name', data)
        self.assertEqual('1', data['name'])
        response = self.app.get('/api/stringid/01')
        self.assertEqual(404, response.status_code)

        bar = StringID(name='01')
        self.session.add(bar)
        self.session.commit()
        response = self.app.get('/api/stringid/01')
        self.assertEqual(200, response.status_code)
        data = loads(response.data)
        self.assertIn('name', data)
        self.assertEqual('01', data['name'])

        baz = StringID(name='hey')
        self.session.add(baz)
        self.session.commit()
        response = self.app.get('/api/stringid/hey')
        self.assertEqual(200, response.status_code)
        data = loads(response.data)
        self.assertIn('name', data)
        self.assertEqual('hey', data['name'])

    def test_jsonp(self):
        """Test for JSON-P callbacks."""
        person1 = self.Person(name='foo')
        person2 = self.Person(name='bar')
        self.session.add_all([person1, person2])
        self.session.commit()
        # test for GET
        response = self.app.get('/api/person/1?callback=baz')
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.data.startswith('baz('))
        self.assertTrue(response.data.endswith(')'))
        # test for search
        response = self.app.get('/api/person?callback=baz')
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.data.startswith('baz('))
        self.assertTrue(response.data.endswith(')'))

    def test_duplicate_post(self):
        """Tests for making a :http:method:`post` request with data that
        already exists in the database.

        """
        data = dict(name='test')
        response = self.app.post('/api/person', data=dumps(data))
        self.assertEqual(201, response.status_code)
        response = self.app.post('/api/person', data=dumps(data))
        self.assertEqual(400, response.status_code)


def load_tests(loader, standard_tests, pattern):
    """Returns the test suite for this module."""
    suite = TestSuite()
    suite.addTest(loader.loadTestsFromTestCase(ModelTestCase))
    suite.addTest(loader.loadTestsFromTestCase(FSAModelTest))
    suite.addTest(loader.loadTestsFromTestCase(FunctionAPITestCase))
    suite.addTest(loader.loadTestsFromTestCase(FunctionEvaluationTest))
    suite.addTest(loader.loadTestsFromTestCase(APITestCase))
    return suite
