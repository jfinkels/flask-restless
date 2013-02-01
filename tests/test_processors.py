"""
    tests.test_processors
    ~~~~~~~~~~~~~~~~

    Provides unit tests for pre- and post-processors hooks.

    :copyright: 2011 by Lincoln de Sousa <lincoln@comum.org>
    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
from __future__ import with_statement

from datetime import date

from flask import json
from flask.ext.restless.views import StopPreprocessor, StopPostprocessor
from .helpers import TestSupport

__all__ = ['ProcessorsTestCase']

dumps = json.dumps
loads = json.loads


class ProcessorsTestCase(TestSupport):
    """Unit tests for the :class:`flask_restless.views.API` class."""

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application.

        """
        # create the database
        super(ProcessorsTestCase, self).setUp()

        # to facilitate searching
        self.app.search = lambda url, q: self.app.get(url + '?q=%s' % q)

    def test_get_single_preprocessor(self):
        """Tests GET method for single object with preprocessors function."""

        def check_permissions(instid):

            current_user_have_permission_to_read_obj = False
            person = self.session.query(self.Person).filter_by(id=instid).first()

            # check permission current user for obj inst
            if person and not current_user_have_permission_to_read_obj:
                raise StopPreprocessor(status_code=403, message='Permission denied')

        pre = dict(GET_SINGLE=[check_permissions])
        # create the api
        self.manager.create_api(self.Person, methods=['GET', 'POST'],
                                url_prefix='/api/v1',
                                preprocessors=pre)

        # Creating people
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Lincoln', 'age': 23}))

        response = self.app.get('/api/v1/person/1')
        self.assertEqual(response.status_code, 403)

    def test_get_list_preprocessor(self):

        def check_permissions(params):
            current_user_have_permission_to_read_only_objs = [1, 3]
            if 'filters' not in params:
                params['filters'] = [{u'name': u'id', u'op': u'in', u'val': current_user_have_permission_to_read_only_objs}]
            else:
                params['filters'].append({u'name': u'id', u'op': u'in', u'val': current_user_have_permission_to_read_only_objs})
            return params

        pre = dict(GET_LIST=[check_permissions])
        # create the api at /api/v1/person
        self.manager.create_api(self.Person, methods=['GET', 'POST'],
                                url_prefix='/api/v1',
                                preprocessors=pre)

        # Creating some people
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Lincoln', 'age': 23}))
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Lucy', 'age': 23}))
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Mary', 'age': 25}))

        response = self.app.get('/api/v1/person')
        objs = loads(response.data)['objects']
        ids = [obj['id'] for obj in objs]
        self.assertEqual(ids, [1, 3])
        self.assertEqual(response.status_code, 200)

        search = {
            'filters': [
                {'name': 'name', 'val': u'Lincoln', 'op': 'equals'}
            ],
        }
        response = self.app.search('/api/v1/person', dumps(search))
        num_results = loads(response.data)['num_results']

        self.assertEqual(num_results, 1)
        self.assertEqual(response.status_code, 200)

    def test_post_preprocessor(self):
        """Tests POST method decoration using a custom function."""
        def decorator_function(params):
            if params:
                # just add a new attribute
                params['other'] = 7
            return params

        pre = dict(POST=[decorator_function])
        # test for function that decorates parameters with 'other' attribute
        self.manager.create_api(self.Person, methods=['POST'],
                                url_prefix='/api/v2',
                                preprocessors=pre)

        response = self.app.post('/api/v2/person',
                                 data=dumps({'name': u'Lincoln', 'age': 23}))
        self.assertEqual(response.status_code, 201)

        personid = loads(response.data)['id']
        person = self.session.query(self.Person).filter_by(id=personid).first()
        self.assertEquals(person.other, 7)

    def test_post_preprocessor_permission(self):
        """Tests POST method decoration using a custom function."""

        def check_permissions(params):
            current_user_have_permission_to_create_obj = False
            # check permission current user for obj inst
            if current_user_have_permission_to_create_obj:
                return params
            else:
                raise StopPreprocessor(status_code=403, message='Permission denied')

        pre = dict(POST=[check_permissions])
        self.manager.create_api(self.Person, methods=['POST'],
                                url_prefix='/api/v2',
                                preprocessors=pre)

        response = self.app.post('/api/v2/person',
                                 data=dumps({'name': u'Lincoln', 'age': 23}))
        self.assertEqual(response.status_code, 403)

    def test_delete_preprocessor(self):

        def check_permissions(instid):
            current_user_have_permission_to_delete_obj = False
            person = self.session.query(self.Person).filter_by(id=instid).first()

            # check permission current user for obj inst
            if person and not current_user_have_permission_to_delete_obj:
                raise StopPreprocessor(status_code=403, message='Permission denied')

        pre = dict(DELETE=[check_permissions])
        # recreate the api at /api/v1/person
        self.manager.create_api(self.Person,
                                url_prefix='/api/v1',
                                methods=['GET', 'PATCH', 'POST', 'DELETE'],
                                preprocessors=pre)

        # Creating some people
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Lincoln', 'age': 23}))
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Lucy', 'age': 23}))
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Mary', 'age': 25}))

        # Try deleting it
        response = self.app.delete('/api/v1/person/1')
        self.assertEqual(response.status_code, 403)

        # Making sure it has been not deleted
        people = self.session.query(self.Person).filter_by(id=1)
        self.assertEquals(people.count(), 1)


    def test_patch_single_preprocessor(self):

        def check_permissions(instid, data):
            current_user_have_permission_to_update_obj = False
            person = self.session.query(self.Person).filter_by(id=instid).first()

            # check permission current user for obj inst
            if person and not current_user_have_permission_to_update_obj:
                raise StopPreprocessor(status_code=403, message='Permission denied')

        pre = dict(PATCH_SINGLE=[check_permissions])
        # recreate the api at /api/v1/person
        self.manager.create_api(self.Person,
                                url_prefix='/api/v1',
                                methods=['GET', 'PATCH', 'POST', 'DELETE'],
                                preprocessors=pre)

        # Creating some test people
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Lincoln', 'age': 23}))
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Lucy', 'age': 23}))
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Mary', 'age': 25}))

        # Try updating people with id=1
        response = self.app.patch('/api/v1/person/1', data=dumps({'age': 27}))
        self.assertEqual(response.status_code, 403)


    def test_patch_single_preprocessor2(self):

        def check_permissions_and_update_data(instid, data):
            current_user_have_permission_to_update_obj = True
            person = self.session.query(self.Person).filter_by(id=instid).first()

            # check permission current user for obj inst
            if person and not current_user_have_permission_to_update_obj:
                raise StopPreprocessor(status_code=403, message='Permission denied')

            data['other'] = 27
            return data

        pre = dict(PATCH_SINGLE=[check_permissions_and_update_data])
        # recreate the api at /api/v1/person
        self.manager.create_api(self.Person,
                                url_prefix='/api/v1',
                                methods=['GET', 'PATCH', 'POST', 'DELETE'],
                                preprocessors=pre)

        # Creating some test people
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Lincoln', 'age': 23}))
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Lucy', 'age': 23}))
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Mary', 'age': 25}))

        # Try updating people with id=1
        response = self.app.patch('/api/v1/person/1', data=dumps({'age': 27}))
        self.assertEqual(response.status_code, 200)

        resp = self.app.get('/api/v1/person/1')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(loads(resp.data)['age'], 27)
        self.assertEqual(loads(resp.data)['other'], 27)


    def test_patch_many_preprocessor(self):

        def check_permissions_and_update_data(params):
            current_user_have_permission_to_update_all_obj = True

            # check permission current user for obj inst
            if current_user_have_permission_to_update_all_obj:
                params['other'] = 27
                return params
            else:
                raise StopPreprocessor(status_code=403, message='Permission denied')

        pre = dict(PATCH_MANY=[check_permissions_and_update_data])
        # recreate the api at /api/v1/person
        self.manager.create_api(self.Person, methods=['GET', 'POST', 'PATCH'],
                                url_prefix='/api/v1',
                                allow_patch_many=True,
                                preprocessors=pre)

        # Creating some people
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Lincoln', 'age': 23}))
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Lucy', 'age': 23}))
        self.app.post('/api/v1/person',
                      data=dumps({'name': u'Mary', 'age': 25}))


        # Changing the birth date field of the entire collection
        day, month, year = 15, 9, 1986
        birth_date = date(year, month, day).strftime('%d/%m/%Y')  # iso8601
        form = {'birth_date': birth_date}
        response = self.app.patch('/api/v1/person', data=dumps(form))


        # Finally, testing if the change was made
        response = self.app.get('/api/v1/person')
        loaded = loads(response.data)['objects']
        for i in loaded:
            self.assertEqual(i['birth_date'], ('%s-%s-%s' % (
                    year, str(month).zfill(2), str(day).zfill(2))))
            self.assertEqual(i['other'], 27)