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
from json import dumps
from json import loads
from tempfile import mkstemp
import os
import unittest

from elixir import create_all
from elixir import drop_all
from elixir import session
import flask
from sqlalchemy import create_engine

from flask.ext.restless import APIManager
from .models import setup
from .models import Computer
from .models import Person


class APITestCase(unittest.TestCase):
    """Unit tests for the :class:`flask_restless.views.API` class."""

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`testapp.Person` and
        :class:`testapp.Computer` models.

        """
        # create the database
        self.db_fd, self.db_file = mkstemp()
        setup(create_engine('sqlite:///%s' % self.db_file))
        create_all()

        # create the Flask application
        app = flask.Flask(__name__)
        app.config['DEBUG'] = True
        app.config['TESTING'] = True
        self.app = app.test_client()

        # setup the URLs for the Person and Computer API
        manager = APIManager(app)
        manager.create_api(Person, methods=['GET', 'PATCH', 'POST', 'DELETE'])
        manager.create_api(Computer, methods=['GET', 'POST'])

        # to facilitate searching
        self.app.search = lambda url, q: self.app.get(url + '?q={}'.format(q))

    def tearDown(self):
        """Drops all tables from the temporary database and closes and unlink
        the temporary file in which it lived.

        """
        drop_all()
        session.commit()
        os.close(self.db_fd)
        os.unlink(self.db_file)

    def test_post(self):
        """Test for creating a new instance of the database model using the
        :http:method:`post` method.

        """
        # Invalid JSON in request data should respond with error.
        response = self.app.post('/api/Person', data='Invalid JSON string')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(loads(response.data)['message'],
                         'Unable to decode data')

        # Now, let's test the validation stuff
        # response = self.app.post('/api/Person', data=dumps({'name': u'Test',
        #                                                      'age': 'oi'}))
        # assert loads(response.data)['message'] == 'Validation error'
        # assert loads(response.data)['error_list'].keys() == ['age']

        response = self.app.post('/api/Person',
                                 data=dumps({'name': 'Lincoln', 'age': 23}))
        self.assertEqual(response.status_code, 201)
        self.assertIn('id', loads(response.data))

        response = self.app.get('/api/Person/1')
        self.assertEqual(response.status_code, 200)

        deep = {'computers': []}
        inst = Person.get_by(id=1).to_dict(deep)
        self.assertEqual(loads(response.data), inst)

    def test_post_with_submodels(self):
        """Tests the creation of a model with a related field."""
        data = {'name': u'John', 'age': 2041,
                'computers': [{'name': u'lixeiro', 'vendor': u'Lemote'}]}
        response = self.app.post('/api/Person', data=dumps(data))
        self.assertEqual(response.status_code, 201)
        self.assertIn('id', loads(response.data))

        response = self.app.get('/api/Person')
        self.assertEqual(len(loads(response.data)), 1)

    def test_delete(self):
        """Test for deleting an instance of the database using the
        :http:method:`delete` method.

        """
        # Creating the person who's gonna be deleted
        response = self.app.post('/api/Person',
                                 data=dumps({'name': 'Lincoln', 'age': 23}))
        self.assertEqual(response.status_code, 201)
        self.assertIn('id', loads(response.data))

        # Making sure it has been created
        deep = {'computers': []}
        inst = Person.get_by(id=1).to_dict(deep)
        response = self.app.get('/api/Person/1')
        self.assertEqual(loads(response.data), inst)

        # Deleting it
        response = self.app.delete('/api/Person/1')
        self.assertEqual(response.status_code, 204)

        # Making sure it has been deleted
        self.assertIsNone(Person.get_by(id=1))

    def test_delete_absent_instance(self):
        """Test that deleting an instance of the model which does not exist
        fails.

        This should give us the same response as when there is an object there,
        since the :http:method:`delete` method is an idempotent method.

        """
        response = self.app.delete('/api/Person/1')
        self.assertEqual(response.status_code, 204)

    def test_patch_many(self):
        """Test for updating a collection of instances of the model using the
        :http:method:`patch` method.

        """
        # Creating some people
        self.app.post('/api/Person',
                      data=dumps({'name': 'Lincoln', 'age': 23}))
        self.app.post('/api/Person',
                      data=dumps({'name': 'Lucy', 'age': 23}))
        self.app.post('/api/Person',
                      data=dumps({'name': 'Mary', 'age': 25}))

        # Trying to pass invalid data to the update method
        # resp = self.app.patch('/api/Person', data='Hello there')
        # assert loads(resp.data)['message'] == 'Unable to decode data'

        # Trying to pass valid JSON with invalid object to the API
        # resp = self.app.patch('/api/Person', data=dumps({'age': 'Hello'}))
        # assert resp.status_code == 400
        # loaded = loads(resp.data)
        # assert loaded['message'] == 'Validation error'
        # assert loaded['error_list'] == [{'age': 'Please enter a number'}]

        # Passing invalid search fields to test the exceptions
        # resp = self.app.patch('/api/Person', data=dumps({'age': 'Hello'}),
        #                     query_string=dict(name='age', op='gt', val='test'))
        # loaded = loads(resp.data)
        # assert loaded['message'] == 'Validation error'
        # assert loaded['error_list'] == [{'age': 'Please enter a number'}]

        # Changing the birth date field of the entire collection
        day, month, year = 15, 9, 1986
        birth_date = date(year, month, day).strftime('%d/%m/%Y')  # iso8601
        form = {'birth_date': birth_date}
        self.app.patch('/api/Person', data=dumps(form))

        # Finally, testing if the change was made
        response = self.app.get('/api/Person')
        loaded = loads(response.data)['objects']
        for i in loaded:
            self.assertEqual(i['birth_date'], ('%s-%s-%s' % (
                    year, str(month).zfill(2), str(day).zfill(2))))

    def test_single_update(self):
        """Test for updating a single instance of the model using the
        :http:method:`patch` method.

        """
        resp = self.app.post('/api/Person', data=dumps({'name': 'Lincoln',
                                                         'age': 10}))
        self.assertEqual(resp.status_code, 201)
        self.assertIn('id', loads(resp.data))

        # Trying to pass invalid data to the update method
        resp = self.app.patch('/api/Person/1', data='Invalid JSON string')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(loads(resp.data)['message'], 'Unable to decode data')

        # Trying to pass valid JSON but an invalid value to the API
        # resp = self.app.patch('/api/Person/1',
        #                     data=dumps({'age': 'Hello there'}))
        # assert resp.status_code == 400
        # loaded = loads(resp.data)
        # assert loaded['message'] == 'Validation error'
        # assert loaded['error_list'] == [{'age': 'Please enter a number'}]

        resp = self.app.patch('/api/Person/1', data=dumps({'age': 24}))
        self.assertEqual(resp.status_code, 200)

        resp = self.app.get('/api/Person/1')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['age'], 24)

    def test_patch_add_submodel(self):
        """Test for updating a single instance of the model by adding a related
        model using the :http:method:`patch` method.

        """
        # Let's create a row as usual
        response = self.app.post('/api/Person',
                                 data=dumps({'name': u'Lincoln', 'age': 23}))
        self.assertEqual(response.status_code, 201)

        data = {'computers':
                    {'add': [{'name': u'lixeiro', 'vendor': u'Lemote'}]}
                }
        response = self.app.patch('/api/Person/1', data=dumps(data))
        self.assertEqual(response.status_code, 200)

        # Let's check it out
        response = self.app.get('/api/Person/1')
        loaded = loads(response.data)

        self.assertEqual(len(loaded['computers']), 1)
        self.assertEqual(loaded['computers'][0]['name'],
                         data['computers']['add'][0]['name'])
        self.assertEqual(loaded['computers'][0]['vendor'],
                         data['computers']['add'][0]['vendor'])

        # test that this new computer was added to the database as well
        computer = Computer.get_by(id=1)
        self.assertIsNotNone(computer)
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
        self.app.post('/api/Person', data=dumps(data))

        # Data for the update
        update_data = {
            'computers': {
                'remove': [{'name': u'pidinti'}],
            }
        }
        resp = self.app.patch('/api/Person/1', data=dumps(update_data))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['id'], 1)

        # Let's check it out
        response = self.app.get('/api/Person/1')
        loaded = loads(response.data)
        self.assertEqual(len(loaded['computers']), 1)

    def test_patch_autodelete_submodel(self):
        """Tests the automatic deletion of entries marked with the
        ``__delete__`` flag on an update operation.

        It also tests adding an already created instance as a related item.

        """
        # Creating all rows needed in our test
        person_data = {'name': u'Lincoln', 'age': 23}
        resp = self.app.post('/api/Person', data=dumps(person_data))
        self.assertEqual(resp.status_code, 201)
        comp_data = {'name': u'lixeiro', 'vendor': u'Lemote'}
        resp = self.app.post('/api/Computer', data=dumps(comp_data))
        self.assertEqual(resp.status_code, 201)

        # updating person to add the computer
        update_data = {'computers': {'add': [{'id': 1}]}}
        self.app.patch('/api/Person/1', data=dumps(update_data))

        # Making sure that everything worked properly
        resp = self.app.get('/api/Person/1')
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
        resp = self.app.patch('/api/Person/1', data=dumps(update2_data))
        self.assertEqual(resp.status_code, 200)

        # Testing to make sure it was removed from the related field
        resp = self.app.get('/api/Person/1')
        self.assertEqual(resp.status_code, 200)
        loaded = loads(resp.data)
        self.assertEqual(len(loaded['computers']), 0)

        # Making sure it was removed from the database
        resp = self.app.get('/api/Computer/1')
        self.assertEqual(resp.status_code, 404)

    def test_search(self):
        """Tests basic search using the :http:method:`get` method."""
        # Trying to pass invalid params to the search method
        # TODO this is no longer a valid test, since the query is no longer
        # passed as JSON in body of the request
        #resp = self.app.get('/api/Person', query_string='Test')
        #assert resp.status_code == 400
        #assert loads(resp.data)['message'] == 'Unable to decode data'

        create = lambda x: self.app.post('/api/Person', data=dumps(x))
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
        resp = self.app.search('/api/Person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        loaded = loads(resp.data)
        self.assertEqual(len(loaded['objects']), 3)  # Mary, Lucy and Katy

        # Let's try something more complex, let's sum all age values
        # available in our database
        search = {
            'functions': [{'name': 'sum', 'field': 'age'}]
        }

        resp = self.app.search('/api/Person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        data = loads(resp.data)
        self.assertIn('sum__age', data)
        self.assertEqual(data['sum__age'], 102.0)

        # Tests searching for a single row
        search = {
            'single': True,      # I'm sure we have only one row here
            'filters': [
                {'name': 'name', 'val': u'Lincoln', 'op': 'equals'}
            ],
        }
        resp = self.app.search('/api/Person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['name'], u'Lincoln')

        # Looking for something that does not exist on the database
        search['filters'][0]['val'] = 'Sammy'
        resp = self.app.search('/api/Person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['message'], 'No result found')

        # We have to receive an error if the user provides an invalid
        # data to the search, like this:
        search = {
            'filters': [
                {'name': 'age', 'val': 'It should not be a string', 'op': 'gt'}
            ]
        }
        resp = self.app.search('/api/Person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        #assert loads(resp.data)['error_list'][0] == \
        #    {'age': 'Please enter a number'}
        self.assertEqual(len(loads(resp.data)['objects']), 0)

        # Testing the order_by stuff
        search = {'order_by': [{'field': 'age', 'direction': 'asc'}]}
        resp = self.app.search('/api/Person', dumps(search))
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
        resp = self.app.search('/api/Person', dumps(search))
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
        resp = self.app.patch('/api/Person/1', data=dumps(update))
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
        resp = self.app.search('/api/Person', dumps(search))
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
        resp = self.app.search('/api/Person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        loaded = loads(resp.data)['objects']
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]['other'], 10)
        self.assertEqual(loaded[1]['other'], 19)

    def test_poorly_defined_functions(self):
        """Tests that poorly defined requests for function evaluations cause an
        error message to be returned.

        """
        # test for bad field name
        search = {'functions': [{'name': 'sum', 'field': 'bogusfieldname'}]}
        resp = self.app.search('/api/Person', dumps(search))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('message', loads(resp.data))
        self.assertIn('bogusfieldname', loads(resp.data)['message'])

        # test for bad function name
        search = {'functions': [{'name': 'bogusfuncname', 'field': 'age'}]}
        resp = self.app.search('/api/Person', dumps(search))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('message', loads(resp.data))
        self.assertIn('bogusfuncname', loads(resp.data)['message'])

    def test_search2(self):
        """Testing more search functionality."""
        create = lambda x: self.app.post('/api/Person', data=dumps(x))
        create({'name': u'Fuxu', 'age': 32})
        create({'name': u'Everton', 'age': 33})
        create({'name': u'Lincoln', 'age': 24})

        # Let's test the search using an id
        search = {
            'single': True,
            'filters': [{'name': 'id', 'op': 'equal_to', 'val': 1}]
        }
        resp = self.app.search('/api/Person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['name'], u'Fuxu')

        # Testing limit and offset
        search = {'limit': 1, 'offset': 1}
        resp = self.app.search('/api/Person', dumps(search))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['objects'][0]['name'], u'Everton')

        # Testing multiple results when calling .one()
        resp = self.app.search('/api/Person', dumps({'single': True}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['message'], 'Multiple results found')
