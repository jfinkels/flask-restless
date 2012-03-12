# -*- coding: utf-8; Mode: Python -*-
#
# Copyright 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
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
"""Unit tests for the :mod:`flask_restless.manager` module."""
from unittest2 import TestSuite

from flask import json

from .helpers import TestSupportWithManager
from .models import Person


__all__ = ['APIManagerTest']


dumps = json.dumps
loads = json.loads


class APIManagerTest(TestSupportWithManager):
    """Unit tests for the :class:`flask_restless.manager.APIManager` class.

    """

    def test_create_api(self):
        """Tests that the :meth:`flask_restless.manager.APIManager.create_api`
        method creates endpoints which are accessible by the client, only allow
        specified HTTP methods, and which provide a correct API to a database.

        """
        # create three different APIs for the same model
        # TODO note in documentation that only
        self.manager.create_api(Person, methods=['GET', 'POST'])
        self.manager.create_api(Person, methods=['PATCH'], url_prefix='/api2')
        self.manager.create_api(Person, methods=['GET'],
                                url_prefix='/readonly')

        # test that specified endpoints exist
        response = self.app.post('/api/person', data=dumps(dict(name='foo')))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(loads(response.data)['id'], 1)
        response = self.app.get('/api/person')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(loads(response.data)['objects']), 1)
        self.assertEqual(loads(response.data)['objects'][0]['id'], 1)

        # test that non-specified methods are not allowed
        response = self.app.delete('/api/person/1')
        self.assertEqual(response.status_code, 405)
        response = self.app.patch('/api/person/1',
                                  data=dumps(dict(name='bar')))
        self.assertEqual(response.status_code, 405)

        # test that specified endpoints exist
        response = self.app.patch('/api2/person/1',
                                  data=dumps(dict(name='bar')))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['id'], 1)
        self.assertEqual(loads(response.data)['name'], 'bar')

        # test that non-specified methods are not allowed
        response = self.app.get('/api2/person/1')
        self.assertEqual(response.status_code, 405)
        response = self.app.delete('/api2/person/1')
        self.assertEqual(response.status_code, 405)
        response = self.app.post('/api2/person',
                                 data=dumps(dict(name='baz')))
        self.assertEqual(response.status_code, 405)

        # test that the model is the same as before
        response = self.app.get('/readonly/person')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(loads(response.data)['objects']), 1)
        self.assertEqual(loads(response.data)['objects'][0]['id'], 1)
        self.assertEqual(loads(response.data)['objects'][0]['name'], 'bar')

    def test_different_collection_name(self):
        """Tests that providing a different collection name exposes the API at
        the corresponding URL.

        """
        self.manager.create_api(Person, methods=['POST', 'GET'],
                                collection_name='people')

        response = self.app.post('/api/people', data=dumps(dict(name='foo')))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(loads(response.data)['id'], 1)

        response = self.app.get('/api/people')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(loads(response.data)['objects']), 1)
        self.assertEqual(loads(response.data)['objects'][0]['id'], 1)

        response = self.app.get('/api/people/1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['id'], 1)

    def test_allow_functions(self):
        """Tests that the ``allow_functions`` keyword argument makes a
        :http:get:`/api/eval/...` endpoint available.

        """
        self.manager.create_api(Person, allow_functions=True)
        response = self.app.get('/api/eval/person')
        self.assertNotEqual(response.status_code, 400)
        self.assertEqual(response.status_code, 200)

    def test_disallow_functions(self):
        """Tests that if the ``allow_functions`` keyword argument if ``False``,
        no endpoint will be made available at :http:get:`/api/eval/...`.

        """
        self.manager.create_api(Person, allow_functions=False)
        response = self.app.get('/api/eval/person')
        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(response.status_code, 404)


def load_tests(loader, standard_tests, pattern):
    """Returns the test suite for this module."""
    suite = TestSuite()
    suite.addTest(loader.loadTestsFromTestCase(APIManagerTest))
    return suite
