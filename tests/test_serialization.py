# test_serialization.py - unit tests for serializing resources
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
"""Unit tests for serializing resources.

This module complements the tests in :mod:`test_fetching` module; tests
in this class should still be testing the behavior of Flask-Restless by
making requests to endpoints created by :meth:`APIManager.create_api`,
not by calling the serialization functions directly. This helps keep the
testing code decoupled from the serialization implementation.

"""
from datetime import datetime
from datetime import time
from datetime import timedelta
from unittest2 import skipUnless
from uuid import UUID
from uuid import uuid1
import warnings

try:
    # HACK The future package uses code that is pending deprecation in
    # Python 3.4 or later. We catch the warning here so that the test
    # suite does not complain about it.
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=PendingDeprecationWarning)
        from future.standard_library import install_aliases
    install_aliases()
except ImportError:
    is_future_available = False
else:
    is_future_available = True
from sqlalchemy import Column
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Interval
from sqlalchemy import Time
from sqlalchemy import TypeDecorator
from sqlalchemy import Unicode
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship

from flask_restless import DefaultSerializer
from flask_restless import MultipleExceptions
from flask_restless import SerializationException

from .helpers import check_sole_error
from .helpers import GUID
from .helpers import loads
from .helpers import ManagerTestBase
from .helpers import raise_s_exception as raise_exception


class DecoratedDateTime(TypeDecorator):

    impl = DateTime


class DecoratedInterval(TypeDecorator):

    impl = Interval


class TestFetchCollection(ManagerTestBase):
    """Tests for serializing when fetching from a collection endpoint."""

    def setUp(self):
        super(TestFetchCollection, self).setUp()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        self.Person = Person
        self.Base.metadata.create_all()

    def test_custom_serializer(self):
        """Tests for a custom serializer for serializing many resources.

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()

        class MySerializer(DefaultSerializer):

            def serialize_many(self, *args, **kw):
                result = super(MySerializer, self).serialize_many(*args, **kw)
                for resource in result['data']:
                    if 'attributes' not in resource:
                        resource['attributes'] = {}
                    resource['attributes']['foo'] = resource['id']
                return result

        self.manager.create_api(self.Person, serializer_class=MySerializer)

        response = self.app.get('/api/person')
        document = loads(response.data)
        people = document['data']
        attributes = sorted(person['attributes']['foo'] for person in people)
        assert ['1', '2'] == attributes

    def test_multiple_exceptions(self):
        """Tests that multiple exceptions are caught when serializing
        many instances.

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()

        class raise_exceptions(DefaultSerializer):

            def serialize_many(self, instances, *args, **kw):
                instance1, instance2 = instances[:2]
                exception1 = SerializationException(instance1, message='foo')
                exception2 = SerializationException(instance2, message='bar')
                exceptions = [exception1, exception2]
                raise MultipleExceptions(exceptions)

        self.manager.create_api(self.Person, serializer_class=raise_exceptions)

        response = self.app.get('/api/person')
        document = loads(response.data)
        assert response.status_code == 500
        errors = document['errors']
        assert len(errors) == 2
        error1, error2 = errors
        detail1 = error1['detail']
        assert 'foo' in detail1
        detail2 = error2['detail']
        assert 'bar' in detail2

    def test_multiple_exceptions_from_dump(self):
        """Tests that multiple exceptions are caught from the
        :meth:`DefaultSerializer._dump` method when serializing many
        instances.

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()

        class raise_exceptions(DefaultSerializer):

            def _dump(self, instance, *args, **kw):
                message = 'failed on {0}'.format(instance.id)
                raise SerializationException(instance, message=message)

        self.manager.create_api(self.Person, serializer_class=raise_exceptions)

        response = self.app.get('/api/person')
        document = loads(response.data)
        assert response.status_code == 500
        errors = document['errors']
        assert len(errors) == 2
        error1, error2 = errors
        detail1 = error1['detail']
        detail2 = error2['detail']
        # There is no guarantee on the order in which the error objects
        # are supplied in the response, so we check which is which.
        if '1' not in detail1:
            detail1, detail2 = detail2, detail1
        assert u'failed on 1' in detail1
        assert u'failed on 2' in detail2

    def test_exception_single(self):
        """Tests for a serialization exception on a filtered single
        response.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()

        self.manager.create_api(self.Person, serializer_class=raise_exception)

        query_string = {'filter[single]': 1}
        response = self.app.get('/api/person', query_string=query_string)
        check_sole_error(response, 500, ['Failed to serialize', 'type',
                                         'person', 'ID', '1'])


class TestFetchResource(ManagerTestBase):
    """Tests for serializing when fetching from a resource endpoint."""

    def setUp(self):
        super(TestFetchResource, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person', backref=backref('articles'))

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            uuid = Column(GUID)
            name = Column(Unicode)

            birthday = Column(Date)
            bedtime = Column(Time)
            birth_datetime = Column(DateTime)

            decorated_datetime = Column(DecoratedDateTime)
            decorated_interval = Column(DecoratedInterval)

            # These class attributes are *not* columns, just hard-coded values.
            uuid_attribute = UUID(hex='f' * 32)
            datetime_attribute = datetime(1, 1, 1)

            @hybrid_property
            def has_early_bedtime(self):
                if not hasattr(self, 'bedtime') or self.bedtime is None:
                    return False
                nine_oclock = time(21)
                return self.bedtime < nine_oclock

        class Comment(self.Base):
            __tablename__ = 'comment'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person', backref=backref('comments'))
            article_id = Column(Integer, ForeignKey('article.id'))
            article = relationship('Article', backref=backref('comments'))

        class Tag(self.Base):
            __tablename__ = 'tag'
            tagid = Column(Integer, primary_key=True)

        self.Article = Article
        self.Comment = Comment
        self.Person = Person
        self.Tag = Tag
        self.Base.metadata.create_all()

    def test_hybrid_property(self):
        """Tests for fetching a resource with a hybrid property attribute."""
        person1 = self.Person(id=1, bedtime=time(20))
        person2 = self.Person(id=2, bedtime=time(22))
        self.session.add_all([person1, person2])
        self.session.commit()
        self.manager.create_api(self.Person)
        response = self.app.get('/api/person/1')
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['has_early_bedtime']
        response = self.app.get('/api/person/2')
        document = loads(response.data)
        person = document['data']
        assert not person['attributes']['has_early_bedtime']

    def test_uuid(self):
        """Tests for serializing a (non-primary key) UUID field."""
        uuid = uuid1()
        person = self.Person(id=1, uuid=uuid)
        self.session.add(person)
        self.session.commit()
        self.manager.create_api(self.Person)
        response = self.app.get('/api/person/1')
        assert response.status_code == 200
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['uuid'] == str(uuid)

    def test_uuid_as_additional_attribute(self):
        """Tests that a UUID is serialized as a string when it is an
        attribute of the model but *not* a SQLAlchemy column.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        self.manager.create_api(self.Person,
                                additional_attributes=['uuid_attribute'])
        response = self.app.get('/api/person/1')
        document = loads(response.data)
        person = document['data']
        attributes = person['attributes']
        assert attributes['uuid_attribute'] == str(self.Person.uuid_attribute)

    def test_time(self):
        """Test for getting the JSON representation of a time field."""
        now = datetime.now().time()
        person = self.Person(id=1, bedtime=now)
        self.session.add(person)
        self.session.commit()
        self.manager.create_api(self.Person)
        response = self.app.get('/api/person/1')
        assert response.status_code == 200
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['bedtime'] == now.isoformat()

    def test_datetime(self):
        """Test for getting the JSON representation of a datetime field."""
        now = datetime.now()
        person = self.Person(id=1, birth_datetime=now)
        self.session.add(person)
        self.session.commit()
        self.manager.create_api(self.Person)
        response = self.app.get('/api/person/1')
        assert response.status_code == 200
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['birth_datetime'] == now.isoformat()

    def test_datetime_as_additional_attribute(self):
        """Tests that a datetime is serialized as a string when it is an
        attribute of the model but *not* a SQLAlchemy column.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        self.manager.create_api(self.Person,
                                additional_attributes=['datetime_attribute'])
        response = self.app.get('/api/person/1')
        document = loads(response.data)
        person = document['data']
        attributes = person['attributes']
        expected = self.Person.datetime_attribute
        assert attributes['datetime_attribute'] == expected.isoformat()

    def test_date(self):
        """Test for getting the JSON representation of a date field."""
        now = datetime.now().date()
        person = self.Person(id=1, birthday=now)
        self.session.add(person)
        self.session.commit()
        self.manager.create_api(self.Person)
        response = self.app.get('/api/person/1')
        assert response.status_code == 200
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['birthday'] == now.isoformat()

    def test_type_decorator_datetime(self):
        """Tests for serializing "subtypes" of the SQLAlchemy
        :class:`sqlalchemy.DateTime` class.

        """
        now = datetime.now()
        person = self.Person(id=1, decorated_datetime=now)
        self.session.add(person)
        self.session.commit()
        self.manager.create_api(self.Person)
        response = self.app.get('/api/person/1')
        assert response.status_code == 200
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['decorated_datetime'] == now.isoformat()

    def test_type_decorator_interval(self):
        """Tests for serializing "subtypes" of the SQLAlchemy
        :class:`sqlalchemy.Interval` class.

        """
        # This timedelta object represents an interval of ten seconds.
        interval = timedelta(0, 10)
        person = self.Person(id=1, decorated_interval=interval)
        self.session.add(person)
        self.session.commit()
        self.manager.create_api(self.Person)
        response = self.app.get('/api/person/1')
        assert response.status_code == 200
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['decorated_interval'] == 10

    def test_custom_serialize(self):
        """Tests for a custom serialization function."""
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()

        class MySerializer(DefaultSerializer):

            def serialize(self, *args, **kw):
                result = super(MySerializer, self).serialize(*args, **kw)
                result['data']['attributes']['foo'] = 'bar'
                return result

        self.manager.create_api(self.Person, serializer_class=MySerializer)
        response = self.app.get('/api/person/1')
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['foo'] == 'bar'

    def test_per_model_serializer_on_included(self):
        """Tests that a response that includes resources of multiple
        types respects the model-specific serializers provided to the
        :meth:`APIManager.create_api` method when called with different
        model classes.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([person, article])
        self.session.commit()

        class MySerializer(DefaultSerializer):

            secret = None

            def serialize(self, *args, **kw):
                result = super(MySerializer, self).serialize(*args, **kw)
                if 'attributes' not in result['data']:
                    result['data']['attributes'] = {}
                result['data']['attributes'][self.secret] = self.secret
                return result

        class FooSerializer(MySerializer):
            secret = 'foo'

        class BarSerializer(MySerializer):
            secret = 'bar'

        self.manager.create_api(self.Person, serializer_class=FooSerializer)
        self.manager.create_api(self.Article, serializer_class=BarSerializer)

        query_string = {'include': 'author'}
        response = self.app.get('/api/article/1', query_string=query_string)
        document = loads(response.data)
        # First, the article resource should have an extra 'bar' attribute.
        article = document['data']
        assert article['attributes']['bar'] == 'bar'
        assert 'foo' not in article['attributes']
        # Second, there should be a single included resource, a person
        # with a 'foo' attribute.
        included = document['included']
        assert len(included) == 1
        author = included[0]
        assert author['attributes']['foo'] == 'foo'
        assert 'bar' not in author['attributes']

    def test_exception(self):
        """Tests that exceptions are caught when a custom serialization method
        raises an exception.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()

        self.manager.create_api(self.Person, serializer_class=raise_exception)

        response = self.app.get('/api/person/1')
        check_sole_error(response, 500, ['Failed to serialize', 'type',
                                         'person', 'ID', '1'])

    def test_exception_on_included(self):
        """Tests that exceptions are caught when a custom serialization method
        raises an exception when serializing an included resource.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()

        self.manager.create_api(self.Person)
        self.manager.create_api(self.Article, serializer_class=raise_exception)

        query_string = {'include': 'articles'}
        response = self.app.get('/api/person/1', query_string=query_string)
        check_sole_error(response, 500, ['Failed to serialize', 'type',
                                         'article', 'ID', '1'])

    def test_multiple_exceptions_on_included(self):
        """Tests that multiple serialization exceptions are caught when
        a custom serialization method raises an exception when
        serializing an included resource.

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        article1.author = person1
        article2.author = person2
        self.session.add_all([article1, article2, person1, person2])
        self.session.commit()

        self.manager.create_api(self.Article)
        self.manager.create_api(self.Person, serializer_class=raise_exception)

        query_string = {'include': 'author'}
        response = self.app.get('/api/article', query_string=query_string)
        assert response.status_code == 500
        document = loads(response.data)
        errors = document['errors']
        assert len(errors) == 2
        error1, error2 = errors
        assert error1['status'] == 500
        assert error2['status'] == 500
        assert 'Failed to serialize included resource' in error1['detail']
        assert 'Failed to serialize included resource' in error2['detail']
        assert 'ID 1' in error1['detail'] or 'ID 1' in error2['detail']
        assert 'ID 2' in error1['detail'] or 'ID 2' in error2['detail']

    def test_circular_includes(self):
        """Tests that circular includes are only included once."""
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        comment1 = self.Comment(id=1)
        comment2 = self.Comment(id=2)
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        comment1.article = article1
        comment2.article = article2
        comment1.author = person1
        comment2.author = person2
        article1.author = person1
        article2.author = person1
        resources = [article1, article2, comment1, comment2, person1, person2]
        self.session.add_all(resources)
        self.session.commit()

        self.manager.create_api(self.Article)
        self.manager.create_api(self.Comment)
        self.manager.create_api(self.Person)

        # The response to this request should include person1 once (for
        # the first 'author') and person 2 once (for the last 'author').
        query_string = {'include': 'author.articles.comments.author'}
        response = self.app.get('/api/comment/1', query_string=query_string)
        document = loads(response.data)
        included = document['included']
        # Sort the included resources, first by type, then by ID.
        resources = sorted(included, key=lambda x: (x['type'], x['id']))
        resource_types = [resource['type'] for resource in resources]
        resource_ids = [resource['id'] for resource in resources]
        # We expect two articles, two persons, and one comment (since
        # the other comment is the primary data in the response
        # document).
        expected_types = ['article', 'article', 'comment', 'person', 'person']
        expected_ids = ['1', '2', '2', '1', '2']
        assert expected_types == resource_types
        assert expected_ids == resource_ids

    def test_exception_message(self):
        """Tests that a message specified in the
        :exc:`~flask_restless.SerializationException` constructor
        appears in an error response.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()

        class raise_with_msg(DefaultSerializer):

            def serialize(self, instance, *args, **kw):
                raise SerializationException(instance, message='foo')

        self.manager.create_api(self.Person, serializer_class=raise_with_msg)

        response = self.app.get('/api/person/1')
        check_sole_error(response, 500, ['foo'])

    def test_non_id_primary_key(self):
        """Test for a primary key field that is not named "id".

        For more information, see issue #540.

        """
        tag = self.Tag(tagid=1)
        self.session.add(tag)
        self.session.commit()
        self.manager.create_api(self.Tag)
        response = self.app.get('/api/tag/1')
        document = loads(response.data)
        tag = document['data']
        self.assertEqual(tag['id'], '1')
        self.assertEqual(tag['type'], 'tag')
        self.assertEqual(tag['attributes']['tagid'], 1)

    @skipUnless(is_future_available, 'required "future" library')
    def test_unicode_self_link(self):
        """Test that serializing the "self" link handles unicode on Python 2.

        This is a specific test for code using the :mod:`future` library.

        For more information, see GitHub issue #594.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        self.manager.create_api(self.Person)
        self.app.get('/api/person/1')


class TestFetchRelation(ManagerTestBase):

    def setUp(self):
        super(TestFetchRelation, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person', backref=backref('articles'))

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        self.Article = Article
        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Article)
        self.manager.create_api(Person)

    def test_exception_to_many(self):
        """Tests that exceptions are caught when a custom serialization method
        raises an exception on a to-many relation.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([person, article])
        self.session.commit()

        self.manager.create_api(self.Person)
        self.manager.create_api(self.Article, serializer_class=raise_exception)

        response = self.app.get('/api/person/1/articles')
        check_sole_error(response, 500, ['Failed to serialize', 'type',
                                         'article', 'ID', '1'])

    def test_exception_to_one(self):
        """Tests that exceptions are caught when a custom serialization method
        raises an exception on a to-one relation.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([person, article])
        self.session.commit()

        self.manager.create_api(self.Person, serializer_class=raise_exception)
        self.manager.create_api(self.Article)

        response = self.app.get('/api/article/1/author')
        check_sole_error(response, 500, ['Failed to serialize', 'type',
                                         'person', 'ID', '1'])

    def test_exception_on_included(self):
        """Tests that exceptions are caught when a custom serialization method
        raises an exception when serializing an included resource.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()

        self.manager.create_api(self.Person, serializer_class=raise_exception)
        self.manager.create_api(self.Article)

        params = {'include': 'author'}
        response = self.app.get('/api/person/1/articles', query_string=params)
        assert response.status_code == 500
        check_sole_error(response, 500, ['Failed to serialize',
                                         'included resource', 'type', 'person',
                                         'ID', '1'])


class TestFetchRelatedResource(ManagerTestBase):
    """Tests for serializing when fetching from a related resource endpoint."""

    def setUp(self):
        super(TestFetchRelatedResource, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person', backref=backref('articles'))

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        self.Article = Article
        self.Person = Person
        self.Base.metadata.create_all()

    def test_exception(self):
        """Tests that serialization exceptions are caught when fetching
        a related resource.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([person, article])
        self.session.commit()

        self.manager.create_api(self.Person)
        self.manager.create_api(self.Article, serializer_class=raise_exception)

        response = self.app.get('/api/person/1/articles/1')
        check_sole_error(response, 500, ['Failed to serialize', 'type',
                                         'article', 'ID', '1'])

    def test_exception_on_included(self):
        """Tests that serialization exceptions are caught for included
        resource on a request to fetch a related resource.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()

        self.manager.create_api(self.Person, serializer_class=raise_exception)
        self.manager.create_api(self.Article)

        query_string = {'include': 'author'}
        response = self.app.get('/api/person/1/articles/1',
                                query_string=query_string)
        check_sole_error(response, 500, ['Failed to serialize',
                                         'included resource', 'type', 'person',
                                         'ID', '1'])
