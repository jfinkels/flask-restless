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
from uuid import uuid1

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

from flask.ext.restless import simple_serialize
from flask.ext.restless import SerializationException

from .helpers import check_sole_error
from .helpers import GUID
from .helpers import loads
from .helpers import ManagerTestBase


def raise_exception(instance, *args, **kw):
    """Immediately raises a :exc:`SerializationException` with access to
    the provided `instance` of a SQLAlchemy model.

    This function is useful for use in tests for serialization
    exceptions.

    """
    raise SerializationException(instance)


class DecoratedDateTime(TypeDecorator):

    impl = DateTime


class DecoratedInterval(TypeDecorator):

    impl = Interval


class TestFetchCollection(ManagerTestBase):
    """Tests for serializing when fetching from a collection endpoint."""

    def setup(self):
        super(TestFetchCollection, self).setup()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        self.Person = Person
        self.Base.metadata.create_all()

    def test_exception_single(self):
        """Tests for a serialization exception on a filtered single
        response.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()

        self.manager.create_api(self.Person, serializer=raise_exception)

        query_string = {'filter[single]': 1}
        response = self.app.get('/api/person', query_string=query_string)
        check_sole_error(response, 500, ['Failed to serialize', 'type',
                                         'person', 'ID', '1'])


class TestFetchResource(ManagerTestBase):
    """Tests for serializing when fetching from a resource endpoint."""

    def setup(self):
        super(TestFetchResource, self).setup()

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

        self.Article = Article
        self.Comment = Comment
        self.Person = Person
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

    def test_custom_function(self):
        """Tests for a custom serialization function."""
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()

        def serializer(instance, **kw):
            result = simple_serialize(instance, **kw)
            result['attributes']['foo'] = 'bar'
            return result

        self.manager.create_api(self.Person, serializer=serializer)
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

        def add_foo(instance, *args, **kw):
            result = simple_serialize(instance, *args, **kw)
            if 'attributes' not in result:
                result['attributes'] = {}
            result['attributes']['foo'] = 'foo'
            return result

        def add_bar(instance, *args, **kw):
            result = simple_serialize(instance, *args, **kw)
            if 'attributes' not in result:
                result['attributes'] = {}
            result['attributes']['bar'] = 'bar'
            return result

        self.manager.create_api(self.Person, serializer=add_foo)
        self.manager.create_api(self.Article, serializer=add_bar)

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

        self.manager.create_api(self.Person, serializer=raise_exception)

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
        self.manager.create_api(self.Article, serializer=raise_exception)

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
        self.manager.create_api(self.Person, serializer=raise_exception)

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
        :exc:`~flask.ext.restless.SerializationException` constructor
        appears in an error response.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()

        def raise_with_msg(instance, *args, **kw):
            raise SerializationException(instance, message='foo')

        self.manager.create_api(self.Person, serializer=raise_with_msg)

        response = self.app.get('/api/person/1')
        check_sole_error(response, 500, ['foo'])


class TestFetchRelation(ManagerTestBase):

    def setup(self):
        super(TestFetchRelation, self).setup()

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
        raises an exception on a to-one relation.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([person, article])
        self.session.commit()

        self.manager.create_api(self.Person)
        self.manager.create_api(self.Article, serializer=raise_exception)

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

        self.manager.create_api(self.Person, serializer=raise_exception)
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

        self.manager.create_api(self.Person, serializer=raise_exception)
        self.manager.create_api(self.Article)

        params = {'include': 'author'}
        response = self.app.get('/api/person/1/articles', query_string=params)
        assert response.status_code == 500
        check_sole_error(response, 500, ['Failed to serialize',
                                         'included resource', 'type', 'person',
                                         'ID', '1'])


class TestFetchRelatedResource(ManagerTestBase):
    """Tests for serializing when fetching from a related resource endpoint."""

    def setup(self):
        super(TestFetchRelatedResource, self).setup()

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
        self.manager.create_api(self.Article, serializer=raise_exception)

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

        self.manager.create_api(self.Person, serializer=raise_exception)
        self.manager.create_api(self.Article)

        query_string = {'include': 'author'}
        response = self.app.get('/api/person/1/articles/1',
                                query_string=query_string)
        check_sole_error(response, 500, ['Failed to serialize',
                                         'included resource', 'type', 'person',
                                         'ID', '1'])
