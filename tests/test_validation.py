"""
    tests.test_validation
    ~~~~~~~~~~~~~~~~~~~~~

    Provides unit tests for SQLAlchemy models which have some validation
    functionality and therefore raise validation errors when requests are made
    to write to the database.

    Validation is not provided by Flask-Restless itself, but it must capture
    validation errors and return them to the client.

    :copyright: 2012, 2013, 2014, 2015 Jeffrey Finkelstein
                <jeffrey.finkelstein@gmail.com> and contributors.
    :license: GNU AGPLv3+ or BSD

"""
import re
import sys

from flask import json
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import Unicode
from sqlalchemy.orm import validates

# for SAValidation package on pypi.python.org
try:
    import savalidation as _sav
    import savalidation.validators as sav
except:
    has_savalidation = False
else:
    sav_version = tuple(int(n) for n in _sav.VERSION.split('.'))
    has_savalidation = True

from .helpers import skip_unless
from .helpers import TestSupport


#: A regular expression for email addresses.
EMAIL_REGEX = re.compile("[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^"
                         "_`{|}~-]+)*@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a"
                         "-z0-9](?:[a-z0-9-]*[a-z0-9])")

dumps = json.dumps
loads = json.loads


class TestSimpleValidation(TestSupport):
    """Tests for validation errors raised by the SQLAlchemy's simple built-in
    validation.

    For more information about this functionality, see the documentation for
    :func:`sqlalchemy.orm.validates`.

    """

    def setUp(self):
        """Create APIs for the validated models."""
        super(TestSimpleValidation, self).setUp()

        class CoolValidationError(Exception):
            pass

        # create the validated class
        # NOTE: don't name this `Person`, as in self.Person
        class Test(self.Base):
            __tablename__ = 'test'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode(30), nullable=False, index=True)
            email = Column(Unicode, nullable=False)
            age = Column(Integer, nullable=False)

            @validates('email')
            def validate_email(self, key, string):
                if len(EMAIL_REGEX.findall(string)) != 1:
                    exception = CoolValidationError()
                    exception.errors = dict(email=('Must be in valid email'
                                                   ' format'))
                    raise exception
                return string

            @validates('age')
            def validate_age(self, key, number):
                if not 0 <= number <= 150:
                    exception = CoolValidationError()
                    exception.errors = dict(age='Must be between 0 and 150')
                    raise exception
                return number

            @validates('name')
            def validate_name(self, key, string):
                if string is None:
                    exception = CoolValidationError()
                    exception.errors = dict(name='Must not be empty')
                    raise exception
                return string
        self.Base.metadata.create_all()
        self.manager.create_api(Test, methods=['GET', 'POST', 'PATCH'],
                                validation_exceptions=[CoolValidationError])

    def test_validations(self):
        """Test SQLAlchemy's built-in simple validations."""
        # test posting a person with a badly formatted email field
        person = dict(name='Jeffrey', email='bogus!!!email', age=1)
        response = self.app.post('/api/test', data=dumps(person))
        assert response.status_code == 400
        data = loads(response.data)
        assert 'validation_errors' in data
        errors = data['validation_errors']
        assert 'email' in errors
        assert 'format' in errors['email'].lower()

        # posting a new person with valid email format should be fine
        person = dict(name='John', email='foo@example.com', age=1)
        response = self.app.post('/api/test', data=dumps(person))
        assert response.status_code == 201
        personid = loads(response.data)['id']

        # test patching a person to with badly formatted data
        person = dict(name='Jeffrey', email='bogus!!!email', age=24)
        response = self.app.patch('/api/test/' + str(personid),
                                  data=dumps(person))
        data = loads(response.data)
        assert 'validation_errors' in data
        errors = data['validation_errors']
        assert 'email' in errors
        assert 'format' in errors['email'].lower()

        # patching a person with correctly formatted fields should be fine
        person = dict(email='foo@example.com')
        response = self.app.patch('/api/test/' + str(personid),
                                  data=dumps(person))
        data = loads(response.data)
        if 'validation_errors' in data and \
                'email' in data['validation_errors']:
            assert 'format' not in errors['email'].lower()


@skip_unless(has_savalidation and sav_version >= (0, 2) and
             sys.version < (3, 0, 0), 'savalidation not found.')
class TestSAV(TestSupport):
    """Tests for validation errors raised by the ``savalidation`` package. For
    more information about this package, see `its PyPI page
    <http://pypi.python.org/pypi/SAValidation>`_.

    """

    def setUp(self):
        """Create APIs for the validated models."""
        super(TestSAV, self).setUp()

        class Test(self.Base, _sav.ValidationMixin):
            __tablename__ = 'test'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode(30))
            email = Column(Unicode)
            age = Column(Integer)

            sav.validates_presence_of('name', 'email')
            sav.validates_email('email')

        self.Base.metadata.create_all()

        exceptions = [_sav.ValidationError]
        self.manager.create_api(Test, methods=['GET', 'POST', 'PATCH'],
                                validation_exceptions=exceptions)

    def test_format_validations(self):
        """Tests that errors from validators which check if fields match a
        format specified by a regular expression are correctly captured and
        returned to the client.

        """
        # test posting a person with a badly formatted email field
        person = dict(name='Jeffrey', email='bogus!!!email', age=1)
        response = self.app.post('/api/test', data=dumps(person))
        assert response.status_code == 400
        data = loads(response.data)
        assert 'validation_errors' in data
        errors = data['validation_errors']
        assert 'email' in errors
        assert 'email address' in errors['email'].lower()

        # posting a new person with valid email format should be fine
        person = dict(name='John', email='foo@example.com', age=1)
        response = self.app.post('/api/test', data=dumps(person))
        assert response.status_code == 201
        personid = loads(response.data)['id']

        # test patching a person to with badly formatted data
        person = dict(name='Jeffrey', email='bogus!!!email', age=24)
        response = self.app.patch('/api/test/' + str(personid),
                                  data=dumps(person))
        assert 'validation_errors' in data
        errors = data['validation_errors']
        assert 'email' in errors
        assert 'email address' in errors['email'].lower()

        # patching a person with correctly formatted fields should be fine
        person = dict(email='foo@example.com')
        response = self.app.patch('/api/test/' + str(personid),
                                  data=dumps(person))
        data = loads(response.data)
        if 'validation_errors' in data and \
                'email' in data['validation_errors']:
            assert 'email address' not in errors['email'].lower()

    def test_presence_validations(self):
        """Tests that errors from validators which check for presence are
        correctly captured and returned to the client.

        """
        # missing required name field
        person = dict(email='example@example.com')
        response = self.app.post('/api/test', data=dumps(person))
        assert response.status_code == 400
        data = loads(response.data)
        assert 'validation_errors' in data
        errors = data['validation_errors']
        assert 'name' in errors
        assert 'enter a value' in errors['name'].lower()

        # missing required email field
        person = dict(name='Jeffrey')
        response = self.app.post('/api/test', data=dumps(person))
        assert response.status_code == 400
        data = loads(response.data)
        assert 'validation_errors' in data
        errors = data['validation_errors']
        assert 'email' in errors
        assert 'enter a value' in errors['email'].lower()

        # everything required is now provided
        person = dict(name='Jeffrey', email='example@example.com', age=24)
        response = self.app.post('/api/test', data=dumps(person))
        assert response.status_code == 201
        personid = loads(response.data)['id']

        # check that the provided field values are in there
        response = self.app.get('/api/test/' + str(personid))
        assert response.status_code == 200
        data = loads(response.data)
        assert data['name'] == 'Jeffrey'
        assert data['email'] == 'example@example.com'
