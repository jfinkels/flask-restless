# test_validation.py - unit tests for model validation
#
# Copyright 2011 Lincoln de Sousa <lincoln@comum.org>.
# Copyright 2012, 2013, 2014, 2015, 2016 Jeffrey Finkelstein
#           <jeffrey.finkelstein@gmail.com> and contributors.
#
# This file is part of Flask-Restless.
#
# Flask-Restless is distributed under both the GNU Affero General Public
# License version 3 and under the 3-clause BSD license. For more
# information, see LICENSE.AGPL and LICENSE.BSD.
"""Unit tests for SQLAlchemy models that include some validation
functionality and therefore raise validation errors on requests to
update resources.

Validation is not provided by Flask-Restless itself, but we still need
to test that it captures validation errors and returns them to the
client.

"""
import sys

from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Unicode
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship
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

from .helpers import check_sole_error
from .helpers import dumps
from .helpers import loads
from .helpers import ManagerTestBase
from .helpers import skip_unless


class CoolValidationError(Exception):
    """Raised when there is a validation error.

    This is used for testing validation errors only.

    """
    pass


class TestSimpleValidation(ManagerTestBase):
    """Tests for validation errors raised by the SQLAlchemy's simple built-in
    validation.

    For more information about this functionality, see the documentation for
    :func:`sqlalchemy.orm.validates`.

    """

    def setup(self):
        """Create APIs for the validated models."""
        super(TestSimpleValidation, self).setup()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            age = Column(Integer, nullable=False)

            @validates('age')
            def validate_age(self, key, number):
                if not 0 <= number <= 150:
                    exception = CoolValidationError()
                    exception.errors = dict(age='Must be between 0 and 150')
                    raise exception
                return number

            @validates('articles')
            def validate_articles(self, key, article):
                if article.title is not None and len(article.title) == 0:
                    exception = CoolValidationError()
                    exception.errors = {'articles': 'empty title not allowed'}
                    raise exception
                return article

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            title = Column(Unicode)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person', backref=backref('articles'))

        class Comment(self.Base):
            __tablename__ = 'comment'
            id = Column(Integer, primary_key=True)
            article_id = Column(Integer, ForeignKey('article.id'),
                                nullable=False)
            article = relationship(Article)

        self.Article = Article
        self.Comment = Comment
        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Article)
        self.manager.create_api(Comment, methods=['PATCH'])
        self.manager.create_api(Person, methods=['POST', 'PATCH'],
                                validation_exceptions=[CoolValidationError])

    def test_create_valid(self):
        """Tests that an attempt to create a valid resource yields no error
        response.

        """
        data = dict(data=dict(type='person', age=1))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['age'] == 1

    def test_create_invalid(self):
        """Tests that an attempt to create an invalid resource yields an error
        response.

        """
        data = dict(data=dict(type='person', age=-1))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 400
        document = loads(response.data)
        errors = document['errors']
        error = errors[0]
        assert 'validation' in error['title'].lower()
        assert 'must be between' in error['detail'].lower()
        # Check that the person was not created.
        assert self.session.query(self.Person).count() == 0

    def test_update_valid(self):
        """Tests that an attempt to update a resource with valid data yields no
        error response.

        """
        person = self.Person(id=1, age=1)
        self.session.add(person)
        self.session.commit()
        data = {'data':
                    {'id': '1',
                     'type': 'person',
                     'attributes': {'age': 2}
                     }
                }
        response = self.app.patch('/api/person/1', data=dumps(data))
        assert response.status_code == 204
        assert person.age == 2

    def test_update_invalid(self):
        """Tests that an attempt to update a resource with an invalid
        attribute yields an error response.

        """
        person = self.Person(id=1, age=1)
        self.session.add(person)
        self.session.commit()
        data = {'data':
                    {'id': '1',
                     'type': 'person',
                     'attributes': {'age': -1}
                     }
                }
        response = self.app.patch('/api/person/1', data=dumps(data))
        check_sole_error(response, 400, ['age', 'Must be between'])
        # Check that the person was not updated.
        assert person.age == 1

    def test_update_relationship_invalid(self):
        """Tests that an attempt to update a resource with an invalid
        relationship yields an error response.

        """
        article = self.Article(id=1)
        comment = self.Comment(id=1)
        comment.article = article
        self.session.add_all([comment, article])
        self.session.commit()
        data = {
            'data': {
                'id': '1',
                'type': 'comment',
                'relationships': {
                    'article': {
                        'data': None
                    }
                }
            }
        }
        response = self.app.patch('/api/comment/1', data=dumps(data))
        assert response.status_code == 400
        document = loads(response.data)
        errors = document['errors']
        assert len(errors) == 1
        error = errors[0]
        assert error['title'] == 'Integrity Error'
        assert 'null' in error['detail'].lower()
        # Check that the relationship was not updated.
        assert comment.article == article

    def test_adding_to_relationship_invalid(self):
        """Tests that an attempt to add to a relationship with invalid
        data yields an error response.

        """
        person = self.Person(id=1, age=1)
        article = self.Article(id=1, title=u'')
        self.session.add_all([person, article])
        self.session.commit()
        data = {'data': [{'type': 'article', 'id': 1}]}
        response = self.app.post('/api/person/1/relationships/articles',
                                 data=dumps(data))
        assert response.status_code == 400
        document = loads(response.data)
        errors = document['errors']
        error = errors[0]
        assert 'validation' in error['title'].lower()
        assert 'empty title not allowed' in error['detail'].lower()
        # Check that the relationship was not updated.
        assert article.author is None

    def test_updating_relationship_invalid(self):
        """Tests that an attempt to update a relationship with invalid
        data yields an error response.

        """
        person = self.Person(id=1, age=1)
        article = self.Article(id=1, title=u'')
        self.session.add_all([person, article])
        self.session.commit()
        self.manager.create_api(self.Person, methods=['PATCH'],
                                allow_to_many_replacement=True,
                                url_prefix='/api2',
                                validation_exceptions=[CoolValidationError])
        data = {'data': [{'type': 'article', 'id': 1}]}
        response = self.app.patch('/api2/person/1/relationships/articles',
                                  data=dumps(data))
        assert response.status_code == 400
        document = loads(response.data)
        errors = document['errors']
        error = errors[0]
        assert 'validation' in error['title'].lower()
        assert 'empty title not allowed' in error['detail'].lower()
        # Check that the relationship was not updated.
        assert person.articles == []


@skip_unless(has_savalidation and sav_version >= (0, 2) and
             sys.version < (3, 0, 0), 'savalidation not found.')
class TestSAValidation(ManagerTestBase):
    """Tests for validation errors raised by the ``savalidation`` package. For
    more information about this package, see `its PyPI page
    <http://pypi.python.org/pypi/SAValidation>`_.

    """

    def setup(self):
        """Create APIs for the validated models."""
        super(TestSAValidation, self).setup()

        class Person(self.Base, _sav.ValidationMixin):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            email = Column(Unicode)

            sav.validates_presence_of('email')
            sav.validates_email('email')

        self.Person = Person
        self.Base.metadata.create_all()
        exceptions = [_sav.ValidationError]
        self.manager.create_api(Person, methods=['POST', 'PATCH'],
                                validation_exceptions=exceptions)

    def test_create_valid(self):
        """Tests that an attempt to create a valid resource yields no error
        response.

        """
        data = dict(data=dict(type='person', email=u'example@example.com'))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['email'] == u'example@example.com'

    def test_create_absent(self):
        """Tests that an attempt to create a resource with a missing required
        attribute yields an error response.

        """
        data = dict(data=dict(type='person'))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 400
        document = loads(response.data)
        errors = document['errors']
        error = errors[0]
        assert 'validation' in error['title'].lower()
        assert 'email' in error['detail'].lower()
        # Check that the person was not created.
        assert self.session.query(self.Person).count() == 0

    def test_create_invalid(self):
        """Tests that an attempt to create an invalid resource yields an error
        response.

        """
        data = {'data':
                    {'type': 'person',
                     'attributes': {'email': 'bogus'}
                     }
                }
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 400
        document = loads(response.data)
        errors = document['errors']
        error = errors[0]
        assert 'validation' in error['title'].lower()
        assert 'email' in error['detail'].lower()
        # Check that the person was not created.
        assert self.session.query(self.Person).count() == 0

    def test_update_valid(self):
        """Tests that an attempt to update a resource with valid data yields no
        error response.

        """
        person = self.Person(id=1, email=u'example@example.com')
        self.session.add(person)
        self.session.commit()
        data = {'data':
                    {'id': '1',
                     'type': 'person',
                     'attributes': {'email': u'foo@example.com'}
                     }
                }
        response = self.app.patch('/api/person/1', data=dumps(data))
        assert response.status_code == 204
        assert person.email == u'foo@example.com'

    def test_update_invalid(self):
        """Tests that an attempt to update a resource with invalid data yields
        an error response.

        """
        person = self.Person(id=1, email=u'example@example.com')
        self.session.add(person)
        self.session.commit()
        data = {'data':
                    {'id': '1',
                     'type': 'person',
                     'attributes': {'email': 'bogus'}
                     }
                }
        response = self.app.patch('/api/person/1', data=dumps(data))
        assert response.status_code == 400
        document = loads(response.data)
        errors = document['errors']
        error = errors[0]
        assert 'validation' in error['title'].lower()
        assert 'email' in error['detail'].lower()
        # Check that the person was not updated.
        assert person.email == u'example@example.com'
