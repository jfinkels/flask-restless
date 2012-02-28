# -*- coding: utf-8; Mode: Python -*-
#
# Copyright (C) 2011  Lincoln de Sousa <lincoln@comum.org>
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

import unittest
import os
from tempfile import mkstemp
from datetime import date, datetime

import flask
from json import dumps, loads
from elixir import create_all, session, drop_all
from sqlalchemy import create_engine

from restful import model#, api
from restful.api import APIManager
from testapp import models  #, validators


class ModelTestCase(unittest.TestCase):
    """Tests focused on `restful.model` module
    """

    def setUp(self):
        self.db_fd, self.db_file = mkstemp()
        models.setup(create_engine('sqlite:///%s' % self.db_file))
        create_all()
        session.commit()

        self.model = models.Person

    def tearDown(self):
        """Destroying the sqlite database file
        """
        drop_all()
        session.commit()
        os.close(self.db_fd)
        os.unlink(self.db_file)

    def test_column_introspection(self):
        """Makes sure that the column list works properly
        """
        columns = self.model.get_columns()
        assert sorted(columns.keys()) == sorted([
                'age', 'birth_date', 'computers', 'id', 'name', 'other'])
        relations = models.Person.get_relations()
        assert relations == ['computers']

    def test_instance_introspection(self):
        """Testing the instance introspection
        """
        me = self.model()
        me.name = u'Lincoln'
        me.age = 24
        me.birth_date = date(1986, 9, 15)
        session.commit()

        me_dict = me.to_dict()
        assert sorted(me_dict.keys()) == sorted([
                'birth_date', 'age', 'id', 'name', 'other'])
        assert me_dict['name'] == u'Lincoln'
        assert me_dict['age'] == 24

    def test_deep_introspection(self):
        """Testing the introspection of related fields
        """
        someone = self.model()
        someone.name = u'John'
        someone.age = 25
        computer1 = models.Computer()
        computer1.name = u'lixeiro'
        computer1.vendor = u'Lemote'
        computer1.owner = someone
        computer1.buy_date = datetime.now()
        session.commit()

        relations = models.Person.get_relations()
        deep = dict(zip(relations, [{}] * len(relations)))

        computers = someone.to_dict(deep)['computers']
        assert len(computers) == 1
        assert computers[0]['name'] == u'lixeiro'
        assert computers[0]['vendor'] == u'Lemote'

    def test_get_or_create(self):
        """Testing the model.get_or_create() method
        """
        # Here we're sure that we have a fresh table with no rows, so
        # let's create the first one:
        instance, created = self.model.get_or_create(name=u'Lincoln', age=24)
        assert created
        assert instance.name == u'Lincoln'
        assert instance.age == 24

        # Now that we have a row, let's try to get it again
        second_instance, created = self.model.get_or_create(name=u'Lincoln')
        assert not created
        assert second_instance.name == u'Lincoln'
        assert second_instance.age == 24


class RestfulTestCase(unittest.TestCase):
    """Test case class for the restful api itself
    """

    def setUp(self):
        """Sets up the database and the flask app
        """
        self.db_fd, self.db_file = mkstemp()
        models.setup(create_engine('sqlite:///%s' % self.db_file))
        create_all()

        app = flask.Flask(__name__)
        app.config['DEBUG'] = True
        app.config['TESTING'] = True
        #api.setup(models, validators)
        manager = APIManager(app)
        # setup the URLs for the Person and Computer API
        # TODO move validators to use sqlalchemy-validation
        manager.create_api(models.Person, #validators=validators.allvalidators,
                           methods=['GET', 'PATCH', 'POST', 'DELETE'])
        manager.create_api(models.Computer,
                           #validators=validators.allvalidators,
                           methods=['GET', 'POST'])
        #app.register_blueprint(api.blueprint, url_prefix="/api")
        self.app = app.test_client()
        # To facilitate searching
        self.app.search = lambda url, query: \
            self.app.get(url + '?q={}'.format(query))

    def tearDown(self):
        """Destroying the sqlite database file
        """
        drop_all()
        session.commit()
        os.close(self.db_fd)
        os.unlink(self.db_file)

    # def test_setup(self):
    #     """Just to make sure that everything worked while setting up api
    #     """
    #     assert api.CONFIG['models'] is models
    #     assert api.CONFIG['validators'] is validators

    def test_new_person(self):
        """Tests the creation of new persons
        """
        # Invalid JSON in request data should respond with error.
        response = self.app.post('/api/Person', data='Invalid JSON string')
        assert response.status_code == 400
        assert loads(response.data)['message'] == 'Unable to decode data'

        # Now, let's test the validation stuff
        # response = self.app.post('/api/Person', data=dumps({'name': u'Test',
        #                                                      'age': 'oi'}))
        # assert loads(response.data)['message'] == 'Validation error'
        # assert loads(response.data)['error_list'].keys() == ['age']

        response = self.app.post('/api/Person',
                                 data=dumps({'name': 'Lincoln', 'age': 23}))
        assert response.status_code == 201
        assert 'id' in loads(response.data)

        response = self.app.get('/api/Person/1')
        assert response.status_code == 200

        deep = {'computers': []}
        inst = models.Person.get_by(id=1).to_dict(deep)
        assert loads(response.data) == inst

    def test_new_with_submodels(self):
        """Tests the creation of a model with some related fields
        """
        data = {'name': u'John', 'age': 2041,
                'computers': [{'name': u'lixeiro', 'vendor': u'Lemote'}]}
        response = self.app.post('/api/Person', data=dumps(data))
        assert response.status_code == 201
        assert 'id' in loads(response.data)

        response = self.app.get('/api/Person')
        assert len(loads(response.data)) == 1

    def test_remove_person(self):
        """Adds a new person and tests its removal.
        """
        # Creating the person who's gonna be deleted
        response = self.app.post('/api/Person',
                                 data=dumps({'name': 'Lincoln', 'age': 23}))
        assert response.status_code == 201
        assert 'id' in loads(response.data)

        # Making sure it has been created
        deep = {'computers': []}
        inst = models.Person.get_by(id=1).to_dict(deep)
        response = self.app.get('/api/Person/1')
        assert loads(response.data) == inst

        # Deleting it
        response = self.app.delete('/api/Person/1')
        assert response.status_code == 204

        # Making sure it has been deleted
        assert models.Person.get_by(id=1) is None

    def test_remove_absent_person(self):
        """Tests the removal of someone that is not in the database.

        This should give us the same response as when there is an object there,
        since the :http:method:`delete` method is an idempotent method.

        """
        response = self.app.delete('/api/Person/1')
        assert response.status_code == 204

    def test_update(self):
        """Tests the update (:http:method:`patch`) operation on a collection.

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
            assert i['birth_date'] == ('%s-%s-%s' % (
                    year, str(month).zfill(2), str(day).zfill(2)))

    def test_single_update(self):
        """Tests the update (:http:method:`patch`) operation on a single
        instance.

        """
        resp = self.app.post('/api/Person', data=dumps({'name': 'Lincoln',
                                                         'age': 10}))
        assert resp.status_code == 201
        assert 'id' in loads(resp.data)

        # Trying to pass invalid data to the update method
        resp = self.app.patch('/api/Person/1', data='Invalid JSON string')
        assert resp.status_code == 400
        assert loads(resp.data)['message'] == 'Unable to decode data'

        # Trying to pass valid JSON but an invalid value to the API
        # resp = self.app.patch('/api/Person/1',
        #                     data=dumps({'age': 'Hello there'}))
        # assert resp.status_code == 400
        # loaded = loads(resp.data)
        # assert loaded['message'] == 'Validation error'
        # assert loaded['error_list'] == [{'age': 'Please enter a number'}]

        resp = self.app.patch('/api/Person/1', data=dumps({'age': 24}))
        assert resp.status_code == 200

        resp = self.app.get('/api/Person/1')
        assert resp.status_code == 200
        assert loads(resp.data)['age'] == 24

    def test_update_submodels(self):
        """Tests the update (:http:method:`put`) operation with submodels."""
        # Let's create a row as usual
        response = self.app.post('/api/Person',
                                 data=dumps({'name': u'Lincoln', 'age': 23}))
        assert response.status_code == 201

        data = {'computers':
                    {'add': [{'name': u'lixeiro', 'vendor': u'Lemote'}]}
                }
        response = self.app.patch('/api/Person/1', data=dumps(data))
        assert response.status_code == 200

        # Let's check it out
        response = self.app.get('/api/Person/1')
        loaded = loads(response.data)

        assert len(loaded['computers']) == 1
        assert loaded['computers'][0]['name'] == \
            data['computers']['add'][0]['name']
        assert loaded['computers'][0]['vendor'] == \
            data['computers']['add'][0]['vendor']

    def test_update_submodels2(self):
        """Tests the removal of a submodel item when updating."""
        # Creating the row that is gonna be updated
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
                'remove': [{'name': u'pidinti'}],  # It was stolen :(
            }
        }
        resp = self.app.patch('/api/Person/1', data=dumps(update_data))
        assert resp.status_code == 200
        assert loads(resp.data)['id'] == 1

        # Let's check it out
        response = self.app.get('/api/Person/1')
        loaded = loads(response.data)
        assert len(loaded['computers']) == 1

    def test_update_submodels3(self):
        """Tests the automatic deletion of entries marked with the
        ``__delete__`` flag on an update operation.

        It also tests adding an already created instance as a related item.

        """
        # Creating all rows needed in our test
        person_data = {'name': u'Lincoln', 'age': 23}
        resp = self.app.post('/api/Person', data=dumps(person_data))
        assert resp.status_code == 201
        comp_data = {'name': u'lixeiro', 'vendor': u'Lemote'}
        resp = self.app.post('/api/Computer', data=dumps(comp_data))
        assert resp.status_code == 201

        # updating person to add the computer
        update_data = {'computers': {'add': [{'id': 1}]}}
        self.app.patch('/api/Person/1', data=dumps(update_data))

        # Making sure that everything worked properly
        resp = self.app.get('/api/Person/1')
        assert resp.status_code == 200
        loaded = loads(resp.data)
        assert len(loaded['computers']) == 1
        assert loaded['computers'][0]['name'] == u'lixeiro'

        # Now, let's remove it and delete it
        update2_data = {
            'computers': {
                'remove': [
                    {'id': 1, '__delete__': True},
                ],
            },
        }
        resp = self.app.patch('/api/Person/1', data=dumps(update2_data))
        assert resp.status_code == 200

        # Testing to make sure it was removed from the related field
        resp = self.app.get('/api/Person/1')
        assert resp.status_code == 200
        loaded = loads(resp.data)
        assert len(loaded['computers']) == 0

        # Making sure it was removed from the database
        resp = self.app.get('/api/Computer/1')
        assert resp.status_code == 404

    def test_search(self):
        """Tests basic search"""
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
        assert resp.status_code == 200
        loaded = loads(resp.data)
        assert len(loaded['objects']) == 3  # Mary, Lucy and Katy

        # Let's try something more complex, let's sum all age values
        # available in our database
        search = {
            'functions': [{'name': 'sum', 'field': 'age'}]
        }

        resp = self.app.search('/api/Person', dumps(search))
        assert resp.status_code == 200
        data = loads(resp.data)
        assert 'sum__age' in data
        assert data['sum__age'] == 102.0

        # Tests searching for a single row
        search = {
            'type': 'one',      # I'm sure we have only one row here
            'filters': [
                {'name': 'name', 'val': u'Lincoln', 'op': 'equals'}
            ],
        }
        resp = self.app.search('/api/Person', dumps(search))
        assert resp.status_code == 200
        assert loads(resp.data)['name'] == u'Lincoln'

        # Looking for something that does not exist on the database
        search['filters'][0]['val'] = 'Sammy'
        resp = self.app.search('/api/Person', dumps(search))
        assert resp.status_code == 200
        assert loads(resp.data)['message'] == 'No result found'

        # We have to receive an error if the user provides an invalid
        # data to the search, like this:
        search = {
            'filters': [
                {'name': 'age', 'val': 'It should not be a string', 'op': 'gt'}
            ]
        }
        resp = self.app.search('/api/Person', dumps(search))
        assert resp.status_code == 200
        #assert loads(resp.data)['error_list'][0] == \
        #    {'age': 'Please enter a number'}
        assert len(loads(resp.data)['objects']) == 0

        # Testing the order_by stuff
        search = {'order_by': [{'field': 'age', 'direction': 'asc'}]}
        resp = self.app.search('/api/Person', dumps(search))
        assert resp.status_code == 200
        loaded = loads(resp.data)['objects']
        assert loaded[0][u'age'] == 7
        assert loaded[1][u'age'] == 19
        assert loaded[2][u'age'] == 23
        assert loaded[3][u'age'] == 25
        assert loaded[4][u'age'] == 28

        # Test the IN operation
        search = {
            'filters': [
                {'name': 'age', 'val': [7, 28], 'op': 'in'}
            ]
        }
        resp = self.app.search('/api/Person', dumps(search))
        assert resp.status_code == 200
        loaded = loads(resp.data)['objects']
        assert loaded[0][u'age'] == 7
        assert loaded[1][u'age'] == 28

        # Testing related search
        update = {
            'computers': {
                'add': [{'name': u'lixeiro', 'vendor': u'Lenovo'}]
            }
        }
        resp = self.app.patch('/api/Person/1', data=dumps(update))
        assert resp.status_code == 200

        search = {
            'type': 'one',
            'filters': [
                {'name': 'computers__name',
                 'val': u'lixeiro',
                 'op': 'any'}
            ]
        }
        resp = self.app.search('/api/Person', dumps(search))
        assert resp.status_code == 200
        assert loads(resp.data)['computers'][0]['name'] == 'lixeiro'

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
        assert resp.status_code == 200
        loaded = loads(resp.data)['objects']
        assert len(loaded) == 2
        assert loaded[0]['other'] == 10
        assert loaded[1]['other'] == 19

    def test_search2(self):
        """Testing more search things.
        """
        create = lambda x: self.app.post('/api/Person', data=dumps(x))
        create({'name': u'Fuxu', 'age': 32})
        create({'name': u'Everton', 'age': 33})
        create({'name': u'Lincoln', 'age': 24})

        # Let's test the search using an id
        search = {
            'type': 'one',
            'filters': [{'name': 'id', 'op': 'equal_to', 'val': 1}]
        }
        resp = self.app.search('/api/Person', dumps(search))
        assert resp.status_code == 200
        assert loads(resp.data)['name'] == u'Fuxu'

        # Testing limit and offset
        search = {'limit': 1, 'offset': 1}
        resp = self.app.search('/api/Person', dumps(search))
        assert resp.status_code == 200
        assert loads(resp.data)['objects'][0]['name'] == u'Everton'

        # Testing multiple results when calling .one()
        resp = self.app.search('/api/Person', dumps({'type': 'one'}))
        assert resp.status_code == 200
        assert loads(resp.data)['message'] == 'Multiple results found'


def suite():
    test_suite = unittest.TestSuite()
    test_suite.addTest(unittest.makeSuite(ModelTestCase))
    test_suite.addTest(unittest.makeSuite(RestfulTestCase))
    return test_suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
