"""
    tests.test_processors
    ~~~~~~~~~~~~~~~~~~~~~

    Provides unit tests for pre- and post-processors hooks.

    :copyright: 2013 Mike Klimin <klinkin@gmail.com>
    :copyright: 2013 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
from __future__ import with_statement

from datetime import date

from flask import json
from flask.ext.restless.views import ProcessingException
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

    def test_delete_preprocessor(self):
        """Tests for using a preprocessor with :http:method:`delete` requests.

        """
        def check_permissions(**kw):
            raise ProcessingException(code=403,
                                      description='Permission denied')

        pre = dict(DELETE=[check_permissions])
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
