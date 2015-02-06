"""
    tests.test_processors
    ~~~~~~~~~~~~~~~~~~~~~

    Provides unit tests for pre- and post-processors hooks.

    :copyright: 2013 Mike Klimin <klinkin@gmail.com>
    :copyright: 2012, 2013, 2014, 2015 Jeffrey Finkelstein
                <jeffrey.finkelstein@gmail.com> and contributors.
    :license: GNU AGPLv3+ or BSD

"""
from __future__ import with_statement

from datetime import date

from flask import json
from flask.ext.restless import ProcessingException
from .helpers import TestSupport


dumps = json.dumps
loads = json.loads


class TestProcessors(TestSupport):
    """Unit tests for preprocessors and postprocessors."""

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application.

        """
        # create the database
        super(TestProcessors, self).setUp()

        # to facilitate searching
        self.app.search = lambda url, q: self.app.get(url + '?q={0}'.format(q))

    def test_get_single_preprocessor(self):
        """Tests :http:method:`get` requests for a single object with
        a preprocessor function.

        """

        def check_permissions(**kw):
            raise ProcessingException(code=403,
                                      description='Permission denied')

        pre = dict(GET_SINGLE=[check_permissions])
        self.manager.create_api(self.Person, methods=['GET', 'POST'],
                                preprocessors=pre)
        response = self.app.post('/api/person', data=dumps({'name': u'test'}))
        assert 201 == response.status_code
        response = self.app.get('/api/person/1')
        assert response.status_code == 403
        json_resp = loads(response.data)
        assert 'Permission denied' == json_resp['message']

    def test_change_instance_id(self):
        """Tests that return values from preprocessors set the instance ID."""
        # Create some people.
        alice = self.Person(id=1, name=u'Alice')
        bob = self.Person(id=2, name=u'Bob')
        eve = self.Person(id=3, name=u'Eve')
        self.session.add_all((alice, bob, eve))
        self.session.commit()

        # Define the preprocessor function, which increments the primary key.
        def increment(instance_id=None, **kw):
            if instance_id is None:
                raise Exception
            return int(instance_id) + 1

        # Create an API with the incrementing preprocessor.
        pre = dict(GET_SINGLE=[increment], PATCH_SINGLE=[increment],
                   DELETE_SINGLE=[increment])
        self.manager.create_api(self.Person,
                                methods=['GET', 'PATCH', 'DELETE'],
                                preprocessors=pre)

        # Create an API where the incrementing preprocessor happens twice.
        pre = dict(GET_SINGLE=[increment, increment])
        self.manager.create_api(self.Person, url_prefix='/api/v2',
                                methods=['GET'], preprocessors=pre)

        # Request the person with ID 1; the preprocessor should cause this to
        # return the person with ID 2. Similarly for the person with ID 2.
        response = self.app.get('/api/person/1')
        assert response.status_code == 200
        data = loads(response.data)
        assert data['id'] == 2
        assert data['name'] == u'Bob'
        response = self.app.get('/api/person/2')
        assert response.status_code == 200
        data = loads(response.data)
        assert data['id'] == 3
        assert data['name'] == u'Eve'

        # Request the person with ID 1; the preprocessor should cause this to
        # return the person with ID 3.
        response = self.app.get('/api/v2/person/1')
        assert response.status_code == 200
        data = loads(response.data)
        assert data['id'] == 3
        assert data['name'] == u'Eve'

        # After this patch request, the person with ID *2* should have the name
        # Paul. The response should include the JSON representation of the
        # person with ID *2*, since that is how the view function acts as if it
        # receives ID 2.
        data = dumps(dict(name='Paul'))
        response = self.app.patch('/api/person/1', data=data)
        assert response.status_code == 200
        data = loads(response.data)
        assert data['id'] == 2
        assert data['name'] == u'Paul'

        # Finally, send a request to delete the person with ID 1, but the
        # preprocessor increments the ID, so person number 2 should actually be
        # deleted.
        response = self.app.delete('/api/person/1')
        assert response.status_code == 204
        # Check that there are only two people in the database, and neither of
        # them is the person with ID 2.
        response = self.app.get('/api/person')
        assert response.status_code == 200
        data = loads(response.data)['objects']
        assert len(data) == 2
        assert data[0]['id'] != 2
        assert data[1]['id'] != 2

    def test_get_many_postprocessor(self):
        filt = dict(name='id', op='in', val=[1, 3])

        def foo(search_params=None, **kw):
            assert filt in search_params['filters']

        post = dict(GET_MANY=[foo])
        self.manager.create_api(self.Person, methods=['GET', 'POST'],
                                postprocessors=post)
        query = dict(filters=[filt])
        response = self.app.search('/api/person', dumps(query))
        assert response.status_code == 200

    def test_get_many_preprocessor(self):
        def check_permissions(search_params=None, **kw):
            filt = {u'name': u'id', u'op': u'in', u'val': [1, 3]}
            if 'filters' not in search_params:
                search_params['filters'] = [filt]
            else:
                search_params['filters'].append(filt)

        pre = dict(GET_MANY=[check_permissions])
        self.manager.create_api(self.Person, methods=['GET', 'POST'],
                                preprocessors=pre)

        self.app.post('/api/person',
                      data=dumps({'name': u'Lincoln', 'age': 23}))
        self.app.post('/api/person',
                      data=dumps({'name': u'Lucy', 'age': 23}))
        self.app.post('/api/person',
                      data=dumps({'name': u'Mary', 'age': 25}))

        response = self.app.get('/api/person')
        objs = loads(response.data)['objects']
        ids = [obj['id'] for obj in objs]
        assert ids == [1, 3]
        assert response.status_code == 200

        search = dict(filters=[dict(name='name', val='Lincoln', op='equals')])
        response = self.app.search('/api/person', dumps(search))
        num_results = loads(response.data)['num_results']

        assert num_results == 1
        assert response.status_code == 200

    def test_post_preprocessor(self):
        """Tests :http:method:`post` requests with a preprocessor function."""
        def add_parameter(data=None, **kw):
            if data:
                data['other'] = 7

        def check_permissions(data=None, **kw):
            raise ProcessingException(code=403,
                                      description='Permission denied')

        self.manager.create_api(self.Person, methods=['POST'],
                                url_prefix='/api/v2',
                                preprocessors=dict(POST=[add_parameter]))
        self.manager.create_api(self.Person, methods=['POST'],
                                url_prefix='/api/v3',
                                preprocessors=dict(POST=[check_permissions]))

        response = self.app.post('/api/v2/person',
                                 data=dumps({'name': u'Lincoln', 'age': 23}))
        assert response.status_code == 201

        personid = loads(response.data)['id']
        person = self.session.query(self.Person).filter_by(id=personid).first()
        assert person.other == 7

        response = self.app.post('/api/v3/person',
                                 data=dumps({'name': u'Lincoln', 'age': 23}))
        assert response.status_code == 403
        json_resp = loads(response.data)
        assert 'Permission denied' == json_resp['message']

    def test_delete_preprocessor(self):
        """Tests for using a preprocessor with :http:method:`delete` requests.

        """
        def check_permissions(**kw):
            raise ProcessingException(code=403,
                                      description='Permission denied')

        pre = dict(DELETE_SINGLE=[check_permissions])
        # recreate the api at /api/v1/person
        self.manager.create_api(self.Person,
                                methods=['POST', 'DELETE'],
                                preprocessors=pre)

        # Creating some people
        self.app.post('/api/person',
                      data=dumps({'name': u'Lincoln', 'age': 23}))
        self.app.post('/api/person',
                      data=dumps({'name': u'Lucy', 'age': 23}))
        self.app.post('/api/person',
                      data=dumps({'name': u'Mary', 'age': 25}))

        # Try deleting it
        response = self.app.delete('/api/person/1')
        assert response.status_code == 403
        json_resp = loads(response.data)
        assert 'Permission denied' == json_resp['message']

        # Making sure it has been not deleted
        people = self.session.query(self.Person).filter_by(id=1)
        assert people.count() == 1

    def test_patch_single_preprocessor(self):
        """Tests for using a preprocessor with :http:method:`patch` requests.

        """

        def check_permissions(**kw):
            raise ProcessingException(code=403,
                                      description='Permission denied')

        pre = dict(PATCH_SINGLE=[check_permissions])
        # recreate the api at /api/v1/person
        self.manager.create_api(self.Person,
                                methods=['PATCH', 'POST'],
                                preprocessors=pre)

        # Creating some test people
        self.app.post('/api/person',
                      data=dumps({'name': u'Lincoln', 'age': 23}))
        self.app.post('/api/person',
                      data=dumps({'name': u'Lucy', 'age': 23}))
        self.app.post('/api/person',
                      data=dumps({'name': u'Mary', 'age': 25}))

        # Try updating people with id=1
        response = self.app.patch('/api/person/1', data=dumps({'age': 27}))
        assert response.status_code == 403
        json_resp = loads(response.data)
        assert 'Permission denied' == json_resp['message']

    def test_patch_single_preprocessor2(self):
        """Tests for using a preprocessor with :http:method:`patch` requests.

        """

        def update_data(data=None, **kw):
            data['other'] = 27

        pre = dict(PATCH_SINGLE=[update_data])
        # recreate the api at /api/v1/person
        self.manager.create_api(self.Person,
                                methods=['GET', 'PATCH', 'POST'],
                                preprocessors=pre)

        # Creating some test people
        self.app.post('/api/person',
                      data=dumps({'name': u'Lincoln', 'age': 23}))
        self.app.post('/api/person',
                      data=dumps({'name': u'Lucy', 'age': 23}))
        self.app.post('/api/person',
                      data=dumps({'name': u'Mary', 'age': 25}))

        # Try updating people with id=1
        response = self.app.patch('/api/person/1', data=dumps({'age': 27}))
        assert response.status_code == 200

        resp = self.app.get('/api/person/1')
        assert resp.status_code == 200
        assert loads(resp.data)['age'] == 27
        assert loads(resp.data)['other'] == 27

    def test_delete_single(self):
        """Test for the DELETE_SINGLE preprocessor."""
        # Create a preprocessor function that only allows deleting a Person
        # instance with ID 2.
        def must_have_id_2(instance_id=None, **kw):
            if int(instance_id) != 2:
                raise ProcessingException(description='hey', code=400)

        pre = dict(DELETE_SINGLE=[must_have_id_2])
        self.manager.create_api(self.Person, methods=['GET', 'DELETE'],
                                preprocessors=pre)

        # Add three people to the database.
        self.session.add(self.Person(id=1))
        self.session.add(self.Person(id=2))
        self.session.add(self.Person(id=3))
        self.session.commit()

        # Trying to delete Person instances with ID 1 and 3 should cause a
        # processing exception, resulting in a HTTP 400 response.
        response = self.app.delete('/api/person/1')
        assert response.status_code == 400
        response = self.app.delete('/api/person/3')
        assert response.status_code == 400

        # Trying to delete person 2 should work
        response = self.app.delete('/api/person/2')
        print(response.data)
        assert response.status_code == 204
        response = self.app.get('/api/person')
        assert response.status_code == 200
        data = loads(response.data)['objects']
        assert 2 not in [person['id'] for person in data]

    def test_delete_many_preprocessor(self):
        # Create a preprocessor function that adds a filter.
        def add_filter(search_params=None, **kw):
            filt = dict(name='age', op='eq', val=23)
            if search_params is None:
                search_params = {}
            if 'filters' not in search_params:
                search_params['filters'] = []
            search_params['filters'].append(filt)

        pre = dict(DELETE_MANY=[add_filter])
        # recreate the api at /api/v1/person
        self.manager.create_api(self.Person, methods=['GET', 'POST', 'DELETE'],
                                allow_delete_many=True, preprocessors=pre)

        self.session.add(self.Person(name=u'foo', age=23))
        self.session.add(self.Person(name=u'bar', age=23))
        self.session.add(self.Person(name=u'baz', age=25))
        self.session.commit()

        # Deleting only those that have age 23 by using the filter added by the
        # preprocessor.
        response = self.app.delete('/api/person')
        assert response.status_code == 200
        assert loads(response.data)['num_deleted'] == 2

        # Finally, testing if the change was made
        response = self.app.get('/api/person')
        data = loads(response.data)['objects']
        assert len(data) == 1
        assert data[0]['name'] == u'baz'

    def test_patch_many_preprocessor(self):
        """Tests for using a preprocessor with :http:method:`patch` requests
        which request changes to many objects.

        """

        def update_data(data=None, **kw):
            data['other'] = 27

        pre = dict(PATCH_MANY=[update_data])
        # recreate the api at /api/v1/person
        self.manager.create_api(self.Person, methods=['GET', 'POST', 'PATCH'],
                                allow_patch_many=True,
                                preprocessors=pre)

        # Creating some people
        self.app.post('/api/person',
                      data=dumps({'name': u'Lincoln', 'age': 23}))
        self.app.post('/api/person',
                      data=dumps({'name': u'Lucy', 'age': 23}))
        self.app.post('/api/person',
                      data=dumps({'name': u'Mary', 'age': 25}))

        # Changing the birth date field of the entire collection
        day, month, year = 15, 9, 1986
        birth_date = date(year, month, day).strftime('%d/%m/%Y')  # iso8601
        form = {'birth_date': birth_date}
        response = self.app.patch('/api/person', data=dumps(form))

        # Finally, testing if the change was made
        response = self.app.get('/api/person')
        loaded = loads(response.data)['objects']
        for i in loaded:
            expected = '{0:4d}-{1:02d}-{2:02d}'.format(year, month, day)
            assert i['birth_date'] == expected
            assert i['other'] == 27

    def test_processor_no_change(self):
        """Tests :http:method:`post` requests with a preprocessor function.
        that makes no change to the data"""
        def no_change(**kw):
            pass

        self.manager.create_api(self.Person, methods=['GET', 'POST'],
                                url_prefix='/api/v2',
                                preprocessors=dict(POST=[no_change],
                                                   GET_SINGLE=[no_change],
                                                   GET_MANY=[no_change]))

        response = self.app.post('/api/v2/person',
                                 data=dumps({'name': u'Lincoln', 'age': 23}))
        assert response.status_code == 201

        personid = loads(response.data)['id']
        person = self.session.query(self.Person).filter_by(id=personid).first()
        assert person.name == u'Lincoln'
        assert person.age == 23

        # Test for GET_SINGLE
        response = self.app.get('/api/v2/person/{0:d}'.format(personid))
        assert response.status_code == 200

        person_response = loads(response.data)
        assert person_response['name'] == person.name
        assert person_response['age'] == person.age

        # Test for GET_MANY
        response = self.app.get('/api/v2/person')
        assert response.status_code == 200

        person_response = loads(response.data)["objects"][0]
        assert person_response['name'] == person.name
        assert person_response['age'] == person.age

    def test_add_filters(self):
        """Test for adding a filter to a :http:method:`get` request for a
        collection where there was no query parameter before.

        """
        # Create some people in the database.
        person1 = self.Person(name=u'foo')
        person2 = self.Person(name=u'bar')
        person3 = self.Person(name=u'baz')
        self.session.add_all((person1, person2, person3))
        self.session.commit()

        # Create a preprocessor function that adds a filter.
        def add_filter(search_params=None, **kw):
            if search_params is None:
                return
            filt = dict(name='name', op='like', val=u'ba%')
            if 'filters' not in search_params:
                search_params['filters'] = []
            search_params['filters'].append(filt)

        # Create the API with the preprocessor.
        self.manager.create_api(self.Person,
                                preprocessors=dict(GET_MANY=[add_filter]))

        # Test that the filter is added on GET requests to the collection.
        response = self.app.get('/api/person')
        assert 200 == response.status_code
        data = loads(response.data)['objects']
        assert 2 == len(data)
        assert sorted(['bar', 'baz']) == sorted([person['name']
                                                 for person in data])
