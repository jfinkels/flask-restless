# -*- coding: utf-8; Mode: Python -*-
#
# Copyright 2012 Jeffrey Finkelstein <jefrey.finkelstein@gmail.com>
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
"""Unit tests for SQLAlchemy models which have some validation functionality
and therefore raise validation errors when requests are made to write to the
database.

Validation is not provided by Flask-Restless itself, but it must capture
validation errors and return them to the client.

"""
from unittest2 import TestSuite
from unittest2 import skipUnless

from flask import json

# for the sqlalchemy_elixir_validations package on pypi.python.org
try:
    from elixir_validations import ValidationException
    from .validation_models.sqlalchemy_elixir_validations import Test
    has_elixir_validations = True
except:
    has_elixir_validations = False

from .helpers import TestSupportWithManager

__all__ = ['ValidationTestCase']


dumps = json.dumps
loads = json.loads


class ValidationTestCase(TestSupportWithManager):
    """Base class for tests which expect validation errors.

    Each subclass which inherits from this base class should override
    :meth:`_create_apis` to create API endpoints for models which have some
    validation on their fields.

    """

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`testapp.Person` and
        :class:`testapp.Computer` models.

        Each subclass which inherits from this base class should override
        :meth:`create_apis` to create API endpoints for models which have some
        validation on their fields.

        """
        super(ValidationTestCase, self).setUp()
        self.create_apis()

    def create_apis(self):
        """Subclasses must override this method and use it to register APIs for
        their models.

        The implementation here does nothing.

        """
        pass


class SAETest(ValidationTestCase):
    """Tests for validation errors raised by the
    ``sqlalchemy_elixir_validations`` package. For more information about this
    package, see `its PyPI page
    <http://pypi.python.org/pypi/sqlalchemy_elixir_validations>`_.

    """

    def create_apis(self):
        """Create APIs for the validated models."""
        self.manager.create_api(Test, methods=['GET', 'POST', 'PATCH'],
                                validation_exceptions=[ValidationException])

    def test_presence_validations(self):
        """Tests that errors from validators which check for presence are
        correctly captured and returned to the client.

        """
        # missing required name field
        person = dict(email='example@example.com')
        response = self.app.post('/api/test', data=dumps(person))
        self.assertEqual(response.status_code, 400)
        data = loads(response.data)
        self.assertIn('validation_errors', data)
        errors = data['validation_errors']
        self.assertIn('name', errors)
        self.assertIn('presence', errors['name'].lower())

        # missing required email field
        person = dict(name='Jeffrey')
        response = self.app.post('/api/test', data=dumps(person))
        self.assertEqual(response.status_code, 400)
        data = loads(response.data)
        self.assertIn('validation_errors', data)
        errors = data['validation_errors']
        self.assertIn('email', errors)
        self.assertIn('presence', errors['email'].lower())

        # everything required is now provided
        person = dict(name='Jeffrey', email='example@example.com', age=24)
        response = self.app.post('/api/test', data=dumps(person))
        self.assertEqual(response.status_code, 201)
        personid = loads(response.data)['id']

        # check that the provided field values are in there
        response = self.app.get('/api/test/' + str(personid))
        self.assertEqual(response.status_code, 200)
        data = loads(response.data)
        self.assertEqual(data['name'], 'Jeffrey')
        self.assertEqual(data['email'], 'example@example.com')

    def test_uniqueness_validations(self):
        """Tests that errors from validators which check for uniqueness are
        correctly captured and returned to the client.

        """
        # create a person
        person = dict(name='Jeffrey', email='example@example.com', age=24)
        response = self.app.post('/api/test', data=dumps(person))
        self.assertEqual(response.status_code, 201)

        # test posting a person with the same name field
        person = dict(name='Jeffrey', email='foo@example.com', age=1)
        response = self.app.post('/api/test', data=dumps(person))
        self.assertEqual(response.status_code, 400)
        data = loads(response.data)
        self.assertIn('validation_errors', data)
        errors = data['validation_errors']
        self.assertIn('name', errors)
        self.assertIn('unique', errors['name'].lower())

        # post a new person with different fields should be fine
        person = dict(name='John', email='foo@example.com', age=1)
        response = self.app.post('/api/test', data=dumps(person))
        self.assertEqual(response.status_code, 201)
        personid = loads(response.data)['id']

        # test patching a person to with non unique field data
        person = dict(name='Jeffrey')
        response = self.app.patch('/api/test/' + str(personid),
                                  data=dumps(person))
        self.assertIn('validation_errors', data)
        errors = data['validation_errors']
        self.assertIn('name', errors)
        self.assertIn('unique', errors['name'].lower())

        # patching a person with unique fields should be fine
        person = dict(name='John', email='foo@example.com', age=1)
        response = self.app.patch('/api/test/' + str(personid),
                                  data=dumps(person))
        self.assertIn('validation_errors', data)
        data = loads(response.data)
        if 'validation_errors' in data and 'name' in data['validation_errors']:
            self.assertNotIn('unique', errors['name'].lower())

    def test_format_validations(self):
        """Tests that errors from validators which check if fields match a
        format specified by a regular expression are correctly captured and
        returned to the client.

        """
        # test posting a person with a badly formatted email field
        person = dict(name='Jeffrey', email='bogus!!!email', age=1)
        response = self.app.post('/api/test', data=dumps(person))
        self.assertEqual(response.status_code, 400)
        data = loads(response.data)
        self.assertIn('validation_errors', data)
        errors = data['validation_errors']
        self.assertIn('email', errors)
        self.assertIn('format', errors['email'].lower())

        # posting a new person with valid email format should be fine
        person = dict(name='John', email='foo@example.com', age=1)
        response = self.app.post('/api/test', data=dumps(person))
        self.assertEqual(response.status_code, 201)
        personid = loads(response.data)['id']

        # test patching a person to with badly formatted data
        person = dict(name='Jeffrey', email='bogus!!!email', age=24)
        response = self.app.patch('/api/test/' + str(personid),
                                  data=dumps(person))
        self.assertIn('validation_errors', data)
        errors = data['validation_errors']
        self.assertIn('email', errors)
        self.assertIn('format', errors['email'].lower())

        # patching a person with correctly formatted fields should be fine
        person = dict(email='foo@example.com')
        response = self.app.patch('/api/test/' + str(personid),
                                  data=dumps(person))
        data = loads(response.data)
        if 'validation_errors' in data and \
                'email' in data['validation_errors']:
            self.assertNotIn('format', errors['email'].lower())

    def test_numericality_validations(self):
        """Tests that errors from validators which check numericality of fields
        are correctly captured and returned to the client.

        """
        # test posting a person with a non-numeric age
        person = dict(name='Jeffrey', email='example@example.com', age='bogus')
        response = self.app.post('/api/test', data=dumps(person))
        self.assertEqual(response.status_code, 400)
        data = loads(response.data)
        self.assertIn('validation_errors', data)
        errors = data['validation_errors']
        self.assertIn('age', errors)
        self.assertIn('numeric', errors['age'].lower())

        # posting a new person with numeric age should be fine
        person = dict(name='Jeffrey', email='example@example.com', age=1)
        response = self.app.post('/api/test', data=dumps(person))
        self.assertEqual(response.status_code, 201)
        personid = loads(response.data)['id']

        # test patching a person to with a non-numeric age
        response = self.app.patch('/api/test/' + str(personid),
                                  data=dumps(dict(age='bogus')))
        self.assertIn('validation_errors', data)
        errors = data['validation_errors']
        self.assertIn('age', errors)
        self.assertIn('numeric', errors['age'].lower())

        # patching a person with numeric age
        person = dict(age=100)
        response = self.app.patch('/api/test/' + str(personid),
                                  data=dumps(person))
        data = loads(response.data)
        if 'validation_errors' in data and 'age' in data['validation_errors']:
            self.assertNotIn('numberic', errors['age'].lower())

    def test_range_validations(self):
        """Tests that errors from validators which check that value of fields
        are between a given range are correctly captured and returned to the
        client.

        """
        # test posting a person with a crazy age
        person = dict(name='Jeffrey', email='example@example.com', age=-100)
        response = self.app.post('/api/test', data=dumps(person))
        self.assertEqual(response.status_code, 400)
        data = loads(response.data)
        self.assertIn('validation_errors', data)
        errors = data['validation_errors']
        self.assertIn('age', errors)
        self.assertIn('range', errors['age'].lower())

        person = dict(name='Jeffrey', email='example@example.com', age=999)
        response = self.app.post('/api/test', data=dumps(person))
        self.assertEqual(response.status_code, 400)
        data = loads(response.data)
        self.assertIn('validation_errors', data)
        errors = data['validation_errors']
        self.assertIn('age', errors)
        self.assertIn('range', errors['age'].lower())

        # posting a new person with non-crazy age should be fine
        person = dict(name='Jeffrey', email='example@example.com', age=50)
        response = self.app.post('/api/test', data=dumps(person))
        self.assertEqual(response.status_code, 201)
        personid = loads(response.data)['id']

        # test patching a person to with a crazy age
        response = self.app.patch('/api/test/' + str(personid),
                                  data=dumps(dict(age=-1000)))
        self.assertIn('validation_errors', data)
        errors = data['validation_errors']
        self.assertIn('age', errors)
        self.assertIn('range', errors['age'].lower())

        response = self.app.patch('/api/test/' + str(personid),
                                  data=dumps(dict(age=9999)))
        self.assertIn('validation_errors', data)
        errors = data['validation_errors']
        self.assertIn('age', errors)
        self.assertIn('range', errors['age'].lower())

        # patching a person with a normal age should be fine
        person = dict(age=100)
        response = self.app.patch('/api/test/' + str(personid),
                                  data=dumps(person))
        data = loads(response.data)
        if 'validation_errors' in data and 'age' in data['validation_errors']:
            self.assertNotIn('range', errors['age'].lower())

# skipUnless should be used as a decorator, but Python 2.5 doesn't have
# decorators.
SAETest = skipUnless(has_elixir_validations,
                     'elixir_validations not found.')(SAETest)


def load_tests(loader, standard_tests, pattern):
    """Returns the test suite for this module."""
    suite = TestSuite()
    suite.addTest(loader.loadTestsFromTestCase(SAETest))
    return suite
