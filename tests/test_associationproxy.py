# -*- encoding: utf-8 -*-
# test_creating.py - unit tests for creating resources
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
"""Unit tests for interacting with association proxies.

The tests in this module use model attributes defined using `association
proxies`_.

.. _association proxies:
   http://docs.sqlalchemy.org/en/latest/orm/extensions/associationproxy.html

"""
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import ForeignKey
from sqlalchemy import Table
from sqlalchemy import Unicode
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship

from .helpers import dumps
from .helpers import loads
from .helpers import ManagerTestBase


class TestAssociationObject(ManagerTestBase):
    """Tests for association proxy with an association object."""

    def setUp(self):
        super(TestAssociationObject, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            articletags = relationship('ArticleTag',
                                       cascade='all, delete-orphan')
            tags = association_proxy('articletags', 'tag',
                                     creator=lambda tag: ArticleTag(tag=tag))

        class ArticleTag(self.Base):
            __tablename__ = 'articletag'
            article_id = Column(Integer, ForeignKey('article.id'),
                                primary_key=True)
            tag_id = Column(Integer, ForeignKey('tag.id'), primary_key=True)
            tag = relationship('Tag')

        class Tag(self.Base):
            __tablename__ = 'tag'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)

        self.Article = Article
        self.Tag = Tag
        self.Base.metadata.create_all()

    def test_fetching(self):
        """Test for fetching a resource that has a many-to-many relation that
        uses an association object with an association proxy.

        We serialize an association proxy that proxies a collection of
        model instances via an association object as a relationship.

        """
        self.manager.create_api(self.Article)
        self.manager.create_api(self.Tag)

        article = self.Article(id=1)
        tag = self.Tag(id=1)
        article.tags = [tag]
        self.session.add_all([article, tag])
        self.session.commit()

        response = self.app.get('/api/article/1')
        document = loads(response.data)
        article = document['data']
        tags = article['relationships']['tags']['data']
        self.assertEqual(['1'], sorted(tag['id'] for tag in tags))

    def test_creating(self):
        """Test for creating a resource with an assocation object."""
        self.manager.create_api(self.Article, methods=['POST'])
        self.manager.create_api(self.Tag)

        tag = self.Tag(id=1)
        self.session.add(tag)
        self.session.commit()

        data = {
            'data': {
                'type': 'article',
                'relationships': {
                    'tags': {
                        'data': [
                            {'type': 'tag', 'id': '1'},
                        ]
                    }
                }
            }
        }
        response = self.app.post('/api/article', data=dumps(data))
        self.assertEqual(response.status_code, 201)

        # Check that the response includes the resource identifiers for
        # the `tags` relationship.
        document = loads(response.data)
        article = document['data']
        tags = article['relationships']['tags']['data']
        self.assertEqual(tags, [{'type': 'tag', 'id': '1'}])

        # Check that the Article object has been created and has the
        # appropriate tags.
        self.assertEqual(self.session.query(self.Article).count(), 1)
        article = self.session.query(self.Article).first()
        self.assertEqual(article.tags, [tag])

    def test_updating(self):
        """Test for updating a to-many relationship via association proxy."""
        self.manager.create_api(self.Article, methods=['PATCH'],
                                allow_to_many_replacement=True)
        self.manager.create_api(self.Tag)

        article = self.Article(id=1)
        tag = self.Tag(id=1)
        self.session.add_all([article, tag])
        self.session.commit()

        data = {
            'data': {
                'type': 'article',
                'id': '1',
                'relationships': {
                    'tags': {
                        'data': [
                            {'type': 'tag', 'id': '1'},
                        ]
                    }
                }
            }
        }
        response = self.app.patch('/api/article/1', data=dumps(data))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(article.tags, [tag])

    def test_deleting(self):
        """Test for deleting a resource with a to-many relationship."""
        self.manager.create_api(self.Article, methods=['DELETE'])
        self.manager.create_api(self.Tag)

        article = self.Article(id=1)
        tag = self.Tag(id=1)
        article.tags = [tag]
        self.session.add_all([article, tag])
        self.session.commit()

        data = {
            'data': {
                'type': 'article',
                'id': '1',
            }
        }
        response = self.app.delete('/api/article/1', data=dumps(data))
        self.assertEqual(response.status_code, 204)
        self.assertEqual([tag], self.session.query(self.Tag).all())

    def test_fetch_relationships(self):
        """Test for fetching to-many relationship resource identifiers."""
        self.manager.create_api(self.Article)
        self.manager.create_api(self.Tag)

        article = self.Article(id=1)
        tag = self.Tag(id=1)
        article.tags = [tag]
        self.session.add_all([article, tag])
        self.session.commit()

        response = self.app.get('/api/article/1/relationships/tags')
        document = loads(response.data)
        tags = document['data']
        self.assertEqual(['1'], sorted(tag['id'] for tag in tags))

    def test_adding_to_relationship(self):
        """Test for adding to a to-many relationship via association proxy."""
        self.manager.create_api(self.Article, methods=['PATCH'])
        self.manager.create_api(self.Tag)

        article = self.Article(id=1)
        tag = self.Tag(id=1)
        self.session.add_all([article, tag])
        self.session.commit()

        data = {
            'data': [
                {'type': 'tag', 'id': '1'},
            ]
        }
        response = self.app.post('/api/article/1/relationships/tags',
                                 data=dumps(data))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(article.tags, [tag])

    def test_removing_from_relationship(self):
        """Test for removing from a to-many relationship."""
        self.manager.create_api(self.Article, methods=['PATCH'],
                                allow_delete_from_to_many_relationships=True)
        self.manager.create_api(self.Tag)

        article = self.Article(id=1)
        tag = self.Tag(id=1)
        article.tags = [tag]
        self.session.add_all([article, tag])
        self.session.commit()

        data = {
            'data': [
                {'type': 'tag', 'id': '1'},
            ]
        }
        response = self.app.delete('/api/article/1/relationships/tags',
                                   data=dumps(data))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(article.tags, [])

    def test_replacing_relationship(self):
        """Test for replacing a to-many relationship via association proxy."""
        self.manager.create_api(self.Article, methods=['PATCH'],
                                allow_to_many_replacement=True)
        self.manager.create_api(self.Tag)

        article = self.Article(id=1)
        tag1 = self.Tag(id=1)
        tag2 = self.Tag(id=2)
        article.tags = [tag1]
        self.session.add_all([article, tag1, tag2])
        self.session.commit()

        data = {
            'data': [
                {'type': 'tag', 'id': '2'},
            ]
        }
        response = self.app.patch('/api/article/1/relationships/tags',
                                  data=dumps(data))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(article.tags, [tag2])


class TestAssociationTable(ManagerTestBase):
    """Tests for association proxy with an association table."""

    def setUp(self):
        super(TestAssociationTable, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            tags = relationship('Tag', secondary=lambda: articletags_table)
            tag_names = association_proxy('tags', 'name',
                                          creator=lambda s: Tag(name=s))

        class Tag(self.Base):
            __tablename__ = 'tag'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)

        articletags_table = \
            Table('articletags', self.Base.metadata,
                  Column('article_id', Integer, ForeignKey('article.id'),
                         primary_key=True),
                  Column('tag_id', Integer, ForeignKey('tag.id'),
                         primary_key=True))

        self.Article = Article
        self.Tag = Tag
        self.Base.metadata.create_all()

    def test_fetching(self):
        """Tests for fetching an association proxy to scalars as a list
        attribute instead of a link object.

        We serialize an association proxy that proxies a collection of
        scalar values via an association table as a JSON list.

        """
        self.manager.create_api(self.Article)

        article = self.Article(id=1)
        article.tag_names = ['foo', 'bar']
        self.session.add(article)
        self.session.commit()

        response = self.app.get('/api/article/1')
        document = loads(response.data)
        article = document['data']
        tag_names = sorted(article['attributes']['tag_names'])
        self.assertEqual(tag_names, ['bar', 'foo'])

    def test_creating(self):
        """Tests for creating with an association proxy to a scalar list."""
        self.manager.create_api(self.Article, methods=['POST'])

        data = {
            'data': {
                'type': 'article',
                'attributes': {
                    'tag_names': ['foo', 'bar']
                }
            }
        }
        response = self.app.post('/api/article', data=dumps(data))
        self.assertEqual(response.status_code, 201)

        # Check that the response includes the `tag_names` attribute.
        document = loads(response.data)
        article = document['data']
        self.assertEqual(article['attributes']['tag_names'], ['foo', 'bar'])

        # Check that the Article object has been created and has the tag names.
        self.assertEqual(self.session.query(self.Article).count(), 1)
        article = self.session.query(self.Article).first()
        self.assertEqual(article.tag_names, ['foo', 'bar'])

    def test_updating(self):
        """Tests for updating an association proxy to a scalar list."""
        self.manager.create_api(self.Article, methods=['PATCH'])

        article = self.Article(id=1)
        article.tag_names = ['foo', 'bar']
        self.session.add(article)
        self.session.commit()

        data = {
            'data': {
                'type': 'article',
                'id': '1',
                'attributes': {
                    'tag_names': ['baz', 'xyzzy']
                }
            }
        }
        response = self.app.patch('/api/article/1', data=dumps(data))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(article.tag_names, ['baz', 'xyzzy'])

    def test_deleting(self):
        """Test for deleting a resource with a to-many relationship."""
        self.manager.create_api(self.Article, methods=['DELETE'])

        article = self.Article(id=1)
        article.tag_names = ['foo', 'bar']
        self.session.add(article)
        self.session.commit()

        data = {
            'data': {
                'type': 'article',
                'id': '1',
            }
        }
        response = self.app.delete('/api/article/1', data=dumps(data))
        self.assertEqual(response.status_code, 204)
        tags = self.session.query(self.Tag).all()
        self.assertEqual(['bar', 'foo'], sorted(tag.name for tag in tags))

    def test_fetch_relationships(self):
        """Test for fetching to-many relationship resource identifiers."""
        self.manager.create_api(self.Article)
        self.manager.create_api(self.Tag)

        article = self.Article(id=1)
        article.tag_names = ['foo', 'bar']
        self.session.add(article)
        self.session.commit()

        # TODO What to do about this situation? The `tags` relationship
        # is not shown in the resource representation of the Article
        # object because we assume the `tag_names` attribute is the only
        # thing the user wants to expose. However, the Tag objects
        # underlying the `tag_names` are visible in the relationships
        # attribute.
        response = self.app.get('/api/article/1/relationships/tags')
        self.assertEqual(response.status_code, 404)

    def test_adding_to_relationship(self):
        """Test for adding to a to-many relationship via association proxy."""
        self.manager.create_api(self.Article, methods=['PATCH'])
        self.manager.create_api(self.Tag)

        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()

        # TODO What to do about this situation? The `tags` relationship
        # is not shown in the resource representation of the Article
        # object because we assume the `tag_names` attribute is the only
        # thing the user wants to expose. However, the Tag objects
        # underlying the `tag_names` are visible in the relationships
        # attribute. Maybe we shouldn't actually hide the `tags`
        # relationship.
        data = {
            'data': [
                {'type': 'tag', 'id': '1'},
                {'type': 'tag', 'id': '2'},
            ]
        }
        response = self.app.post('/api/article/1/relationships/tags',
                                 data=dumps(data))
        self.assertEqual(response.status_code, 404)

    def test_removing_from_relationship(self):
        """Test for removing from a to-many relationship."""
        self.manager.create_api(self.Article, methods=['PATCH'],
                                allow_delete_from_to_many_relationships=True)
        self.manager.create_api(self.Tag)

        article = self.Article(id=1)
        tag = self.Tag(id=1)
        article.tags = [tag]
        self.session.add_all([article, tag])
        self.session.commit()

        # TODO What to do about this situation? The `tags` relationship
        # is not shown in the resource representation of the Article
        # object because we assume the `tag_names` attribute is the only
        # thing the user wants to expose. However, the Tag objects
        # underlying the `tag_names` are visible in the relationships
        # attribute. Maybe we shouldn't actually hide the `tags`
        # relationship.
        data = {
            'data': [
                {'type': 'tag', 'id': '1'},
            ]
        }
        response = self.app.delete('/api/article/1/relationships/tags',
                                   data=dumps(data))
        self.assertEqual(response.status_code, 404)

    def test_replacing_relationship(self):
        """Test for replacing a to-many relationship via association proxy."""
        self.manager.create_api(self.Article, methods=['PATCH'],
                                allow_to_many_replacement=True)
        self.manager.create_api(self.Tag)

        article = self.Article(id=1)
        tag1 = self.Tag(id=1)
        tag2 = self.Tag(id=2)
        article.tags = [tag1]
        self.session.add_all([article, tag1, tag2])
        self.session.commit()

        # TODO What to do about this situation? The `tags` relationship
        # is not shown in the resource representation of the Article
        # object because we assume the `tag_names` attribute is the only
        # thing the user wants to expose. However, the Tag objects
        # underlying the `tag_names` are visible in the relationships
        # attribute. Maybe we shouldn't actually hide the `tags`
        # relationship.
        data = {
            'data': [
                {'type': 'tag', 'id': '2'},
            ]
        }
        response = self.app.patch('/api/article/1/relationships/tags',
                                  data=dumps(data))
        self.assertEqual(response.status_code, 404)
