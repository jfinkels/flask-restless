# test_updating_resources.py - tests updating resources according to JSON API
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
"""Unit tests for updating resources according to the JSON API
specification.

The tests in this module correspond to the `Updating Resources`_ section
of the JSON API specification.

.. _Updating Resources: http://jsonapi.org/format/#crud-updating

"""
from operator import attrgetter

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import func
from sqlalchemy import Integer
from sqlalchemy import Unicode
from sqlalchemy.orm import relationship

from ..helpers import dumps
from ..helpers import loads
from ..helpers import ManagerTestBase


class TestUpdatingResources(ManagerTestBase):
    """Tests corresponding to the `Updating Resources`_ section of the JSON API
    specification.

    .. _Updating Resources: http://jsonapi.org/format/#crud-updating

    """

    def setup(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        and :class:`TestSupport.Article` models.

        """
        super(TestUpdatingResources, self).setup()

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
        person = self.Person(id=1, name=u'foo', age=10)
        self.session.add(person)
        self.session.commit()
        data = dict(data=dict(type='person', id='1',
                              attributes=dict(name=u'bar')))
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
        articles = sorted(person.articles, key=attrgetter('id'))
        assert [article1, article2] == articles

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
        data = {'data':
                {'type': 'tag',
                 'id': '1',
                 'attributes': {'name': u'foo'}
                }
        }
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
        person1 = self.Person(id=1, name=u'foo')
        person2 = self.Person(id=2)
        self.session.add_all([person1, person2])
        self.session.commit()
        data = dict(data=dict(type='person', id='2',
                              attributes=dict(name=u'foo')))
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
