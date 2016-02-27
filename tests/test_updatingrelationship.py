# test_updatingrelationship.py - unit tests for updating relationships
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
"""Unit tests for updating relationships via relationship URLs.

This module includes tests for additional functionality that is not
already tested by :mod:`test_jsonapi`, the package that guarantees
Flask-Restless meets the minimum requirements of the JSON API
specification.

"""
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship

from .helpers import dumps
from .helpers import ManagerTestBase


class TestAdding(ManagerTestBase):
    """Tests for adding to a resource's to-many relationship via the
    relationship URL.

    """

    def setup(self):
        super(TestAdding, self).setup()

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
        self.manager.create_api(Person, methods=['PATCH'])

    def test_nonexistent_instance(self):
        """Tests that an attempt to POST to a relationship URL for a resource
        that doesn't exist yields an error.

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        data = dict(data=[dict(id=1, type='article')])
        data = dumps(data)
        response = self.app.post('/api/person/bogus/relationships/articles',
                                 data=data)
        assert response.status_code == 404
        # TODO check error message here

    def test_nonexistent_relation(self):
        """Tests that an attempt to POST to a relationship URL for a
        nonexistent relation yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = dict(data=dict(id=1, type='bogus'))
        response = self.app.post('/api/person/1/relationships/bogus',
                                 data=dumps(data))
        assert response.status_code == 404
        # TODO check error message here

    def test_missing_relation(self):
        """Tests that an attempt to POST to a relationship URL without
        specifying a relationship yields an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(id=1, type='article')])
        response = self.app.post('/api/person/1/relationships',
                                 data=dumps(data))
        assert response.status_code == 405
        # TODO check error message here

    def test_missing_id(self):
        """Tests that providing a linkage object without an ID yields an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(type='article')])
        data = dumps(data)
        response = self.app.post('/api/person/1/relationships/articles',
                                 data=data)
        assert response.status_code == 400
        # TODO check error message here

    def test_missing_type(self):
        """Tests that providing a linkage object without a resource type yields
        an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(id=1)])
        data = dumps(data)
        response = self.app.post('/api/person/1/relationships/articles',
                                 data=data)
        assert response.status_code == 400
        # TODO check error message here

    def test_conflicting_type(self):
        """Tests that providing a linkage object with an incorrect type yields
        an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(id=1, type='bogus')])
        data = dumps(data)
        response = self.app.post('/api/person/1/relationships/articles',
                                 data=data)
        assert response.status_code == 409
        # TODO check error message here

    def test_nonexistent_linkage(self):
        """Tests that an attempt to POST to a relationship URL with a linkage
        object that has an unknown ID yields an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(id='bogus', type='article')])
        data = dumps(data)
        response = self.app.post('/api/person/1/relationships/articles',
                                 data=data)
        assert response.status_code == 404
        # TODO check error message here

    def test_empty_request(self):
        """Test that attempting to POST to a relationship URL with no data
        yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.post('/api/person/1/relationships/articles')
        assert response.status_code == 400
        # TODO check the error message here

    def test_empty_string(self):
        """Test that attempting to POST to a relationship URL with an empty
        string (which is invalid JSON) yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.post('/api/person/1/relationships/articles',
                                 data='')
        assert response.status_code == 400
        # TODO check the error message here

    def test_invalid_json(self):
        """Test that attempting to POST to a relationship URL with invalid JSON
        yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = 'Invalid JSON string'
        response = self.app.post('/api/person/1/relationships/articles',
                                 data=data)
        assert response.status_code == 400
        # TODO check error message here

    def test_preprocessor(self):
        """Test that a preprocessor is triggered on a request to add to
        a to-many relationship.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        self.session.add_all([article, person])
        self.session.commit()

        data = {'triggered': False}

        def update_data(*args, **kw):
            data['triggered'] = True

        preprocessors = {'POST_RELATIONSHIP': [update_data]}
        self.manager.create_api(self.Person, preprocessors=preprocessors,
                                url_prefix='/api2', methods=['PATCH'])
        data = {'data': [{'type': 'article', 'id': '1'}]}
        # The preprocessor will change the resource ID and the
        # relationship name.
        self.app.post('/api2/person/1/relationships/articles',
                      data=dumps(data))
        assert data['triggered']

    def test_change_two_preprocessor(self):
        """Test for a preprocessor that changes both the primary
        resource ID and the relation name from the ones given in the
        requested URL.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        self.session.add_all([article, person])
        self.session.commit()

        def change_two(*args, **kw):
            return 1, 'articles'

        preprocessors = {'POST_RELATIONSHIP': [change_two]}
        self.manager.create_api(self.Person, preprocessors=preprocessors,
                                url_prefix='/api2', methods=['PATCH'])
        data = {'data': [{'type': 'article', 'id': '1'}]}
        # The preprocessor will change the resource ID and the
        # relationship name.
        response = self.app.post('/api2/person/bogus1/relationships/bogus2',
                                 data=dumps(data))
        assert response.status_code == 204
        assert article.author is person

    def test_postprocessor(self):
        """Tests that a postprocessor gets executing when adding a link
        to a to-many relationship.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        self.session.add_all([article, person])
        self.session.commit()

        has_run = []
        def enable_flag(*args, **kw):
            has_run.append(True)

        postprocessors = {'POST_RELATIONSHIP': [enable_flag]}
        self.manager.create_api(self.Person, postprocessors=postprocessors,
                                url_prefix='/api2', methods=['PATCH'])
        data = {'data': [{'type': 'article', 'id': '1'}]}
        response = self.app.post('/api2/person/1/relationships/articles',
                                 data=dumps(data))
        assert response.status_code == 204
        assert has_run == [True]


class TestDeleting(ManagerTestBase):
    """Tests for deleting a link from a resource's to-many relationship via the
    relationship URL.

    """

    def setup(self):
        super(TestDeleting, self).setup()

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
        self.manager.create_api(Person, methods=['PATCH'],
                                allow_delete_from_to_many_relationships=True)
        self.manager.create_api(Article)

    def test_nonexistent_instance(self):
        """Tests that an attempt to delete from a relationship URL for a
        resource that doesn't exist yields an error.

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        data = dict(data=[dict(id=1, type='article')])
        response = self.app.delete('/api/person/bogus/relationships/articles',
                                   data=dumps(data))
        assert response.status_code == 404
        # TODO check error message here

    def test_nonexistent_relation(self):
        """Tests that an attempt to delete from a relationship URL for a
        nonexistent relation yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = dict(data=dict(id=1, type='bogus'))
        data = dumps(data)
        response = self.app.delete('/api/person/1/relationships/bogus',
                                   data=data)
        assert response.status_code == 404
        # TODO check error message here

    def test_missing_relation(self):
        """Tests that an attempt to delete from a relationship URL without
        specifying a relationship yields an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(id=1, type='article')])
        response = self.app.delete('/api/person/1/relationships',
                                   data=dumps(data))
        assert response.status_code == 405
        # TODO check error message here

    def test_missing_id(self):
        """Tests that providing a linkage object without an ID yields an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(type='article')])
        data = dumps(data)
        response = self.app.delete('/api/person/1/relationships/articles',
                                   data=data)
        assert response.status_code == 400
        # TODO check error message here

    def test_missing_type(self):
        """Tests that providing a linkage object without a resource type yields
        an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(id=1)])
        data = dumps(data)
        response = self.app.delete('/api/person/1/relationships/articles',
                                   data=data)
        assert response.status_code == 400
        # TODO check error message here

    def test_conflicting_type(self):
        """Tests that providing a linkage object with an incorrect type yields
        an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(id=1, type='bogus')])
        data = dumps(data)
        response = self.app.delete('/api/person/1/relationships/articles',
                                   data=data)
        assert response.status_code == 409
        # TODO check error message here

    def test_nonexistent_linkage(self):
        """Tests that an attempt to delete from a relationship URL with a
        linkage object that has an unknown ID yields an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(id='bogus', type='article')])
        data = dumps(data)
        response = self.app.delete('/api/person/1/relationships/articles',
                                   data=data)
        assert response.status_code == 404
        # TODO check error message here

    def test_empty_request(self):
        """Test that attempting to delete from a relationship URL with no data
        yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.delete('/api/person/1/relationships/articles')
        assert response.status_code == 400
        # TODO check the error message here

    def test_empty_string(self):
        """Test that attempting to delete from a relationship URL with an empty
        string (which is invalid JSON) yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.delete('/api/person/1/relationships/articles',
                                   data='')
        assert response.status_code == 400
        # TODO check the error message here

    def test_invalid_json(self):
        """Test that attempting to delete from a relationship URL with invalid
        JSON yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = 'Invalid JSON string'
        response = self.app.delete('/api/person/1/relationships/articles',
                                   data=data)
        assert response.status_code == 400
        # TODO check error message here

    def test_preprocessor(self):
        """Test that a preprocessor is triggered on a request to delete
        from a to-many relationship.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        self.session.add_all([article, person])
        self.session.commit()

        data = {'triggered': False}

        def update_data(*args, **kw):
            data['triggered'] = True

        preprocessors = {'DELETE_RELATIONSHIP': [update_data]}
        self.manager.create_api(self.Person, preprocessors=preprocessors,
                                url_prefix='/api2', methods=['PATCH'],
                                allow_delete_from_to_many_relationships=True)
        data = {'data': [{'type': 'article', 'id': '1'}]}
        # The preprocessor will change the resource ID and the
        # relationship name.
        self.app.delete('/api2/person/1/relationships/articles',
                        data=dumps(data))
        assert data['triggered']

    def test_change_id_preprocessor(self):
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()

        def change_id(*args, **kw):
            return 1

        preprocessors = {'DELETE_RELATIONSHIP': [change_id]}
        self.manager.create_api(self.Person, preprocessors=preprocessors,
                                allow_delete_from_to_many_relationships=True,
                                url_prefix='/api2', methods=['PATCH'])
        data = {'data': [{'type': 'article', 'id': '1'}]}
        response = self.app.delete('/api2/person/bogus/relationships/articles',
                                   data=dumps(data))
        assert response.status_code == 204
        assert article.author is None

    def test_postprocessor(self):
        """Tests that a postprocessor gets executing when deleting from
        a to-many relationship.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()

        has_run = []
        def enable_flag(was_deleted=None, *args, **kw):
            has_run.append(was_deleted)

        postprocessors = {'DELETE_RELATIONSHIP': [enable_flag]}
        self.manager.create_api(self.Person, postprocessors=postprocessors,
                                url_prefix='/api2', methods=['PATCH'],
                                allow_delete_from_to_many_relationships=True)
        data = {'data': [{'type': 'article', 'id': '1'}]}
        response = self.app.delete('/api2/person/1/relationships/articles',
                                   data=dumps(data))
        assert response.status_code == 204
        assert has_run == [True]


class TestUpdatingToMany(ManagerTestBase):
    """Tests for updating a resource's to-many relationship via the
    relationship URL.

    """

    def setup(self):
        super(TestUpdatingToMany, self).setup()

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
        self.manager.create_api(Person, methods=['PATCH'],
                                allow_to_many_replacement=True)
        self.manager.create_api(Article)

    def test_nonexistent_instance(self):
        """Tests that an attempt to update a relationship for a resource that
        doesn't exist yields an error.

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        data = dict(data=[dict(id=1, type='article')])
        response = self.app.patch('/api/person/bogus/relationships/articles',
                                  data=dumps(data))
        assert response.status_code == 404
        # TODO check error message here

    def test_nonexistent_relation(self):
        """Tests that an attempt to update a relationship for a nonexistent
        relation yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = dict(data=[dict(id=1, type='bogus')])
        data = dumps(data)
        response = self.app.patch('/api/person/1/relationships/bogus',
                                  data=data)
        assert response.status_code == 404
        # TODO check error message here

    def test_missing_relation(self):
        """Tests that an attempt to update a relationship without specifying a
        relationship in the URL yields an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(id=1, type='article')])
        response = self.app.patch('/api/person/1/relationships',
                                  data=dumps(data))
        assert response.status_code == 405
        # TODO check error message here

    def test_missing_id(self):
        """Tests that providing a linkage object without an ID yields an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(type='article')])
        data = dumps(data)
        response = self.app.patch('/api/person/1/relationships/articles',
                                  data=data)
        assert response.status_code == 400
        # TODO check error message here

    def test_missing_type(self):
        """Tests that providing a linkage object without a resource type yields
        an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(id=1)])
        data = dumps(data)
        response = self.app.patch('/api/person/1/relationships/articles',
                                  data=data)
        assert response.status_code == 400
        # TODO check error message here

    def test_conflicting_type(self):
        """Tests that providing a linkage object with an incorrect type yields
        an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(id=1, type='bogus')])
        data = dumps(data)
        response = self.app.patch('/api/person/1/relationships/articles',
                                  data=data)
        assert response.status_code == 409
        # TODO check error message here

    def test_nonexistent_linkage(self):
        """Tests that an attempt to update a relationship with a linkage object
        that has an unknown ID yields an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(id='bogus', type='article')])
        data = dumps(data)
        response = self.app.patch('/api/person/1/relationships/articles',
                                  data=data)
        assert response.status_code == 404
        # TODO check error message here

    def test_empty_request(self):
        """Test that attempting to delete from a relationship URL with no data
        yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.patch('/api/person/1/relationships/articles')
        assert response.status_code == 400
        # TODO check the error message here

    def test_empty_string(self):
        """Test that attempting to update a relationship with an empty string
        (which is invalid JSON) yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.patch('/api/person/1/relationships/articles',
                                  data='')
        assert response.status_code == 400
        # TODO check the error message here

    def test_invalid_json(self):
        """Test that attempting to update a relationship with invalid JSON
        yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = 'Invalid JSON string'
        response = self.app.patch('/api/person/1/relationships/articles',
                                  data=data)
        assert response.status_code == 400
        # TODO check error message here

    def test_preprocessor(self):
        """Test that a preprocessor is triggered on a request to update
        a to-many relationship.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        self.session.add_all([article, person])
        self.session.commit()

        data = {'triggered': False}

        def update_data(*args, **kw):
            data['triggered'] = True

        preprocessors = {'PATCH_RELATIONSHIP': [update_data]}
        self.manager.create_api(self.Person, preprocessors=preprocessors,
                                url_prefix='/api2', methods=['PATCH'],
                                allow_to_many_replacement=True)
        data = {'data': [{'type': 'article', 'id': '1'}]}
        # The preprocessor will change the resource ID and the
        # relationship name.
        self.app.patch('/api2/person/1/relationships/articles',
                       data=dumps(data))
        assert data['triggered']

    def test_change_two_preprocessor(self):
        """Test for a preprocessor that changes both the primary
        resource ID and the relation name from the ones given in the
        requested URL.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        self.session.add_all([article, person])
        self.session.commit()

        def change_two(*args, **kw):
            return 1, 'articles'

        preprocessors = {'PATCH_RELATIONSHIP': [change_two]}
        self.manager.create_api(self.Person, preprocessors=preprocessors,
                                url_prefix='/api2', methods=['PATCH'],
                                allow_to_many_replacement=True)
        data = {'data': [{'type': 'article', 'id': '1'}]}
        # The preprocessor will change the resource ID and the
        # relationship name.
        response = self.app.patch('/api2/person/bogus1/relationships/bogus2',
                                  data=dumps(data))
        assert response.status_code == 204
        assert person.articles == [article]

    def test_postprocessor(self):
        """Tests that a postprocessor gets executing when replacing a
        to-many relationship.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        self.session.add_all([article, person])
        self.session.commit()

        has_run = []
        def enable_flag(*args, **kw):
            has_run.append(True)

        postprocessors = {'PATCH_RELATIONSHIP': [enable_flag]}
        self.manager.create_api(self.Person, postprocessors=postprocessors,
                                url_prefix='/api2', methods=['PATCH'],
                                allow_to_many_replacement=True)
        data = {'data': [{'type': 'article', 'id': '1'}]}
        response = self.app.patch('/api2/person/1/relationships/articles',
                                  data=dumps(data))
        assert response.status_code == 204
        assert has_run == [True]

    def test_set_null(self):
        """Tests that an attempt to set a null value on a to-many
        relationship causes an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = {'data': None}
        response = self.app.patch('/api/person/1/relationships/articles',
                                  data=dumps(data))
        assert response.status_code == 400
        # TODO Check error message here.


class TestUpdatingToOne(ManagerTestBase):
    """Tests for updating a resource's to-one relationship via the relationship
    URL.

    """

    def setup(self):
        super(TestUpdatingToOne, self).setup()

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
        self.manager.create_api(Article, methods=['PATCH'])
        self.manager.create_api(Person)

    def test_nonexistent_instance(self):
        """Tests that an attempt to update a relationship for a resource that
        doesn't exist yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = dict(data=dict(id=1, type='person'))
        response = self.app.patch('/api/article/bogus/relationships/author',
                                  data=dumps(data))
        assert response.status_code == 404
        # TODO check error message here

    def test_nonexistent_relation(self):
        """Tests that an attempt to update a relationship for a nonexistent
        relation yields an error.

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        data = dict(data=dict(id=1, type='bogus'))
        data = dumps(data)
        response = self.app.patch('/api/article/1/relationships/bogus',
                                  data=data)
        assert response.status_code == 404
        # TODO check error message here

    def test_missing_relation(self):
        """Tests that an attempt to update a relationship without specifying a
        relationship in the URL yields an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=dict(id=1, type='person'))
        response = self.app.patch('/api/article/1/relationships',
                                  data=dumps(data))
        assert response.status_code == 405
        # TODO check error message here

    def test_missing_id(self):
        """Tests that providing a linkage object without an ID yields an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=dict(type='person'))
        data = dumps(data)
        response = self.app.patch('/api/article/1/relationships/author',
                                  data=data)
        assert response.status_code == 400
        # TODO check error message here

    def test_missing_type(self):
        """Tests that providing a linkage object without a resource type yields
        an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=dict(id=1))
        data = dumps(data)
        response = self.app.patch('/api/article/1/relationships/author',
                                  data=data)
        assert response.status_code == 400
        # TODO check error message here

    def test_conflicting_type(self):
        """Tests that providing a linkage object with an incorrect type yields
        an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=dict(id=1, type='bogus'))
        data = dumps(data)
        response = self.app.patch('/api/article/1/relationships/author',
                                  data=data)
        assert response.status_code == 409
        # TODO check error message here

    def test_nonexistent_linkage(self):
        """Tests that an attempt to update a relationship with a linkage object
        that has an unknown ID yields an error.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=dict(id='bogus', type='person'))
        data = dumps(data)
        response = self.app.patch('/api/article/1/relationships/author',
                                  data=data)
        print(response.data)
        assert response.status_code == 404
        # TODO check error message here

    def test_empty_request(self):
        """Test that attempting to delete from a relationship URL with no data
        yields an error.

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.patch('/api/article/1/relationships/author')
        assert response.status_code == 400
        # TODO check the error message here

    def test_empty_string(self):
        """Test that attempting to update a relationship with an empty string
        (which is invalid JSON) yields an error.

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.patch('/api/article/1/relationships/author',
                                  data='')
        assert response.status_code == 400
        # TODO check the error message here

    def test_invalid_json(self):
        """Test that attempting to update a relationship with invalid JSON
        yields an error.

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        data = 'Invalid JSON string'
        response = self.app.patch('/api/article/1/relationships/author',
                                  data=data)
        assert response.status_code == 400
        # TODO check error message here
