"""
    tests.test_jsonapi
    ~~~~~~~~~~~~~~~~~~

    Provides tests ensuring that Flask-Restless meets the requirements of the
    `JSON API`_ standard.

    .. _JSON API: http://jsonapi.org

    :copyright: 2015 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com> and
                contributors.
    :license: GNU AGPLv3+ or BSD

"""
import string
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse
import uuid

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import func
from sqlalchemy import Integer
from sqlalchemy import Unicode
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship
from sqlalchemy.types import CHAR
from sqlalchemy.types import TypeDecorator

from flask.ext.restless import CONTENT_TYPE

from .helpers import dumps
from .helpers import loads
from .helpers import ManagerTestBase


# This code is adapted from
# http://docs.sqlalchemy.org/en/latest/core/custom_types.html#backend-agnostic-guid-type
class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses Postgresql's UUID type, otherwise uses CHAR(32), storing as
    stringified hex values.

    """
    impl = CHAR

    def load_dialect_impl(self, dialect):
        descriptor = UUID() if dialect.name == 'postgresql' else CHAR(32)
        return dialect.type_descriptor(descriptor)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == 'postgresql':
            return str(value)
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(value).hex
        # If we get to this point, we assume `value` is a UUID object.
        return value.hex

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return uuid.UUID(value)


class TestServerResponsibilities(ManagerTestBase):
    """Tests corresponding to the `Server Responsibilities`_ section of
    the JSON API specification.

    .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

    """

    def setUp(self):
        super(TestServerResponsibilities, self).setUp()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        #self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Person)

    def test_response_content_type(self):
        """"Tests that a server responds with the correct content type.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

        """
        response = self.app.get('/api/person')
        assert response.mimetype == CONTENT_TYPE

    def test_no_response_media_type_params(self):
        """"Tests that a server responds with :http:status:`415` if any
        media type parameters appear in the request content type header.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

        """
        headers = {'Content-Type': '{}; version=1'.format(CONTENT_TYPE)}
        response = self.app.get('/api/person', headers=headers)
        assert response.status_code == 415

    def test_no_accept_media_type_params(self):
        """"Tests that a server responds with :http:status:`406` if each
        :http:header:`Accept` header is the JSON API media type, but
        each instance of that media type has a media type parameter.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

        """
        headers = [('Accept', '{}; version=1'.format(CONTENT_TYPE)),
                   ('Accept', '{}; foo=bar'.format(CONTENT_TYPE))]
        response = self.app.get('/api/person', headers=headers)
        assert response.status_code == 406


class TestDocumentStructure(ManagerTestBase):
    """Tests corresponding to the `Document Structure`_ section of the JSON API
    specification.

    .. _Document Structure: http://jsonapi.org/format/#document-structure

    """

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        and :class:`TestSupport.Article` models.

        """
        super(TestDocumentStructure, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            articles = relationship(Article)
            comments = relationship('Comment')

        class Comment(self.Base):
            __tablename__ = 'comment'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')

        self.Article = Article
        self.Comment = Comment
        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Article)
        self.manager.create_api(Comment)
        self.manager.create_api(Person, methods=['GET', 'POST'])

    def test_ignore_additional_members(self):
        """Tests that the server ignores any additional top-level members.

        For more information, see the `Document Structure`_ section of the JSON
        API specification.

        .. _Document Structure: http://jsonapi.org/format/#document-structure

        """
        # The key `bogus` is unknown to the JSON API specification, and
        # therefore should be ignored.
        data = dict(data=dict(type='person'), bogus=True)
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        assert 'errors' not in document
        assert self.session.query(self.Person).count() == 1

    def test_allowable_top_level_keys(self):
        """Tests that a response contains at least one of the top-level
        elements ``data``, ``errors``, and ``meta``.

        For more information, see the `Top Level`_ section of the JSON
        API specification.

        .. _Top Level: http://jsonapi.org/format/#document-top-level

        """
        response = self.app.get('/api/person')
        allowable_keys = ('data', 'errors', 'meta')
        assert any(key in loads(response.data) for key in allowable_keys)

    def test_no_data_and_errors_good_request(self):
        """Tests that a response to a valid request does not contain
        both ``data`` and ``errors`` simultaneously as top-level
        elements.

        For more information, see the `Top Level`_ section of the JSON
        API specification.

        .. _Top Level: http://jsonapi.org/format/#document-top-level

        """
        response = self.app.get('/api/person')
        assert not all(k in loads(response.data) for k in ('data', 'errors'))

    def test_no_data_and_errors_bad_request(self):
        """Tests that a response to an invalid request does not contain
        both ``data`` and ``errors`` simultaneously as top-level
        elements.

        For more information, see the `Top Level`_ section of the JSON
        API specification.

        .. _Top Level: http://jsonapi.org/format/#document-top-level

        """
        response = self.app.get('/api/person/boguskey')
        assert not all(k in loads(response.data) for k in ('data', 'errors'))

    def test_errors_top_level_key(self):
        """Tests that errors appear under a top-level key ``errors``."""
        response = self.app.get('/api/person/boguskey')
        data = loads(response.data)
        assert 'errors' in data

    def test_no_other_top_level_keys(self):
        """Tests that no there are no other alphanumeric top-level keys in the
        response other than the allowed ones.

        For more information, see the `Top Level`_ section of the JSON API
        specification.

        .. _Top Level: http://jsonapi.org/format/#document-structure-top-level

        """
        response = self.app.get('/api/person')
        document = loads(response.data)
        allowed = ('data', 'errors', 'meta', 'jsonapi', 'links', 'included')
        alphanumeric = string.ascii_letters + string.digits
        assert all(d in allowed or d[0] not in alphanumeric for d in document)

    def test_resource_attributes(self):
        """Test that a resource has the required top-level keys.

        For more information, see the `Resource Objects`_ section of the JSON
        API specification.

        .. _Resource Objects: http://jsonapi.org/format/#document-resource-objects

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.get('/api/person/1')
        document = loads(response.data)
        person = document['data']
        assert person['id'] == '1'
        assert person['type'] == 'person'

    def test_no_foreign_keys(self):
        """By default, foreign keys should not appear in the representation of
        a resource.

        For more information, see the `Resource Object Attributes`_
        section of the JSON API specification.

        .. _Resource Object Attributes: http://jsonapi.org/format/#document-resource-object-attributes

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.get('/api/article/1')
        document = loads(response.data)
        article = document['data']
        assert 'attributes' not in article
        assert 'author_id' not in article

    def test_required_relationship_keys(self):
        """Tests that a relationship object contains at least one of the
        required keys, ``links``, ``data``, or ``meta``.

        For more information, see the `Resource Object Relationships`_
        section of the JSON API specification.

        .. _Resource Object Relationships: http://jsonapi.org/format/#document-resource-object-relationships

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.get('/api/person/1')
        document = loads(response.data)
        person = document['data']
        relationship = document['data']['relationships']['articles']
        assert any(key in relationship for key in ('data', 'links', 'meta'))

    def test_required_relationship_link_keys(self):
        """Tests that a relationship links object contains at least one
        of the required keys, ``self`` or ``related``.

        For more information, see the `Resource Object Relationships`_
        section of the JSON API specification.

        .. _Resource Object Relationships: http://jsonapi.org/format/#document-resource-object-relationships

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.get('/api/person/1')
        document = loads(response.data)
        relationship = document['data']['relationships']['articles']
        links = relationship['links']
        assert any(key in links for key in ('self', 'related'))

    def test_self_relationship_url(self):
        """Tests that a link object correctly identifies its own
        relationship URL.

        For more information, see the `Resource Object Relationships`_
        section of the JSON API specification.

        .. _Resource Object Relationships: http://jsonapi.org/format/#document-resource-object-relationships

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([person, article])
        self.session.commit()
        response = self.app.get('/api/article/1')
        document = loads(response.data)
        article = document['data']
        relationship = article['relationships']['author']
        relationship_url = relationship['links']['self']
        assert relationship_url.endswith('/api/article/1/links/author')

    def test_related_resource_url_to_one(self):
        """Tests that the related resource URL in a to-one relationship
        correctly identifies the related resource.

        For more information, see the `Related Resource Links`_ section
        of the JSON API specification.

        .. _Related Resource Links: http://jsonapi.org/format/#document-resource-object-related-resource-links

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([person, article])
        self.session.commit()
        # Get a resource that has links.
        response = self.app.get('/api/article/1')
        document = loads(response.data)
        article = document['data']
        # Get the related resource URL.
        resource_url = article['relationships']['author']['links']['related']
        # The Flask test client doesn't need the `netloc` part of the URL.
        path = urlparse(resource_url).path
        # Fetch the resource at the related resource URL.
        response = self.app.get(path)
        document = loads(response.data)
        actual_person = document['data']
        # Compare it with what we expect to get.
        response = self.app.get('/api/person/1')
        expected_person = loads(response.data)['data']
        assert actual_person == expected_person

    def test_related_resource_url_to_many(self):
        """Tests that the related resource URL in a to-many relationship
        correctly identifies the related resource.

        For more information, see the `Related Resource Links`_ section
        of the JSON API specification.

        .. _Related Resource Links: http://jsonapi.org/format/#document-resource-object-related-resource-links

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([person, article])
        self.session.commit()
        # Get a resource that has links.
        response = self.app.get('/api/person/1')
        document = loads(response.data)
        person = document['data']
        # Get the related resource URL.
        resource_url = person['relationships']['articles']['links']['related']
        # The Flask test client doesn't need the `netloc` part of the URL.
        path = urlparse(resource_url).path
        # Fetch the resource at the related resource URL.
        response = self.app.get(path)
        document = loads(response.data)
        actual_articles = document['data']
        # Compare it with what we expect to get.
        #
        # TODO To make this test more robust, filter by `article.author == 1`.
        response = self.app.get('/api/article')
        document = loads(response.data)
        expected_articles = document['data']
        assert actual_articles == expected_articles

    def test_resource_linkage_empty_to_one(self):
        """Tests that resource linkage for an empty to-one relationship
        is ``null``.

        For more information, see the `Resource Linkage`_ section of the
        JSON API specification.

        .. _Resource Linkage: http://jsonapi.org/format/#document-resource-object-linkage

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.get('/api/article/1')
        document = loads(response.data)
        article = document['data']
        author_relationship = article['relationships']['author']
        linkage = author_relationship['data']
        assert linkage is None

    def test_resource_linkage_empty_to_many(self):
        """Tests that resource linkage for an empty to-many relationship
        is an empty list.

        For more information, see the `Resource Linkage`_ section of the
        JSON API specification.

        .. _Resource Linkage: http://jsonapi.org/format/#document-resource-object-linkage

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.get('/api/person/1')
        document = loads(response.data)
        person = document['data']
        articles_relationship = person['relationships']['articles']
        linkage = articles_relationship['data']
        assert linkage == []

    def test_resource_linkage_to_one(self):
        """Tests that resource linkage for a to-one relationship is
        a single resource identifier object.

        For more information, see the `Resource Linkage`_ section of the
        JSON API specification.

        .. _Resource Linkage: http://jsonapi.org/format/#document-resource-object-linkage

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        response = self.app.get('/api/article/1')
        document = loads(response.data)
        article = document['data']
        author_relationship = article['relationships']['author']
        linkage = author_relationship['data']
        assert linkage['id'] == '1'
        assert linkage['type'] == 'person'

    def test_resource_linkage_to_many(self):
        """Tests that resource linkage for a to-many relationship is a
        list of resource identifier objects.

        For more information, see the `Resource Linkage`_ section of the
        JSON API specification.

        .. _Resource Linkage: http://jsonapi.org/format/#document-resource-object-linkage

        """
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        person = self.Person(id=1)
        person.articles = [article1, article2]
        self.session.add_all([person, article1, article2])
        self.session.commit()
        response = self.app.get('/api/person/1')
        document = loads(response.data)
        person = document['data']
        articles_relationship = person['relationships']['articles']
        linkage = articles_relationship['data']
        assert ['1', '2'] == sorted(link['id'] for link in linkage)
        assert all(link['type'] == 'article' for link in linkage)

    def test_self_link(self):
        """Tests that a request to a self link responds with the same
        object.

        For more information, see the `Resource Links`_ section of the
        JSON API specification.

        .. _Resource Links: http://jsonapi.org/format/#document-resource-object-links

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.get('/api/person/1')
        document1 = loads(response.data)
        person = document1['data']
        selfurl = person['links']['self']
        # The Flask test client doesn't need the `netloc` part of the URL.
        path = urlparse(selfurl).path
        response = self.app.get(path)
        document2 = loads(response.data)
        assert document1 == document2

    def test_resource_identifier_object_keys(self):
        """Tests that a resource identifier object contains the required
        keys.

        For more information, see the `Resource Identifier Objects`_
        section of the JSON API specification.

        .. _Resource Identifier Objects: http://jsonapi.org/format/#document-resource-identifier-objects

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        response = self.app.get('/api/article/1')
        document = loads(response.data)
        article = document['data']
        author_relationship = article['relationships']['author']
        linkage = author_relationship['data']
        assert all(key in linkage for key in ('id', 'type'))
        assert linkage['id'] == '1'
        assert linkage['type'] == 'person'

    # def test_link_object(self):
    #     """Tests for relations as resource URLs."""
    #     # TODO configure the api manager here
    #     person = self.Person(id=1)
    #     self.session.add(person)
    #     self.session.commit()
    #     response = self.app.get('/api/person/1')
    #     person = loads(response.data)['data']
    #     links = person['relationships']['articles']['links']
    #     # A link object must contain at least one of 'self', 'related',
    #     # linkage to a compound document, or 'meta'.
    #     assert links['self'].endswith('/api/person/1/links/articles')
    #     assert links['related'].endswith('/api/person/1/articles')
    #     # TODO should also include pagination links

    # def test_link_object_allowable_keys(self):
    #     """Tests that only allowable keys exist in the link object.

    #     For more information, see the `Resource Relationships`_ section of the
    #     JSON API specification.

    #     .. _Resource Relationships: http://jsonapi.org/format/#document-structure-resource-relationships

    #     """
    #     response = self.app.get('/api/person')
    #     document = loads(response.data)
    #     allowed = ('self', 'resource', 'type', 'id', 'meta', 'first', 'last',
    #                'next', 'prev')
    #     alphanumeric = string.ascii_letters + string.digits
    #     for link_name, link_object in document['links'].items():
    #         if link_name not in ('first', 'last', 'next', 'prev', 'self'):
    #             assert all(k in allowed or k[0] not in alphanumeric
    #                        for k in link_object)

    def test_top_level_self_link(self):
        """Tests that there is a top-level links object containing a
        self link.

        For more information, see the `Links`_ section of the JSON API
        specification.

        .. _Links: http://jsonapi.org/format/#document-links

        """
        response = self.app.get('/api/person')
        document = loads(response.data)
        links = document['links']
        assert links['self'].endswith('/api/person')

    def test_jsonapi_object(self):
        """Tests that the server provides a jsonapi object.

        For more information, see the `JSON API Object`_ section of the
        JSON API specification.

        .. _JSON API Object: http://jsonapi.org/format/#document-jsonapi-object

        """
        response = self.app.get('/api/person')
        document = loads(response.data)
        jsonapi = document['jsonapi']
        assert '1.0' == jsonapi['version']


class TestFetchingData(ManagerTestBase):
    """Tests corresponding to the `Fetching Data`_ section of the JSON API
    specification.

    .. _Fetching Data: http://jsonapi.org/format/#fetching

    """

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        and :class:`TestSupport.Article` models.

        """
        super(TestFetchingData, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            title = Column(Unicode)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')

        class Comment(self.Base):
            __tablename__ = 'comment'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')
            article_id = Column(Integer, ForeignKey('article.id'))
            article = relationship(Article, backref=backref('comments'))

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)
            age = Column(Integer)
            other = Column(Float)
            comments = relationship('Comment')
            articles = relationship('Article')

        self.Article = Article
        self.Comment = Comment
        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Article)
        self.manager.create_api(Person)
        # HACK Need to create APIs for these other models because otherwise
        # we're not able to create the link URLs to them.
        #
        # TODO Fix this by simply not creating links to related models for
        # which no API has been made.
        self.manager.create_api(Comment)

    # def test_correct_accept_header(self):
    #     """Tests that the server responds with a resource if the ``Accept``
    #     header specifies the JSON API media type.

    #     For more information, see the `Fetching Data`_ section of the JSON API
    #     specification.

    #     .. _Fetching Data: http://jsonapi.org/format/#fetching

    #     """
    #     # The fixtures for this test class set up the correct `Accept` header
    #     # for all requests from the test client.
    #     response = self.app.get('/api/person')
    #     assert response.status_code == 200
    #     assert response.mimetype == CONTENT_TYPE

    # def test_incorrect_accept_header(self):
    #     """Tests that the server responds with an :http:status:`415` if the
    #     ``Accept`` header is incorrect.

    #     For more information, see the `Fetching Data`_ section of the JSON API
    #     specification.

    #     .. _Fetching Data: http://jsonapi.org/format/#fetching

    #     """
    #     headers = dict(Accept='application/json')
    #     response = self.app.get('/api/person', headers=headers)
    #     assert response.status_code == 406
    #     assert response.mimetype == CONTENT_TYPE

    def test_single_resource(self):
        """Tests for fetching a single resource.

        For more information, see the `Fetching Resources`_ section of
        JSON API specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.get('/api/article/1')
        assert response.status_code == 200
        document = loads(response.data)
        article = document['data']
        assert article['id'] == '1'
        assert article['type'] == 'article'

    def test_collection(self):
        """Tests for fetching a collection of resources.

        For more information, see the `Fetching Resources`_ section of
        JSON API specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.get('/api/article')
        assert response.status_code == 200
        document = loads(response.data)
        articles = document['data']
        assert ['1'] == sorted(article['id'] for article in articles)

    def test_related_resource(self):
        """Tests for fetching a to-one related resource.

        For more information, see the `Fetching Resources`_ section of
        JSON API specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        article = self.Article(id=1)
        person = self.Person(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        response = self.app.get('/api/article/1/author')
        assert response.status_code == 200
        document = loads(response.data)
        author = document['data']
        assert author['type'] == 'person'
        assert author['id'] == '1'

    def test_empty_collection(self):
        """Tests for fetching an empty collection of resources.

        For more information, see the `Fetching Resources`_ section of
        JSON API specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        response = self.app.get('/api/person')
        assert response.status_code == 200
        document = loads(response.data)
        people = document['data']
        assert people == []

    def test_to_many_related_resource_url(self):
        """Tests for fetching to-many related resources from a related
        resource URL.

        The response to a request to a to-many related resource URL should
        include an array of resource objects, *not* linkage objects.

        For more information, see the `Fetching Resources`_ section of JSON API
        specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        person = self.Person(id=1)
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        person.articles = [article1, article2]
        self.session.add_all([person, article1, article2])
        self.session.commit()
        response = self.app.get('/api/person/1/articles')
        assert response.status_code == 200
        document = loads(response.data)
        articles = document['data']
        assert ['1', '2'] == sorted(article['id'] for article in articles)
        assert all(article['type'] == 'article' for article in articles)
        assert all('title' in article['attributes'] for article in articles)
        assert all('author' in article['relationships']
                   for article in articles)

    def test_to_one_related_resource_url(self):
        """Tests for fetching a to-one related resource from a related resource
        URL.

        The response to a request to a to-one related resource URL should
        include a resource object, *not* a linkage object.

        For more information, see the `Fetching Resources`_ section of JSON API
        specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([person, article])
        self.session.commit()
        response = self.app.get('/api/article/1/author')
        assert response.status_code == 200
        document = loads(response.data)
        author = document['data']
        assert author['id'] == '1'
        assert author['type'] == 'person'
        assert all(field in author['attributes']
                   for field in ('name', 'age', 'other'))

    def test_empty_to_many_related_resource_url(self):
        """Tests for fetching an empty to-many related resource from a related
        resource URL.

        For more information, see the `Fetching Resources`_ section of JSON API
        specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.get('/api/person/1/articles')
        assert response.status_code == 200
        document = loads(response.data)
        articles = document['data']
        assert articles == []

    def test_empty_to_one_related_resource(self):
        """Tests for fetching an empty to-one related resource from a related
        resource URL.

        For more information, see the `Fetching Resources`_ section of JSON API
        specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.get('/api/article/1/author')
        assert response.status_code == 200
        document = loads(response.data)
        author = document['data']
        assert author is None

    def test_nonexistent_resource(self):
        """Tests for fetching a nonexistent resource.

        For more information, see the `Fetching Resources`_ section of
        JSON API specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        response = self.app.get('/api/article/1')
        assert response.status_code == 404

    def test_nonexistent_collection(self):
        """Tests for fetching a nonexistent collection of resources.

        For more information, see the `Fetching Resources`_ section of
        JSON API specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        response = self.app.get('/api/bogus')
        assert response.status_code == 404

    def test_to_many_relationship_url(self):
        """Test for fetching linkage objects from a to-many relationship
        URL.

        The response to a request to a to-many relationship URL should
        be a linkage object, *not* a resource object.

        For more information, see the `Fetching Relationships`_ section
        of JSON API specification.

        .. _Fetching Relationships: http://jsonapi.org/format/#fetching-relationships

        """
        article = self.Article(id=1)
        comment1 = self.Comment(id=1)
        comment2 = self.Comment(id=2)
        article.comments = [comment1, comment2]
        self.session.add_all([article, comment1, comment2])
        self.session.commit()
        response = self.app.get('/api/article/1/relationships/comments')
        assert response.status_code == 200
        document = loads(response.data)
        comments = document['data']
        assert all(['id', 'type'] == sorted(comment) for comment in comments)
        assert ['1', '2'] == sorted(comment['id'] for comment in comments)
        assert all(comment['type'] == 'comment' for comment in comments)

    def test_empty_to_many_relationship_url(self):
        """Test for fetching from an empty to-many relationship URL.

        For more information, see the `Fetching Relationships`_ section of JSON
        API specification.

        .. _Fetching Relationships: http://jsonapi.org/format/#fetching-relationships

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.get('/api/article/1/relationships/comments')
        assert response.status_code == 200
        document = loads(response.data)
        comments = document['data']
        assert comments == []

    def test_to_one_relationship_url(self):
        """Test for fetching a resource from a to-one relationship URL.

        The response to a request to a to-many relationship URL should
        be a linkage object, *not* a resource object.

        For more information, see the `Fetching Relationships`_ section
        of JSON API specification.

        .. _Fetching Relationships: http://jsonapi.org/format/#fetching-relationships

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([person, article])
        self.session.commit()
        response = self.app.get('/api/article/1/relationships/author')
        assert response.status_code == 200
        document = loads(response.data)
        person = document['data']
        assert ['id', 'type'] == sorted(person)
        assert person['id'] == '1'
        assert person['type'] == 'person'

    def test_empty_to_one_relationship_url(self):
        """Test for fetching from an empty to-one relationship URL.

        For more information, see the `Fetching Relationships`_ section of JSON
        API specification.

        .. _Fetching Relationships: http://jsonapi.org/format/#fetching-relationships

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.get('/api/article/1/relationships/author')
        assert response.status_code == 200
        document = loads(response.data)
        person = document['data']
        assert person is None

    def test_relationship_links(self):
        """Tests for links included in relationship objects.

        For more information, see the `Fetching Relationships`_ section
        of JSON API specification.

        .. _Fetching Relationships: http://jsonapi.org/format/#fetching-relationships

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.get('/api/article/1/relationships/author')
        document = loads(response.data)
        links = document['links']
        assert links['self'].endswith('/article/1/relationships/author')
        assert links['related'].endswith('/article/1/author')

    def test_default_inclusion(self):
        """Tests that by default, Flask-Restless includes no information
        in compound documents.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        person.articles = [article]
        self.session.add_all([person, article])
        self.session.commit()
        # By default, no links will be included at the top level of the
        # document.
        response = self.app.get('/api/person/1')
        document = loads(response.data)
        person = document['data']
        articles = person['relationships']['articles']['data']
        assert ['1'] == sorted(article['id'] for article in articles)
        assert 'included' not in document

    def test_set_default_inclusion(self):
        """Tests that the user can specify default compound document
        inclusions when creating an API.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        person.articles = [article]
        self.session.add_all([person, article])
        self.session.commit()
        self.manager.create_api(self.Person, includes=['articles'],
                                url_prefix='/api2')
        # In the alternate API, articles are included by default in compound
        # documents.
        response = self.app.get('/api2/person/1')
        document = loads(response.data)
        person = document['data']
        linked = document['included']
        articles = person['relationships']['articles']['data']
        assert ['1'] == sorted(article['id'] for article in articles)
        assert linked[0]['type'] == 'article'
        assert linked[0]['id'] == '1'

    # # TODO The next few methods seem to be duplicates.
    # def test_compound_document_to_many(self):
    #     """Tests for getting linked resources from a to-many
    #     relationship in a compound document.

    #     For more information, see the `Compound Documents`_ section of
    #     the JSON API specification.

    #     .. _Compound Documents: http://jsonapi.org/format/#document-compound-documents

    #     """
    #     person = self.Person(id=1)
    #     article1 = self.Article(id=1)
    #     article2 = self.Article(id=2)
    #     person.articles = [article1, article2]
    #     self.session.add_all([person, article1, article2])
    #     self.session.commit()
    #     # For a to-many relationship, we should have an array of
    #     # objects, each of which has a 'type' key and an 'id' key.
    #     response = self.app.get('/api/person/1?include=articles')
    #     document = loads(response.data)
    #     person = document['data']
    #     articles = person['links']['articles']['linkage']
    #     assert all(article['type'] == 'article' for article in articles)
    #     assert ['1', '2'] == sorted(article['id'] for article in articles)
    #     linked = document['included']
    #     # Sort the links on their IDs, then get the two linked articles.
    #     linked_article1, linked_article2 = sorted(linked,
    #                                               key=lambda c: c['id'])
    #     assert linked_article1['type'] == 'article'
    #     assert linked_article1['id'] == '1'
    #     assert linked_article2['type'] == 'article'
    #     assert linked_article2['id'] == '2'

    # def test_compound_document_to_one(self):
    #     """Tests for getting linked resources from a to-one relationship
    #     in a compound document.

    #     For more information, see the `Compound Documents`_ section of
    #     the JSON API specification.

    #     .. _Compound Documents: http://jsonapi.org/format/#document-compound-documents

    #     """
    #     person = self.Person(id=1)
    #     article = self.Article(id=1)
    #     article.author = person
    #     self.session.add_all([person, article])
    #     self.session.commit()
    #     # For a to-one relationship, we should have a 'type' and an 'id' key.
    #     response = self.app.get('/api/article/1?include=author')
    #     document = loads(response.data)
    #     article = document['data']
    #     author = article['links']['author']['linkage']
    #     assert author['type'] == 'person'
    #     assert author['id'] == '1'
    #     linked = document['included']
    #     linked_person = linked[0]
    #     assert linked_person['type'] == 'person'
    #     assert linked_person['id'] == '1'

    # def test_compound_document_many_types(self):
    #     """Tests for getting linked resources of multiple types in a
    #     compound document.

    #     For more information, see the `Compound Documents`_ section of
    #     the JSON API specification.

    #     .. _Compound Documents: http://jsonapi.org/format/#document-compound-documents

    #     """
    #     article = self.Article(id=3)
    #     comment = self.Comment(id=2)
    #     person = self.Person(id=1)
    #     comment.author = person
    #     article.author = person
    #     self.session.add_all([article, person, comment])
    #     self.session.commit()
    #     query_string = dict(include='comments,articles')
    #     response = self.app.get('/api/person/1', query_string=query_string)
    #     document = loads(response.data)
    #     person = document['data']
    #     included = sorted(document['included'], key=lambda x: x['type'])
    #     assert ['article', 'comment'] == [x['type'] for x in included]
    #     assert ['3', '2'] == [x['id'] for x in included]

    def test_include(self):
        """Tests that the client can specify which linked relations to
        include in a compound document.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        person = self.Person(id=1, name='foo')
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        comment = self.Comment()
        person.articles = [article1, article2]
        person.comments = [comment]
        self.session.add_all([person, comment, article1, article2])
        self.session.commit()
        query_string = dict(include='articles')
        response = self.app.get('/api/person/1', query_string=query_string)
        assert response.status_code == 200
        document = loads(response.data)
        linked = document['included']
        # If a client supplied an include request parameter, no other types of
        # objects should be included.
        assert all(c['type'] == 'article' for c in linked)
        assert ['1', '2'] == sorted(c['id'] for c in linked)

    def test_include_multiple(self):
        """Tests that the client can specify multiple linked relations
        to include in a compound document.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        person = self.Person(id=1, name='foo')
        article = self.Article(id=2)
        comment = self.Comment(id=3)
        person.articles = [article]
        person.comments = [comment]
        self.session.add_all([person, comment, article])
        self.session.commit()
        query_string = dict(include='articles,comments')
        response = self.app.get('/api/person/1', query_string=query_string)
        assert response.status_code == 200
        document = loads(response.data)
        # Sort the linked objects by type; 'article' comes before 'comment'
        # lexicographically.
        linked = sorted(document['included'], key=lambda x: x['type'])
        linked_article, linked_comment = linked
        assert linked_article['type'] == 'article'
        assert linked_article['id'] == '2'
        assert linked_comment['type'] == 'comment'
        assert linked_comment['id'] == '3'

    def test_include_dot_separated(self):
        """Tests that the client can specify resources linked to other
        resources to include in a compound document.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        article = self.Article(id=1)
        comment1 = self.Comment(id=1)
        comment2 = self.Comment(id=2)
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        comment1.article = article
        comment2.article = article
        comment1.author = person1
        comment2.author = person2
        self.session.add_all([article, comment1, comment2, person1, person2])
        self.session.commit()
        query_string = dict(include='comments.author')
        response = self.app.get('/api/article/1', query_string=query_string)
        document = loads(response.data)
        authors = [resource for resource in document['included']
                   if resource['type'] == 'person']
        assert ['1', '2'] == sorted(author['id'] for author in authors)

    def test_include_intermediate_resources(self):
        """Tests that intermediate resources from a multi-part
        relationship path are included in a compound document.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        article = self.Article(id=1)
        comment1 = self.Comment(id=1)
        comment2 = self.Comment(id=2)
        article.comments = [comment1, comment2]
        comment1.author = person1
        comment2.author = person2
        self.session.add_all([article, comment1, comment2, person1, person2])
        self.session.commit()
        query_string = dict(include='comments.author')
        response = self.app.get('/api/article/1', query_string=query_string)
        document = loads(response.data)
        linked = document['included']
        # The included resources should be the two comments and the two
        # authors of those comments.
        assert len(linked) == 4
        authors = [r for r in linked if r['type'] == 'person']
        comments = [r for r in linked if r['type'] == 'comment']
        assert ['1', '2'] == sorted(author['id'] for author in authors)
        assert ['1', '2'] == sorted(comment['id'] for comment in comments)

    def test_include_relationship(self):
        """Tests for including related resources from a relationship endpoint.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        article = self.Article(id=1)
        comment1 = self.Comment(id=1)
        comment2 = self.Comment(id=2)
        article.comments = [comment1, comment2]
        comment1.author = person1
        comment2.author = person2
        self.session.add_all([article, comment1, comment2, person1, person2])
        self.session.commit()
        query_string = dict(include='comments.author')
        response = self.app.get('/api/article/1/relationships/comments',
                                query_string=query_string)
        # In this case, the primary data is a collection of resource
        # identifier objects that represent linkage to comments for an
        # article, while the full comments and comment authors would be
        # returned as included data.
        #
        # This differs from the previous test because the primary data
        # is a collection of relationship objects instead of a
        # collection of resource objects.
        document = loads(response.data)
        links = document['data']
        assert all(sorted(link) == ['id', 'type'] for link in links)
        included = document['included']
        # The included resources should be the two comments and the two
        # authors of those comments.
        assert len(included) == 4
        authors = [r for r in included if r['type'] == 'person']
        comments = [r for r in included if r['type'] == 'comment']
        assert ['1', '2'] == sorted(author['id'] for author in authors)
        assert ['1', '2'] == sorted(comment['id'] for comment in comments)

    def test_client_overrides_server_includes(self):
        """Tests that if a client supplies an include query parameter, the
        server does not include any other resource objects in the included
        section of the compound document.

        For more information, see the `Inclusion of Related Resources`_ section
        of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        person = self.Person(id=1)
        article = self.Article(id=2)
        comment = self.Comment(id=3)
        article.author = person
        comment.author = person
        self.session.add_all([person, article, comment])
        self.session.commit()
        # The server will, by default, include articles. The client will
        # override this and request only comments.
        self.manager.create_api(self.Person, url_prefix='/api2',
                                includes=['articles'])
        query_string = dict(include='comments')
        response = self.app.get('/api2/person/1', query_string=query_string)
        document = loads(response.data)
        included = document['included']
        assert ['3'] == sorted(obj['id'] for obj in included)
        assert ['comment'] == sorted(obj['type'] for obj in included)

    def test_sparse_fieldsets(self):
        """Tests that the client can specify which fields to return in the
        response of a fetch request for a single object.

        For more information, see the `Sparse Fieldsets`_ section
        of the JSON API specification.

        .. _Sparse Fieldsets: http://jsonapi.org/format/#fetching-sparse-fieldsets

        """
        person = self.Person(id=1, name='foo', age=99)
        self.session.add(person)
        self.session.commit()
        query_string = {'fields[person]': 'id,name'}
        response = self.app.get('/api/person/1', query_string=query_string)
        document = loads(response.data)
        person = document['data']
        # ID and type must always be included.
        assert ['attributes', 'id', 'type'] == sorted(person)
        assert ['name'] == sorted(person['attributes'])

    def test_sparse_fieldsets_id_and_type(self):
        """Tests that the ID and type of the resource are always included in a
        response from a request for sparse fieldsets, regardless of what the
        client requests.

        For more information, see the `Sparse Fieldsets`_ section
        of the JSON API specification.

        .. _Sparse Fieldsets: http://jsonapi.org/format/#fetching-sparse-fieldsets

        """
        person = self.Person(id=1, name='foo', age=99)
        self.session.add(person)
        self.session.commit()
        query_string = {'fields[person]': 'id'}
        response = self.app.get('/api/person/1', query_string=query_string)
        document = loads(response.data)
        person = document['data']
        # ID and type must always be included.
        assert ['id', 'type'] == sorted(person)

    def test_sparse_fieldsets_collection(self):
        """Tests that the client can specify which fields to return in the
        response of a fetch request for a collection of objects.

        For more information, see the `Sparse Fieldsets`_ section
        of the JSON API specification.

        .. _Sparse Fieldsets: http://jsonapi.org/format/#fetching-sparse-fieldsets

        """
        person1 = self.Person(id=1, name='foo', age=99)
        person2 = self.Person(id=2, name='bar', age=80)
        self.session.add_all([person1, person2])
        self.session.commit()
        query_string = {'fields[person]': 'id,name'}
        response = self.app.get('/api/person', query_string=query_string)
        document = loads(response.data)
        people = document['data']
        assert all(['attributes', 'id', 'type'] == sorted(p) for p in people)
        assert all(['name'] == sorted(p['attributes']) for p in people)

    def test_sparse_fieldsets_multiple_types(self):
        """Tests that the client can specify which fields to return in the
        response with multiple types specified.

        For more information, see the `Sparse Fieldsets`_ section
        of the JSON API specification.

        .. _Sparse Fieldsets: http://jsonapi.org/format/#fetching-sparse-fieldsets

        """
        article = self.Article(id=1, title='bar')
        person = self.Person(id=1, name='foo', age=99, articles=[article])
        self.session.add_all([person, article])
        self.session.commit()
        # Person objects should only have ID and name, while article objects
        # should only have ID.
        query_string = {'include': 'articles',
                        'fields[person]': 'id,name,articles',
                        'fields[article]': 'id'}
        response = self.app.get('/api/person/1', query_string=query_string)
        document = loads(response.data)
        person = document['data']
        linked = document['included']
        # We requested 'id', 'name', and 'articles'; 'id' and 'type' must
        # always be present; 'name' comes under an 'attributes' key; and
        # 'articles' comes under a 'links' key.
        assert ['attributes', 'id', 'relationships', 'type'] == sorted(person)
        assert ['articles'] == sorted(person['relationships'])
        assert ['name'] == sorted(person['attributes'])
        # We requested only 'id', but 'type' must always appear as well.
        assert all(['id', 'type'] == sorted(article) for article in linked)

    def test_sort_increasing(self):
        """Tests that the client can specify the fields on which to sort
        the response in increasing order.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: http://jsonapi.org/format/#fetching-sorting

        """
        person1 = self.Person(name='foo', age=20)
        person2 = self.Person(name='bar', age=10)
        person3 = self.Person(name='baz', age=30)
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        query_string = {'sort': 'age'}
        response = self.app.get('/api/person', query_string=query_string)
        document = loads(response.data)
        people = document['data']
        age1, age2, age3 = (p['attributes']['age'] for p in people)
        assert age1 <= age2 <= age3

    def test_sort_decreasing(self):
        """Tests that the client can specify the fields on which to sort
        the response in decreasing order.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: http://jsonapi.org/format/#fetching-sorting

        """
        person1 = self.Person(name='foo', age=20)
        person2 = self.Person(name='bar', age=10)
        person3 = self.Person(name='baz', age=30)
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        query_string = {'sort': '-age'}
        response = self.app.get('/api/person', query_string=query_string)
        document = loads(response.data)
        people = document['data']
        age1, age2, age3 = (p['attributes']['age'] for p in people)
        assert age1 >= age2 >= age3

    def test_sort_multiple_fields(self):
        """Tests that the client can sort by multiple fields.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: http://jsonapi.org/format/#fetching-sorting

        """
        person1 = self.Person(name='foo', age=99)
        person2 = self.Person(name='bar', age=99)
        person3 = self.Person(name='baz', age=80)
        person4 = self.Person(name='xyzzy', age=80)
        self.session.add_all([person1, person2, person3, person4])
        self.session.commit()
        # Sort by age, decreasing, then by name, increasing.
        query_string = {'sort': '-age,name'}
        response = self.app.get('/api/person', query_string=query_string)
        document = loads(response.data)
        people = document['data']
        p1, p2, p3, p4 = (p['attributes'] for p in people)
        assert p1['age'] == p2['age'] >= p3['age'] == p4['age']
        assert p1['name'] <= p2['name']
        assert p3['name'] <= p4['name']

    def test_sort_relationship_attributes(self):
        """Tests that the client can sort by relationship attributes.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: http://jsonapi.org/format/#fetching-sorting

        """
        person1 = self.Person(age=20)
        person2 = self.Person(age=10)
        person3 = self.Person(age=30)
        article1 = self.Article(id=1, author=person1)
        article2 = self.Article(id=2, author=person2)
        article3 = self.Article(id=3, author=person3)
        self.session.add_all([person1, person2, person3, article1, article2,
                              article3])
        self.session.commit()
        query_string = {'sort': 'author.age'}
        response = self.app.get('/api/article', query_string=query_string)
        document = loads(response.data)
        articles = document['data']
        assert ['2', '1', '3'] == [c['id'] for c in articles]

    def test_sorting_relationship(self):
        """Tests for sorting relationship objects when requesting
        information from a to-many relationship endpoint.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: http://jsonapi.org/format/#fetching-sorting

        """
        person = self.Person(id=1)
        articles = [self.Article(id=i, title=str(i)) for i in range(5)]
        self.session.add(person)
        self.session.add_all(articles)
        self.session.commit()
        query_string = dict(sort='-title')
        response = self.app.get('/api/person/1/relationships/articles',
                                query_string=query_string)
        document = loads(response.data)
        articles = document['data']
        articleids = [article['id'] for article in articles]
        assert ['4', '3', '2', '1', '0'] == articleids


class TestPagination(ManagerTestBase):
    """Tests for pagination links in fetched documents.

    For more information, see the `Pagination`_ section of the JSON API
    specification.

    .. _Pagination: http://jsonapi.org/format/#fetching-pagination

    """

    def setUp(self):
        super(TestPagination, self).setUp()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Person)

    def test_top_level_pagination_link(self):
        """Tests that there are top-level pagination links by default.

        For more information, see the `Top Level`_ section of the JSON
        API specification.

        .. _Top Level: http://jsonapi.org/format/#document-top-level

        """
        response = self.app.get('/api/person')
        document = loads(response.data)
        links = document['links']
        assert 'first' in links
        assert 'last' in links
        assert 'prev' in links
        assert 'next' in links

    def test_no_client_parameters(self):
        """Tests that a request without pagination query parameters returns the
        first page of the collection.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: http://jsonapi.org/format/#fetching-pagination

        """
        people = [self.Person() for i in range(25)]
        self.session.add_all(people)
        self.session.commit()
        response = self.app.get('/api/person')
        document = loads(response.data)
        pagination = document['links']
        assert '/api/person?' in pagination['first']
        assert 'page[number]=1' in pagination['first']
        assert '/api/person?' in pagination['last']
        assert 'page[number]=3' in pagination['last']
        assert pagination['prev'] is None
        assert '/api/person?' in pagination['next']
        assert 'page[number]=2' in pagination['next']
        assert len(document['data']) == 10

    def test_client_page_and_size(self):
        """Tests that a request that specifies both page number and page size
        returns the correct page of the collection.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: http://jsonapi.org/format/#fetching-pagination

        """
        people = [self.Person() for i in range(25)]
        self.session.add_all(people)
        self.session.commit()
        query_string = {'page[number]': 2, 'page[size]': 3}
        response = self.app.get('/api/person', query_string=query_string)
        document = loads(response.data)
        pagination = document['links']
        assert '/api/person?' in pagination['first']
        assert 'page[number]=1' in pagination['first']
        assert '/api/person?' in pagination['last']
        assert 'page[number]=9' in pagination['last']
        assert '/api/person?' in pagination['prev']
        assert 'page[number]=1' in pagination['prev']
        assert '/api/person?' in pagination['next']
        assert 'page[number]=3' in pagination['next']
        assert len(document['data']) == 3

    def test_client_number_only(self):
        """Tests that a request that specifies only the page number returns the
        correct page with the default page size.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: http://jsonapi.org/format/#fetching-pagination

        """
        people = [self.Person() for i in range(25)]
        self.session.add_all(people)
        self.session.commit()
        response = self.app.get('/api/person?page[number]=2')
        document = loads(response.data)
        pagination = document['links']
        assert '/api/person?' in pagination['first']
        assert 'page[number]=1' in pagination['first']
        assert '/api/person?' in pagination['last']
        assert 'page[number]=3' in pagination['last']
        assert '/api/person?' in pagination['prev']
        assert 'page[number]=1' in pagination['prev']
        assert '/api/person?' in pagination['next']
        assert 'page[number]=3' in pagination['next']
        assert len(document['data']) == 10

    def test_sorted_pagination(self):
        """Tests that pagination is consistent with sorting.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: http://jsonapi.org/format/#fetching-pagination

        """
        people = [self.Person() for i in range(40)]
        self.session.add_all(people)
        self.session.commit()
        response = self.app.get('/api/person?sort=-id&page[number]=2')
        document = loads(response.data)
        # In reverse order, the first page should have Person instances with
        # IDs 40 through 31, so the second page should have Person instances
        # with IDs 30 through 21.
        people = document['data']
        assert list(range(30, 20, -1)) == [int(p['id']) for p in people]
        # The pagination links should include not only the pagination query
        # parameters, but also the same sorting query parameters from the
        # client's original quest.
        pagination = document['links']
        assert '/api/person?' in pagination['first']
        assert 'page[number]=1' in pagination['first']
        assert 'sort=-id' in pagination['first']

        assert '/api/person?' in pagination['last']
        assert 'page[number]=4' in pagination['last']
        assert 'sort=-id' in pagination['last']

        assert '/api/person?' in pagination['prev']
        assert 'page[number]=1' in pagination['prev']
        assert 'sort=-id' in pagination['prev']

        assert '/api/person?' in pagination['next']
        assert 'page[number]=3' in pagination['next']
        assert 'sort=-id' in pagination['next']

    def test_client_size_only(self):
        """Tests that a request that specifies only the page size returns the
        first page with the requested page size.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: http://jsonapi.org/format/#fetching-pagination

        """
        people = [self.Person() for i in range(25)]
        self.session.add_all(people)
        self.session.commit()
        response = self.app.get('/api/person?page[size]=5')
        document = loads(response.data)
        pagination = document['links']
        assert '/api/person?' in pagination['first']
        assert 'page[number]=1' in pagination['first']
        assert '/api/person?' in pagination['last']
        assert 'page[number]=5' in pagination['last']
        assert pagination['prev'] is None
        assert '/api/person?' in pagination['next']
        assert 'page[number]=2' in pagination['next']
        assert len(document['data']) == 5

    def test_short_page(self):
        """Tests that a request that specifies the last page may get fewer
        resources than the page size.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: http://jsonapi.org/format/#fetching-pagination

        """
        people = [self.Person() for i in range(25)]
        self.session.add_all(people)
        self.session.commit()
        response = self.app.get('/api/person?page[number]=3')
        document = loads(response.data)
        pagination = document['links']
        assert '/api/person?' in pagination['first']
        assert 'page[number]=1' in pagination['first']
        assert '/api/person?' in pagination['last']
        assert 'page[number]=3' in pagination['last']
        assert '/api/person?' in pagination['prev']
        assert 'page[number]=2' in pagination['prev']
        assert pagination['next'] is None
        assert len(document['data']) == 5

    def test_server_page_size(self):
        """Tests for setting the default page size on the server side.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: http://jsonapi.org/format/#fetching-pagination

        """
        people = [self.Person() for i in range(25)]
        self.session.add_all(people)
        self.session.commit()
        self.manager.create_api(self.Person, url_prefix='/api2', page_size=5)
        response = self.app.get('/api2/person?page[number]=3')
        document = loads(response.data)
        pagination = document['links']
        assert '/api2/person?' in pagination['first']
        assert 'page[number]=1' in pagination['first']
        assert '/api2/person?' in pagination['last']
        assert 'page[number]=5' in pagination['last']
        assert '/api2/person?' in pagination['prev']
        assert 'page[number]=2' in pagination['prev']
        assert '/api2/person?' in pagination['next']
        assert 'page[number]=4' in pagination['next']
        assert len(document['data']) == 5

    def test_disable_pagination(self):
        """Tests for disabling default pagination on the server side.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: http://jsonapi.org/format/#fetching-pagination

        """
        people = [self.Person() for i in range(25)]
        self.session.add_all(people)
        self.session.commit()
        self.manager.create_api(self.Person, url_prefix='/api2', page_size=0)
        response = self.app.get('/api2/person')
        document = loads(response.data)
        pagination = document['links']
        assert 'first' not in pagination
        assert 'last' not in pagination
        assert 'prev' not in pagination
        assert 'next' not in pagination
        assert len(document['data']) == 25

    def test_disable_pagination_ignore_client(self):
        """Tests that disabling default pagination on the server side ignores
        client page number requests.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: http://jsonapi.org/format/#fetching-pagination

        """
        people = [self.Person() for i in range(25)]
        self.session.add_all(people)
        self.session.commit()
        self.manager.create_api(self.Person, url_prefix='/api2', page_size=0)
        response = self.app.get('/api2/person?page[number]=2')
        document = loads(response.data)
        pagination = document['links']
        assert 'first' not in pagination
        assert 'last' not in pagination
        assert 'prev' not in pagination
        assert 'next' not in pagination
        assert len(document['data']) == 25
        # TODO Should there be an error here?

    def test_max_page_size(self):
        """Tests that the client cannot exceed the maximum page size.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: http://jsonapi.org/format/#fetching-pagination

        """
        people = [self.Person() for i in range(25)]
        self.session.add_all(people)
        self.session.commit()
        self.manager.create_api(self.Person, url_prefix='/api2',
                                max_page_size=15)
        response = self.app.get('/api2/person?page[size]=20')
        assert response.status_code == 400
        # TODO check the error message here.

    def test_negative_page_size(self):
        """Tests that the client cannot specify a negative page size.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: http://jsonapi.org/format/#fetching-pagination

        """
        response = self.app.get('/api/person?page[size]=-1')
        assert response.status_code == 400
        # TODO check the error message here.

    def test_negative_page_number(self):
        """Tests that the client cannot specify a negative page number.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: http://jsonapi.org/format/#fetching-pagination

        """
        response = self.app.get('/api/person?page[number]=-1')
        assert response.status_code == 400
        # TODO check the error message here.

    def test_headers(self):
        """Tests that paginated requests come with ``Link`` headers.

        (This is not part of the JSON API standard, but should live with the
        other pagination test methods anyway.)

        """
        people = [self.Person() for i in range(25)]
        self.session.add_all(people)
        self.session.commit()
        response = self.app.get('/api/person?page[number]=4&page[size]=3')
        links = response.headers['Link'].split(',')
        assert any(all(('/api/person?' in l, 'page[number]=1' in l,
                        'page[size]=3' in l, 'rel="first"' in l))
                   for l in links)
        assert any(all(('/api/person?' in l, 'page[number]=9' in l,
                        'page[size]=3' in l, 'rel="last"' in l))
                   for l in links)
        assert any(all(('/api/person?' in l, 'page[number]=3' in l,
                        'page[size]=3' in l, 'rel="prev"' in l))
                   for l in links)
        assert any(all(('/api/person?' in l, 'page[number]=5' in l,
                        'page[size]=3' in l, 'rel="next"' in l))
                   for l in links)


class TestCreatingResources(ManagerTestBase):
    """Tests corresponding to the `Creating Resources`_ section of the JSON API
    specification.

    .. _Creating Resources: http://jsonapi.org/format/#crud-creating

    """

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        and :class:`TestSupport.Article` models.

        """
        super(TestCreatingResources, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(GUID, primary_key=True)

        class Comment(self.Base):
            __tablename__ = 'comment'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)
            age = Column(Integer)
            comments = relationship('Comment')

        self.Article = Article
        self.Comment = Comment
        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Person, methods=['POST'])
        self.manager.create_api(Article, methods=['POST'],
                                allow_client_generated_ids=True)
        self.manager.create_api(Comment)

    def test_sparse_fieldsets_post(self):
        """Tests for restricting which fields are returned in a
        :http:method:`post` request.

        This unit test lives in this class instead of the
        :class:`TestFetchingData` class because in that class, APIs do
        not allow :http:method:`post` requests.

        For more information, see the `Sparse Fieldsets`_ section
        of the JSON API specification.

        .. _Sparse Fieldsets: http://jsonapi.org/format/#fetching-sparse-fieldsets
        """
        data = {'data':
                    {'type': 'person',
                     'attributes':
                         {'name': 'foo',
                          'age': 99}
                     }
                }
        query_string = {'fields[person]': 'name'}
        response = self.app.post('/api/person', data=dumps(data),
                                 query_string=query_string)
        document = loads(response.data)
        person = document['data']
        # ID and type must always be included.
        assert ['attributes', 'id', 'type'] == sorted(person)
        assert ['name'] == sorted(person['attributes'])

    def test_include_post(self):
        """Tests for including related resources on a
        :http:method:`post` request.

        This unit test lives in this class instead of the
        :class:`TestFetchingData` class because in that class, APIs do
        not allow :http:method:`post` requests.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        comment = self.Comment(id=1)
        self.session.add(comment)
        self.session.commit()
        data = {'data':
                    {'type': 'person',
                     'relationships':
                         {'comments':
                              {'data':
                                   [{'type': 'comment', 'id': 1}]
                               }
                          }
                     }
                }
        query_string = dict(include='comments')
        response = self.app.post('/api/person', data=dumps(data),
                                 query_string=query_string)
        assert response.status_code == 201
        document = loads(response.data)
        included = document['included']
        assert len(included) == 1
        comment = included[0]
        assert comment['type'] == 'comment'
        assert comment['id'] == '1'

    def test_create(self):
        """Tests that the client can create a single resource.

        For more information, see the `Creating Resources`_ section of the JSON
        API specification.

        .. _Creating Resources: http://jsonapi.org/format/#crud-creating

        """
        data = dict(data=dict(type='person', name='foo'))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 201
        location = response.headers['Location']
        # TODO Technically, this test shouldn't know beforehand where the
        # location of the created object will be. We are testing implementation
        # here, assuming that the implementation of the server creates a new
        # Person object with ID 1, which is bad style.
        assert location.endswith('/api/person/1')
        document = loads(response.data)
        person = document['data']
        assert person['type'] == 'person'
        assert person['id'] == '1'
        assert person['attributes']['name'] == 'foo'
        # # No self link will exist because no GET endpoint was created.
        # assert person['links']['self'] == location

    def test_without_type(self):
        """Tests for an error response if the client fails to specify the type
        of the object to create.

        For more information, see the `Creating Resources`_ section of the JSON
        API specification.

        .. _Creating Resources: http://jsonapi.org/format/#crud-creating

        """
        data = dict(data=dict(name='foo'))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 400
        # TODO test for error details (for example, a message specifying that
        # type is missing)

    def test_client_generated_id(self):
        """Tests that the client can specify a UUID to become the ID of the
        created object.

        For more information, see the `Client-Generated IDs`_ section of the
        JSON API specification.

        .. _Client-Generated IDs: http://jsonapi.org/format/#crud-creating-client-ids

        """
        generated_id = uuid.uuid1()
        data = dict(data=dict(type='article', id=generated_id))
        response = self.app.post('/api/article', data=dumps(data))
        # Our server always responds with 201 when a client-generated ID is
        # specified. It does not return a 204.
        #
        # TODO should we reverse that and only return 204?
        assert response.status_code == 201
        document = loads(response.data)
        article = document['data']
        assert article['type'] == 'article'
        assert article['id'] == str(generated_id)

    def test_client_generated_id_forbidden(self):
        """Tests that the client can specify a UUID to become the ID of the
        created object.

        For more information, see the `Client-Generated IDs`_ section of the
        JSON API specification.

        .. _Client-Generated IDs: http://jsonapi.org/format/#crud-creating-client-ids

        """
        self.manager.create_api(self.Article, url_prefix='/api2',
                                methods=['POST'])
        data = dict(data=dict(type='article', id=uuid.uuid1()))
        response = self.app.post('/api2/article', data=dumps(data))
        assert response.status_code == 403
        # TODO test for error details (for example, a message specifying that
        # client-generated IDs are not allowed).

    def test_type_conflict(self):
        """Tests that if a client specifies a type that does not match the
        endpoint, a :http:status:`409` is returned.

        For more information, see the `409 Conflict`_ section of the JSON API
        specification.

        .. _409 Conflict: http://jsonapi.org/format/#crud-creating-responses-409

        """

        data = dict(data=dict(type='bogustype', name='foo'))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 409
        # TODO test for error details (for example, a message specifying that
        # client-generated IDs are not allowed).

    def test_id_conflict(self):
        """Tests that if a client specifies a client-generated ID that already
        exists, a :http:status:`409` is returned.

        For more information, see the `409 Conflict`_ section of the JSON API
        specification.

        .. _409 Conflict: http://jsonapi.org/format/#crud-creating-responses-409

        """
        generated_id = uuid.uuid1()
        self.session.add(self.Article(id=generated_id))
        self.session.commit()
        data = dict(data=dict(type='article', id=generated_id))
        response = self.app.post('/api/article', data=dumps(data))
        assert response.status_code == 409
        # TODO test for error details (for example, a message specifying that
        # client-generated IDs are not allowed).


class TestUpdatingResources(ManagerTestBase):
    """Tests corresponding to the `Updating Resources`_ section of the JSON API
    specification.

    .. _Updating Resources: http://jsonapi.org/format/#crud-updating

    """

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        and :class:`TestSupport.Article` models.

        """
        super(TestUpdatingResources, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode, unique=True)
            age = Column(Integer)
            articles = relationship('Article')

        class Tag(self.Base):
            __tablename__ = 'tag'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)
            updated_at = Column(DateTime, server_default=func.now(),
                                onupdate=func.current_timestamp())

        self.Article = Article
        self.Person = Person
        self.Tag = Tag
        self.Base.metadata.create_all()
        self.manager.create_api(Article, methods=['PATCH'])
        self.manager.create_api(Person, methods=['PATCH'])
        self.manager.create_api(Tag, methods=['GET', 'PATCH'])

    def test_update(self):
        """Tests that the client can update a resource's attributes.

        For more information, see the `Updating a Resource's Attributes`_
        section of the JSON API specification.

        .. _Updating a Resource's Attributes: http://jsonapi.org/format/#crud-updating-resource-attributes

        """
        person = self.Person(id=1, name='foo', age=10)
        self.session.add(person)
        self.session.commit()
        data = dict(data=dict(type='person', id='1',
                              attributes=dict(name='bar')))
        response = self.app.patch('/api/person/1', data=dumps(data))
        assert response.status_code == 204
        assert person.id == 1
        assert person.name == 'bar'
        assert person.age == 10

    def test_to_one(self):
        """Tests that the client can update a resource's to-one relationships.

        For more information, see the `Updating a Resource's To-One Relationships`_
        section of the JSON API specification.

        .. _Updating a Resource's To-One Relationships: http://jsonapi.org/format/#crud-updating-resource-to-one-relationships

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        article = self.Article(id=1)
        person1.articles = [article]
        self.session.add_all([person1, person2, article])
        self.session.commit()
        # Change the author of the article from person 1 to person 2.
        data = {
            'data': {
                'type': 'article',
                'id': '1',
                'relationships': {
                    'author': {
                        'data': {'type': 'person', 'id': '2'}
                    }
                }
            }
        }
        response = self.app.patch('/api/article/1', data=dumps(data))
        assert response.status_code == 204
        assert article.author is person2

    def test_remove_to_one(self):
        """Tests that the client can remove a resource's to-one relationship.

        For more information, see the `Updating a Resource's To-One Relationships`_
        section of the JSON API specification.

        .. _Updating a Resource's To-One Relationships: http://jsonapi.org/format/#crud-updating-resource-to-one-relationships

        """
        person = self.Person(id=1)
        article = self.Article()
        person.articles = [article]
        self.session.add_all([person, article])
        self.session.commit()
        # Change the author of the article to None.
        data = {
            'data': {
                'type': 'article',
                'id': '1',
                'relationships': {'author': {'data': None}}
            }
        }
        response = self.app.patch('/api/article/1', data=dumps(data))
        assert response.status_code == 204
        assert article.author is None

    def test_to_many(self):
        """Tests that the client can update a resource's to-many relationships.

        For more information, see the `Updating a Resource's To-Many Relationships`_
        section of the JSON API specification.

        .. _Updating a Resource's To-Many Relationships: http://jsonapi.org/format/#crud-updating-resource-to-many-relationships

        """
        person = self.Person(id=1)
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        self.session.add_all([person, article1, article2])
        self.session.commit()
        self.manager.create_api(self.Person, methods=['PATCH'],
                                url_prefix='/api2',
                                allow_to_many_replacement=True)
        data = {
            'data': {
                'type': 'person',
                'id': '1',
                'relationships': {
                    'articles': {
                        'data': [
                            {'type': 'article', 'id': '1'},
                            {'type': 'article', 'id': '2'}
                        ]
                    }
                }
            }
        }
        response = self.app.patch('/api2/person/1', data=dumps(data))
        assert response.status_code == 204
        assert set(person.articles) == {article1, article2}

    def test_to_many_clear(self):
        """Tests that the client can clear a resource's to-many relationships.

        For more information, see the `Updating a Resource's To-Many Relationships`_
        section of the JSON API specification.

        .. _Updating a Resource's To-Many Relationships: http://jsonapi.org/format/#crud-updating-resource-to-many-relationships

        """
        person = self.Person(id=1)
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        person.articles = [article1, article2]
        self.session.add_all([person, article1, article2])
        self.session.commit()
        self.manager.create_api(self.Person, methods=['PATCH'],
                                url_prefix='/api2',
                                allow_to_many_replacement=True)
        data = {
            'data': {
                'type': 'person',
                'id': '1',
                'relationships': {
                    'articles': {
                        'data': []
                    }
                }
            }
        }
        response = self.app.patch('/api2/person/1', data=dumps(data))
        assert response.status_code == 204
        assert person.articles == []

    def test_to_many_forbidden(self):
        """Tests that the client receives a :http:status:`403` if the server
        has been configured to disallow full replacement of a to-many
        relationship.

        For more information, see the `Updating a Resource's To-Many Relationships`_
        section of the JSON API specification.

        .. _Updating a Resource's To-Many Relationships: http://jsonapi.org/format/#crud-updating-resource-to-many-relationships

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = {
            'data': {
                'type': 'person',
                'id': '1',
                'relationships': {'articles': {'data': []}}
            }
        }
        response = self.app.patch('/api/person/1', data=dumps(data))
        assert response.status_code == 403

    def test_other_modifications(self):
        """Tests that if an update causes additional changes in the resource in
        ways other than those specified by the client, the response has status
        :http:status:`200` and includes the updated resource.

        For more information, see the `200 OK`_ section of the JSON API
        specification.

        .. _200 OK: http://jsonapi.org/format/#crud-updating-responses-200

        """
        tag = self.Tag(id=1)
        self.session.add(tag)
        self.session.commit()
        data = dict(data=dict(type='tag', id='1', attributes=dict(name='foo')))
        response = self.app.patch('/api/tag/1', data=dumps(data))
        assert response.status_code == 200
        document = loads(response.data)
        tag1 = document['data']
        response = self.app.get('/api/tag/1')
        document = loads(response.data)
        tag2 = document['data']
        assert tag1 == tag2

    def test_nonexistent(self):
        """Tests that an attempt to update a nonexistent resource causes a
        :http:status:`404` response.

        For more information, see the `404 Not Found`_ section of the JSON API
        specification.

        .. _404 Not Found: http://jsonapi.org/format/#crud-updating-responses-404

        """
        data = dict(data=dict(type='person', id='1'))
        response = self.app.patch('/api/person/1', data=dumps(data))
        assert response.status_code == 404

    def test_nonexistent_relationship(self):
        """Tests that an attempt to update a nonexistent resource causes a
        :http:status:`404` response.

        For more information, see the `404 Not Found`_ section of the JSON API
        specification.

        .. _404 Not Found: http://jsonapi.org/format/#crud-updating-responses-404

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        self.manager.create_api(self.Person, methods=['PATCH'],
                                url_prefix='/api2',
                                allow_to_many_replacement=True)
        data = {
            'data': {
                'type': 'person',
                'id': '1',
                'relationships': {
                    'articles': {'data': [{'type': 'article', 'id': '1'}]}
                }
            }
        }
        response = self.app.patch('/api2/person/1', data=dumps(data))
        assert response.status_code == 404
        # TODO test for error details

    def test_conflicting_attributes(self):
        """Tests that an attempt to update a resource with a non-unique
        attribute value where uniqueness is required causes a
        :http:status:`409` response.

        For more information, see the `409 Conflict`_ section of the JSON API
        specification.

        .. _409 Conflict: http://jsonapi.org/format/#crud-updating-responses-409

        """
        person1 = self.Person(id=1, name='foo')
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()
        data = dict(data=dict(type='person', id='2',
                              attributes=dict(name='foo')))
        response = self.app.patch('/api/person/2', data=dumps(data))
        assert response.status_code == 409
        # TODO test for error details

    def test_conflicting_type(self):
        """Tests that an attempt to update a resource with the wrong type
        causes a :http:status:`409` response.

        For more information, see the `409 Conflict`_ section of the JSON API
        specification.

        .. _409 Conflict: http://jsonapi.org/format/#crud-updating-responses-409

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = dict(data=dict(type='bogus', id='1'))
        response = self.app.patch('/api/person/1', data=dumps(data))
        assert response.status_code == 409
        # TODO test for error details

    def test_conflicting_id(self):
        """Tests that an attempt to update a resource with the wrong ID causes
        a :http:status:`409` response.

        For more information, see the `409 Conflict`_ section of the JSON API
        specification.

        .. _409 Conflict: http://jsonapi.org/format/#crud-updating-responses-409

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = dict(data=dict(type='person', id='bogus'))
        response = self.app.patch('/api/person/1', data=dumps(data))
        assert response.status_code == 409
        # TODO test for error details


class TestUpdatingRelationships(ManagerTestBase):
    """Tests corresponding to the `Updating Relationships`_ section of the JSON
    API specification.

    .. _Updating Relationships: http://jsonapi.org/format/#crud-updating-relationships

    """

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        and :class:`TestSupport.Article` models.

        """
        super(TestUpdatingRelationships, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            articles = relationship('Article')

        self.Article = Article
        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(self.Person, methods=['PATCH'])
        self.manager.create_api(self.Article, methods=['PATCH'])

    def test_to_one(self):
        """Tests for updating a to-one relationship via a :http:method:`patch`
        request to a relationship URL.

        For more information, see the `Updating To-One Relationships`_ section
        of the JSON API specification.

        .. _Updating To-One Relationships: http://jsonapi.org/format/#crud-updating-to-one-relationships

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        article = self.Article(id=1)
        article.author = person1
        self.session.add_all([person1, person2, article])
        self.session.commit()
        data = dict(data=dict(type='person', id='2'))
        response = self.app.patch('/api/article/1/links/author',
                                  data=dumps(data))
        assert response.status_code == 204
        assert article.author is person2

    def test_remove_to_one(self):
        """Tests for removing a to-one relationship via a :http:method:`patch`
        request to a relationship URL.

        For more information, see the `Updating To-One Relationships`_ section
        of the JSON API specification.

        .. _Updating To-One Relationships: http://jsonapi.org/format/#crud-updating-to-one-relationships

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        article = self.Article(id=1)
        article.author = person1
        self.session.add_all([person1, person2, article])
        self.session.commit()
        data = dict(data=None)
        response = self.app.patch('/api/article/1/links/author',
                                  data=dumps(data))
        assert response.status_code == 204
        assert article.author is None

    def test_to_many(self):
        """Tests for replacing a to-many relationship via a
        :http:method:`patch` request to a relationship URL.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: http://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        person = self.Person(id=1)
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        self.session.add_all([person, article1, article2])
        self.session.commit()
        self.manager.create_api(self.Person, methods=['PATCH'],
                                url_prefix='/api2',
                                allow_to_many_replacement=True)
        data = {'data': [{'type': 'article', 'id': '1'},
                         {'type': 'article', 'id': '2'}]}
        response = self.app.patch('/api2/person/1/links/articles',
                                  data=dumps(data))
        assert response.status_code == 204
        assert set(person.articles) == {article1, article2}

    def test_to_many_not_found(self):
        """Tests that an attempt to replace a to-many relationship with a
        related resource that does not exist yields an error response.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: http://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        self.session.add_all([person, article])
        self.session.commit()
        self.manager.create_api(self.Person, methods=['PATCH'],
                                url_prefix='/api2',
                                allow_to_many_replacement=True)
        data = {'data': [{'type': 'article', 'id': '1'},
                         {'type': 'article', 'id': '2'}]}
        response = self.app.patch('/api2/person/1/links/articles',
                                  data=dumps(data))
        assert response.status_code == 404
        # TODO test error messages

    def test_to_many_forbidden(self):
        """Tests that full replacement of a to-many relationship is forbidden
        by the server configuration, then the response is :http:status:`403`.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: http://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = {'data': []}
        response = self.app.patch('/api/person/1/links/articles',
                                  data=dumps(data))
        assert response.status_code == 403
        # TODO test error messages

    def test_to_many_append(self):
        """Tests for appending to a to-many relationship via a
        :http:method:`post` request to a relationship URL.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: http://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        person = self.Person(id=1)
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        self.session.add_all([person, article1, article2])
        self.session.commit()
        data = {'data': [{'type': 'article', 'id': '1'},
                         {'type': 'article', 'id': '2'}]}
        response = self.app.post('/api/person/1/links/articles',
                                 data=dumps(data))
        assert response.status_code == 204
        assert set(person.articles) == {article1, article2}

    def test_to_many_preexisting(self):
        """Tests for attempting to append an element that already exists in a
        to-many relationship via a :http:method:`post` request to a
        relationship URL.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: http://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        person.articles = [article]
        self.session.add_all([person, article])
        self.session.commit()
        data = {'data': [{'type': 'article', 'id': '1'}]}
        response = self.app.post('/api/person/1/links/articles',
                                 data=dumps(data))
        assert response.status_code == 204
        assert person.articles == [article]

    def test_to_many_delete(self):
        """Tests for deleting from a to-many relationship via a
        :http:method:`delete` request to a relationship URL.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: http://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        person = self.Person(id=1)
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        person.articles = [article1, article2]
        self.session.add_all([person, article1, article2])
        self.session.commit()
        self.manager.create_api(self.Person, methods=['PATCH'],
                                url_prefix='/api2',
                                allow_delete_from_to_many_relationships=True)
        data = {'data': [{'type': 'article', 'id': '1'}]}
        response = self.app.delete('/api2/person/1/links/articles',
                                   data=dumps(data))
        assert response.status_code == 204
        assert person.articles == [article2]

    def test_to_many_delete_nonexistent(self):
        """Tests for deleting a nonexistent member from a to-many relationship
        via a :http:method:`delete` request to a relationship URL.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: http://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        person = self.Person(id=1)
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        person.articles = [article1]
        self.session.add_all([person, article1, article2])
        self.session.commit()
        self.manager.create_api(self.Person, methods=['PATCH'],
                                url_prefix='/api2',
                                allow_delete_from_to_many_relationships=True)
        data = {'data': [{'type': 'article', 'id': '2'}]}
        response = self.app.delete('/api2/person/1/links/articles',
                                   data=dumps(data))
        assert response.status_code == 204
        assert person.articles == [article1]

    def test_to_many_delete_forbidden(self):
        """Tests that attempting to delete from a to-many relationship via a
        :http:method:`delete` request to a relationship URL when the server has
        disallowed it yields a :http:status:`409` response.

        For more information, see the `Updating To-Many Relationships`_ section
        of the JSON API specification.

        .. _Updating To-Many Relationships: http://jsonapi.org/format/#crud-updating-to-many-relationships

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        person.articles = [article]
        self.session.add_all([person, article])
        self.session.commit()
        data = {'data': [{'type': 'article', 'id': '1'}]}
        response = self.app.delete('/api/person/1/links/articles',
                                   data=dumps(data))
        assert response.status_code == 403
        assert person.articles == [article]


class TestDeletingResources(ManagerTestBase):
    """Tests corresponding to the `Deleting Resources`_ section of the JSON API
    specification.

    .. _Deleting Resources: http://jsonapi.org/format/#crud-deleting

    """

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        class.

        """
        # create the database
        super(TestDeletingResources, self).setUp()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(self.Person, methods=['DELETE'])

    def test_delete(self):
        """Tests for deleting a resource.

        For more information, see the `Deleting Resources`_ section of the JSON
        API specification.

        .. _Deleting Resources: http://jsonapi.org/format/#crud-deleting

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.delete('/api/person/1')
        assert response.status_code == 204
        assert self.session.query(self.Person).count() == 0

    def test_delete_nonexistent(self):
        """Tests that deleting a nonexistent resource causes a
        :http:status:`404`.

        For more information, see the `404 Not Found`_ section of the JSON API
        specification.

        .. _404 Not Found: http://jsonapi.org/format/#crud-deleting-responses-404

        """
        response = self.app.delete('/api/person/1')
        assert response.status_code == 404
