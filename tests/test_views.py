# -*- coding: utf-8; Mode: Python -*-
#
# Copyright (C) 2011 Lincoln de Sousa <lincoln@comum.org>
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
"""Unit tests for the :mod:`flask_restless.views` module."""
from datetime import date
from unittest import TestSuite

from flask import json
from sqlalchemy.exc import OperationalError

from flask.ext.restless.views import _evaluate_functions as evaluate_functions
from flask.ext.restless.manager import IllegalArgumentError

from .helpers import TestSupportPrefilled
from .helpers import TestSupportWithManager
from .helpers import TestSupportWithManagerPrefilled
from .models import Computer
from .models import Person


__all__ = ['FunctionEvaluationTest', 'FunctionAPITestCase', 'APITestCase']


dumps = json.dumps
loads = json.loads


class FunctionEvaluationTest(TestSupportPrefilled):
    """Unit tests for the :func:`flask_restless.view._evaluate_functions`
    function.

    """

    def test_basic_evaluation(self):
        """Tests for basic function evaluation."""
        # test for no model
        result = evaluate_functions(None, [])
        self.assertEqual(result, {})

        # test for no functions
        result = evaluate_functions(Person, [])
        self.assertEqual(result, {})

        # test for summing ages
        functions = [{'name': 'sum', 'field': 'age'}]
        result = evaluate_functions(Person, functions)
        self.assert_in('sum__age', result)
        self.assertEqual(result['sum__age'], 102.0)

        # test for multiple functions
        functions = [{'name': 'sum', 'field': 'age'},
                     {'name': 'avg', 'field': 'other'}]
        result = evaluate_functions(Person, functions)
        self.assert_in('sum__age', result)
        self.assertEqual(result['sum__age'], 102.0)
        self.assert_in('avg__other', result)
        self.assertEqual(result['avg__other'], 16.2)

    def test_poorly_defined_functions(self):
        """Tests that poorly defined functions raise errors."""
        # test for unknown field
        functions = [{'name': 'sum', 'field': 'bogus'}]
        self.assertRaises(AttributeError, evaluate_functions,
                          *(Person, functions))

        # test for unknown function
        functions = [{'name': 'bogus', 'field': 'age'}]
        self.assertRaises(OperationalError, evaluate_functions,
                          *(Person, functions))


class FunctionAPITestCase(TestSupportWithManagerPrefilled):
    """Unit tests for the :class:`flask_restless.views.FunctionAPI` class."""

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`testapp.Person` and
        :class:`testapp.Computer` models.

        """
        super(FunctionAPITestCase, self).setUp()
        self.manager.create_api(Person, allow_functions=True)

    def test_function_evaluation(self):
        """Test that the :http:get:`/api/eval/person` endpoint returns the
        result of evaluating functions.

        """
        functions = [{'name': 'sum', 'field': 'age'},
                     {'name': 'avg', 'field': 'other'}]
        response = self.app.get('/api/eval/person',
                                data=dumps(dict(functions=functions)))
        self.assertEqual(response.status_code, 200)
        data = loads(response.data)
        self.assert_in('sum__age', data)
        self.assertEqual(data['sum__age'], 102.0)
        self.assert_in('avg__other', data)
        self.assertEqual(data['avg__other'], 16.2)

    def test_poorly_defined_functions(self):
        """Tests that poorly defined requests for function evaluations cause an
        error message to be returned.

        """
        # test for bad field name
        search = {'functions': [{'name': 'sum', 'field': 'bogusfieldname'}]}
        resp = self.app.get('/api/eval/person', data=dumps(search))
        self.assertEqual(resp.status_code, 400)
        self.assert_in('message', loads(resp.data))
        self.assert_in('bogusfieldname', loads(resp.data)['message'])

        # test for bad function name
        search = {'functions': [{'name': 'bogusfuncname', 'field': 'age'}]}
        resp = self.app.get('/api/eval/person', data=dumps(search))
        self.assertEqual(resp.status_code, 400)
        self.assert_in('message', loads(resp.data))
        self.assert_in('bogusfuncname', loads(resp.data)['message'])


class APITestCase(TestSupportWithManager):
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
        self.manager.create_api(Person, methods=['GET', 'PATCH', 'POST',
                                                 'DELETE'])
        self.manager.create_api(Computer, methods=['GET', 'POST'])

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
                                 data=dumps({'name': 'Lincoln', 'age': 23}))
        self.assertEqual(response.status_code, 201)
        self.assert_in('id', loads(response.data))

        response = self.app.get('/api/person/1')
        self.assertEqual(response.status_code, 200)

        deep = {'computers': []}
        inst = Person.get_by(id=1).to_dict(deep)
        self.assertEqual(loads(response.data), inst)

    def test_post_with_submodels(self):
        """Tests the creation of a model with a related field."""
        data = {'name': u'John', 'age': 2041,
                'computers': [{'name': u'lixeiro', 'vendor': u'Lemote'}]}
        response = self.app.post('/api/person', data=dumps(data))
        self.assertEqual(response.status_code, 201)
        self.assert_in('id', loads(response.data))

        response = self.app.get('/api/person')
        self.assertEqual(len(loads(response.data)), 1)

    def test_delete(self):
        """Test for deleting an instance of the database using the
        :http:method:`delete` method.

        """
        # Creating the person who's gonna be deleted
        response = self.app.post('/api/person',
                                 data=dumps({'name': 'Lincoln', 'age': 23}))
        self.assertEqual(response.status_code, 201)
        self.assert_in('id', loads(response.data))

        # Making sure it has been created
        deep = {'computers': []}
        inst = Person.get_by(id=1).to_dict(deep)
        response = self.app.get('/api/person/1')
        self.assertEqual(loads(response.data), inst)

        # Deleting it
        response = self.app.delete('/api/person/1')
        self.assertEqual(response.status_code, 204)

        # Making sure it has been deleted
        self.assert_is_none(Person.get_by(id=1))

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
        self.manager.create_api(Person, methods=['GET', 'POST', 'PUT'],
                                allow_patch_many=True, url_prefix='/api/v2')

        # Creating some people
        self.app.post('/api/v2/person',
                      data=dumps({'name': 'Lincoln', 'age': 23}))
        self.app.post('/api/v2/person',
                      data=dumps({'name': 'Lucy', 'age': 23}))
        self.app.post('/api/v2/person',
                      data=dumps({'name': 'Mary', 'age': 25}))

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

    def test_patch_many(self):
        """Test for updating a collection of instances of the model using the
        :http:method:`patch` method.

        """
        # recreate the api to allow patch many at /api/v2/person
        self.manager.create_api(Person, methods=['GET', 'POST', 'PATCH'],
                                allow_patch_many=True, url_prefix='/api/v2')

        # Creating some people
        self.app.post('/api/v2/person',
                      data=dumps({'name': 'Lincoln', 'age': 23}))
        self.app.post('/api/v2/person',
                      data=dumps({'name': 'Lucy', 'age': 23}))
        self.app.post('/api/v2/person',
                      data=dumps({'name': 'Mary', 'age': 25}))

        # Trying to pass invalid data to the update method
        # resp = self.app.patch('/api/person', data='Hello there')
        # assert loads(resp.data)['message'] == 'Unable to decode data'

        # Trying to pass valid JSON with invalid object to the API
        # resp = self.app.patch('/api/person', data=dumps({'age': 'Hello'}))
        # assert resp.status_code == 400
        # loaded = loads(resp.data)
        # assert loaded['message'] == 'Validation error'
        # assert loaded['error_list'] == [{'age': 'Please enter a number'}]

        # Passing invalid search fields to test the exceptions
        # resp = self.app.patch('/api/person', data=dumps({'age': 'Hello'}),
        #                     query_string=dict(name='age', op='gt', val='test'))
        # loaded = loads(resp.data)
        # assert loaded['message'] == 'Validation error'
        # assert loaded['error_list'] == [{'age': 'Please enter a number'}]

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

    def test_single_update(self):
        """Test for updating a single instance of the model using the
        :http:method:`patch` method.

        """
        resp = self.app.post('/api/person', data=dumps({'name': 'Lincoln',
                                                         'age': 10}))
        self.assertEqual(resp.status_code, 201)
        self.assert_in('id', loads(resp.data))

        # Trying to pass invalid data to the update method
        resp = self.app.patch('/api/person/1', data='Invalid JSON string')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(loads(resp.data)['message'], 'Unable to decode data')

        # Trying to pass valid JSON but an invalid value to the API
        # resp = self.app.patch('/api/person/1',
        #                     data=dumps({'age': 'Hello there'}))
        # assert resp.status_code == 400
        # loaded = loads(resp.data)
        # assert loaded['message'] == 'Validation error'
        # assert loaded['error_list'] == [{'age': 'Please enter a number'}]

        resp = self.app.patch('/api/person/1', data=dumps({'age': 24}))
        self.assertEqual(resp.status_code, 200)

        resp = self.app.get('/api/person/1')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['age'], 24)

    def test_patch_add_submodel(self):
        """Test for updating a single instance of the model by adding a related
        model using the :http:method:`patch` method.

        """
        # Let's create a row as usual
        response = self.app.post('/api/person',
                                 data=dumps({'name': u'Lincoln', 'age': 23}))
        self.assertEqual(response.status_code, 201)

        data = {'computers':
                    {'add': [{'name': u'lixeiro', 'vendor': u'Lemote'}]}
                }
        response = self.app.patch('/api/person/1', data=dumps(data))
        self.assertEqual(response.status_code, 200)

        # Let's check it out
        response = self.app.get('/api/person/1')
        loaded = loads(response.data)

        self.assertEqual(len(loaded['computers']), 1)
        self.assertEqual(loaded['computers'][0]['name'],
                         data['computers']['add'][0]['name'])
        self.assertEqual(loaded['computers'][0]['vendor'],
                         data['computers']['add'][0]['vendor'])

        # test that this new computer was added to the database as well
        computer = Computer.get_by(id=1)
        self.assert_is_not_none(computer)
        self.assertEqual(data['computers']['add'][0]['name'], computer.name)
        self.assertEqual(data['computers']['add'][0]['vendor'],
                         computer.vendor)

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
        # TODO this is no longer a valid test, since the query is no longer
        # passed as JSON in body of the request
        #resp = self.app.get('/api/person', query_string='Test')
        #assert resp.status_code == 400
        #assert loads(resp.data)['message'] == 'Unable to decode data'

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

        # # Let's try something more complex, let's sum all age values
        # # available in our database
        # search = {
        #     'functions': [{'name': 'sum', 'field': 'age'}]
        # }

        # resp = self.app.search('/api/person', dumps(search))
        # self.assertEqual(resp.status_code, 200)
        # data = loads(resp.data)
        # self.assertIn('sum__age', data)
        # self.assertEqual(data['sum__age'], 102.0)

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
        # TODO what is this? document it.
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
        self.assertEqual(loads(resp.data)['objects'][0]['name'], u'Everton')

        # Testing multiple results when calling .one()
        resp = self.app.search('/api/person', dumps({'single': True}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['message'], 'Multiple results found')

    def test_authentication(self):
        """Tests basic authentication using custom authentication functions."""
        # must provide authentication function if authentication is required
        # for some HTTP methods
        self.assertRaises(IllegalArgumentError, self.manager.create_api,
                          *(Person, ),
                          **dict(methods=['GET', 'POST'],
                                 authentication_required_for=['POST']))

        # test for authentication always failing
        self.manager.create_api(Person, methods=['GET', 'POST'],
                                url_prefix='/api/v2',
                                authentication_required_for=['POST'],
                                authentication_function=lambda: False)

        # a slightly more complicated function; all odd calls are authenticated
        class everyother(object):
            """Stores the number of times this object has been called."""

            def __init__(self):
                """Initialize the number of calls to 0."""
                self.count = 0

            def __call__(self):
                """Increment the call count and return its parity."""
                self.count += 1
                return self.count % 2

        self.manager.create_api(Person, methods=['GET'], url_prefix='/api/v3',
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


def load_tests(loader, standard_tests, pattern):
    """Returns the test suite for this module."""
    suite = TestSuite()
    suite.addTest(loader.loadTestsFromTestCase(FunctionAPITestCase))
    suite.addTest(loader.loadTestsFromTestCase(FunctionEvaluationTest))
    suite.addTest(loader.loadTestsFromTestCase(APITestCase))
    return suite
