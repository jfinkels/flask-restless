# test_document_structure.py - tests JSON API document structure
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
"""Tests that Flask-Restless responds to the client with correctly
structured JSON documents.

The tests in this module correspond to the `Document Structure`_ section
of the JSON API specification.

.. _Document Structure: http://jsonapi.org/format/#document-structure

"""
import string
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy.orm import relationship

from ..helpers import dumps
from ..helpers import loads
from ..helpers import ManagerTestBase


class TestDocumentStructure(ManagerTestBase):
    """Tests corresponding to the `Document Structure`_ section of the JSON API
    specification.

    .. _Document Structure: http://jsonapi.org/format/#document-structure

    """

    def setup(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        and :class:`TestSupport.Article` models.

        """
        super(TestDocumentStructure, self).setup()

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
        """Tests that a relationship object correctly identifies its own
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
        assert relationship_url.endswith('/api/article/1/relationships/author')

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

    # TODO Test this for every possible type of request.
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
