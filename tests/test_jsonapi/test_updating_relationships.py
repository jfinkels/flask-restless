# test_updating_relationships.py - tests updating relationships via JSON API
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
"""Unit tests for requests that update relationships.

The tests in this module correspond to the `Updating Relationships`_
section of the JSON API specification.

.. _Updating Relationships: http://jsonapi.org/format/#crud-updating-relationships

"""
from operator import attrgetter

from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy.orm import relationship

from ..helpers import dumps
from ..helpers import ManagerTestBase


class TestUpdatingRelationships(ManagerTestBase):
    """Tests corresponding to the `Updating Relationships`_ section of the JSON
    API specification.

    .. _Updating Relationships: http://jsonapi.org/format/#crud-updating-relationships

    """

    def setup(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        and :class:`TestSupport.Article` models.

        """
        super(TestUpdatingRelationships, self).setup()

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
        response = self.app.patch('/api/article/1/relationships/author',
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
        response = self.app.patch('/api/article/1/relationships/author',
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
        response = self.app.patch('/api2/person/1/relationships/articles',
                                  data=dumps(data))
        assert response.status_code == 204
        articles = sorted(person.articles, key=attrgetter('id'))
        assert [article1, article2] == articles

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
        response = self.app.patch('/api2/person/1/relationships/articles',
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
        response = self.app.patch('/api/person/1/relationships/articles',
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
        response = self.app.post('/api/person/1/relationships/articles',
                                 data=dumps(data))
        assert response.status_code == 204
        articles = sorted(person.articles, key=attrgetter('id'))
        assert [article1, article2] == articles

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
        response = self.app.post('/api/person/1/relationships/articles',
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
        response = self.app.delete('/api2/person/1/relationships/articles',
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
        response = self.app.delete('/api2/person/1/relationships/articles',
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
        response = self.app.delete('/api/person/1/relationships/articles',
                                   data=dumps(data))
        assert response.status_code == 403
        assert person.articles == [article]
