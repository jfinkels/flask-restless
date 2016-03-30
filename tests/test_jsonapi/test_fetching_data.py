# test_fetching_data.py - tests fetching data according to JSON API
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
"""Unit tests for requests that fetch resources and relationships.

The tests in this module correspond to the `Fetching Data`_ section of
the JSON API specification.

.. _Fetching Data: http://jsonapi.org/format/#fetching

"""
from sqlalchemy import Column
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Unicode
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship

from ..helpers import loads
from ..helpers import ManagerTestBase


class TestFetchingData(ManagerTestBase):
    """Tests corresponding to the `Fetching Data`_ section of the JSON API
    specification.

    .. _Fetching Data: http://jsonapi.org/format/#fetching

    """

    def setup(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        and :class:`TestSupport.Article` models.

        """
        super(TestFetchingData, self).setup()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            title = Column(Unicode)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')

        class Comment(self.Base):
            __tablename__ = 'comment'
            id = Column(Integer, primary_key=True)
            article_id = Column(Integer, ForeignKey('article.id'))
            article = relationship(Article, backref=backref('comments'))

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)
            age = Column(Integer)
            other = Column(Float)
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
        comment3 = self.Comment(id=3)
        article.comments = [comment1, comment2]
        self.session.add_all([article, comment1, comment2, comment3])
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


class TestInclusion(ManagerTestBase):
    """Tests corresponding to the `Inclusion of Related Resources`_
    section of the JSON API specification.

    .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

    """

    def setup(self):
        super(TestInclusion, self).setup()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')

        class Comment(self.Base):
            __tablename__ = 'comment'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person', backref=backref('comments'))
            article_id = Column(Integer, ForeignKey('article.id'))
            article = relationship(Article, backref=backref('comments'))

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)
            articles = relationship('Article')

        self.Article = Article
        self.Comment = Comment
        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Article)
        self.manager.create_api(Comment)
        self.manager.create_api(Person)

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

    def test_include(self):
        """Tests that the client can specify which linked relations to
        include in a compound document.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        person = self.Person(id=1, name=u'foo')
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
        person = self.Person(id=1, name=u'foo')
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


class TestSparseFieldsets(ManagerTestBase):
    """Tests corresponding to the `Sparse Fieldsets`_ section of the
    JSON API specification.

    .. _Sparse Fieldsets: http://jsonapi.org/format/#fetching-sparse-fieldsets

    """

    def setup(self):
        super(TestSparseFieldsets, self).setup()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            title = Column(Unicode)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)
            age = Column(Integer)
            articles = relationship('Article')

        self.Article = Article
        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Article)
        self.manager.create_api(Person)

    def test_sparse_fieldsets(self):
        """Tests that the client can specify which fields to return in the
        response of a fetch request for a single object.

        For more information, see the `Sparse Fieldsets`_ section
        of the JSON API specification.

        .. _Sparse Fieldsets: http://jsonapi.org/format/#fetching-sparse-fieldsets

        """
        person = self.Person(id=1, name=u'foo', age=99)
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
        person = self.Person(id=1, name=u'foo', age=99)
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
        person1 = self.Person(id=1, name=u'foo', age=99)
        person2 = self.Person(id=2, name=u'bar', age=80)
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
        article = self.Article(id=1, title=u'bar')
        person = self.Person(id=1, name=u'foo', age=99, articles=[article])
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


class TestSorting(ManagerTestBase):
    """Tests corresponding to the `Sorting`_ section of the JSON API
    specification.

    .. _Sorting: http://jsonapi.org/format/#fetching-sorting

    """

    def setup(self):
        super(TestSorting, self).setup()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            title = Column(Unicode)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)
            age = Column(Integer)
            articles = relationship('Article')

        self.Article = Article
        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Article)
        self.manager.create_api(Person)

    def test_sort_increasing(self):
        """Tests that the client can specify the fields on which to sort
        the response in increasing order.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: http://jsonapi.org/format/#fetching-sorting

        """
        person1 = self.Person(name=u'foo', age=20)
        person2 = self.Person(name=u'bar', age=10)
        person3 = self.Person(name=u'baz', age=30)
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
        person1 = self.Person(name=u'foo', age=20)
        person2 = self.Person(name=u'bar', age=10)
        person3 = self.Person(name=u'baz', age=30)
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
        person1 = self.Person(name=u'foo', age=99)
        person2 = self.Person(name=u'bar', age=99)
        person3 = self.Person(name=u'baz', age=80)
        person4 = self.Person(name=u'xyzzy', age=80)
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


    def test_sort_multiple_relationship_attributes(self):
        """Tests that the client can sort by multiple relationship
        attributes.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: http://jsonapi.org/format/#fetching-sorting

        """
        person1 = self.Person(age=2, name=u'd')
        person2 = self.Person(age=1, name=u'b')
        person3 = self.Person(age=1, name=u'a')
        person4 = self.Person(age=2, name=u'c')
        people = [person1, person2, person3, person4]
        articles = [self.Article(id=i, author=person)
                    for i, person in enumerate(people, start=1)]
        self.session.add_all(people + articles)
        self.session.commit()
        query_string = {'sort': 'author.age,author.name'}
        response = self.app.get('/api/article', query_string=query_string)
        document = loads(response.data)
        articles = document['data']
        assert ['3', '2', '4', '1'] == [c['id'] for c in articles]

    def test_sorting_relationship(self):
        """Tests for sorting relationship objects when requesting
        information from a to-many relationship endpoint.

        For more information, see the `Sorting`_ section of the JSON API
        specification.

        .. _Sorting: http://jsonapi.org/format/#fetching-sorting

        """
        person = self.Person(id=1)
        # In Python 3, the `unicode` class doesn't exist.
        try:
            to_string = unicode
        except NameError:
            to_string = str
        articles = [self.Article(id=i, title=to_string(i), author=person) for i in range(5)]
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

    def setup(self):
        super(TestPagination, self).setup()

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
        query_string = {'page[number]': 2}
        response = self.app.get('/api/person', query_string=query_string)
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
        query_string = {'sort': '-id', 'page[number]': 2}
        response = self.app.get('/api/person', query_string=query_string)
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
        query_string = {'page[size]': 5}
        response = self.app.get('/api/person', query_string=query_string)
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
        query_string = {'page[number]': 3}
        response = self.app.get('/api/person', query_string=query_string)
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
        query_string = {'page[number]': 3}
        response = self.app.get('/api2/person', query_string=query_string)
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
        query_string = {'page[number]': 2}
        response = self.app.get('/api2/person', query_string=query_string)
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
        query_string = {'page[size]': 20}
        response = self.app.get('/api2/person', query_string=query_string)
        assert response.status_code == 400
        # TODO check the error message here.

    def test_negative_page_size(self):
        """Tests that the client cannot specify a negative page size.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: http://jsonapi.org/format/#fetching-pagination

        """
        query_string = {'page[size]': -1}
        response = self.app.get('/api/person', query_string=query_string)
        assert response.status_code == 400
        # TODO check the error message here.

    def test_negative_page_number(self):
        """Tests that the client cannot specify a negative page number.

        For more information, see the `Pagination`_ section of the JSON API
        specification.

        .. _Pagination: http://jsonapi.org/format/#fetching-pagination

        """
        query_string = {'page[number]': -1}
        response = self.app.get('/api/person', query_string=query_string)
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
        query_string = {'page[number]': 4, 'page[size]': 3}
        response = self.app.get('/api/person', query_string=query_string)
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
