"""
    tests.test_updatingrelationship
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Provides tests for updating relationships via relationship URLs.

    This module includes tests for additional functionality that is not already
    tested by :mod:`test_jsonapi`, the module that guarantees Flask-Restless
    meets the minimum requirements of the JSON API specification.

    :copyright: 2015 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com> and
                contributors.
    :license: GNU AGPLv3+ or BSD

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

    def setUp(self):
        super(TestAdding, self).setUp()

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
        response = self.app.post('/api/person/bogus/links/articles', data=data)
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
        response = self.app.post('/api/person/1/links/bogus', data=dumps(data))
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
        response = self.app.post('/api/person/1/links', data=dumps(data))
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
        response = self.app.post('/api/person/1/links/articles', data=data)
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
        response = self.app.post('/api/person/1/links/articles', data=data)
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
        response = self.app.post('/api/person/1/links/articles', data=data)
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
        response = self.app.post('/api/person/1/links/articles', data=data)
        assert response.status_code == 404
        # TODO check error message here

    def test_empty_request(self):
        """Test that attempting to POST to a relationship URL with no data
        yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.post('/api/person/1/links/articles')
        assert response.status_code == 400
        # TODO check the error message here

    def test_empty_string(self):
        """Test that attempting to POST to a relationship URL with an empty
        string (which is invalid JSON) yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.post('/api/person/1/links/articles', data='')
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
        response = self.app.post('/api/person/1/links/articles', data=data)
        assert response.status_code == 400
        # TODO check error message here


class TestDeleting(ManagerTestBase):
    """Tests for deleting a link from a resource's to-many relationship via the
    relationship URL.

    """

    def setUp(self):
        super(TestDeleting, self).setUp()

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
        response = self.app.delete('/api/person/bogus/links/articles',
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
        response = self.app.delete('/api/person/1/links/bogus', data=data)
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
        response = self.app.delete('/api/person/1/links', data=dumps(data))
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
        response = self.app.delete('/api/person/1/links/articles', data=data)
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
        response = self.app.delete('/api/person/1/links/articles', data=data)
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
        response = self.app.delete('/api/person/1/links/articles', data=data)
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
        response = self.app.delete('/api/person/1/links/articles', data=data)
        assert response.status_code == 404
        # TODO check error message here

    def test_empty_request(self):
        """Test that attempting to delete from a relationship URL with no data
        yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.delete('/api/person/1/links/articles')
        assert response.status_code == 400
        # TODO check the error message here

    def test_empty_string(self):
        """Test that attempting to delete from a relationship URL with an empty
        string (which is invalid JSON) yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.delete('/api/person/1/links/articles', data='')
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
        response = self.app.delete('/api/person/1/links/articles', data=data)
        assert response.status_code == 400
        # TODO check error message here


class TestUpdatingToMany(ManagerTestBase):
    """Tests for updating a resource's to-many relationship via the
    relationship URL.

    """

    def setUp(self):
        super(TestUpdatingToMany, self).setUp()

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
        response = self.app.patch('/api/person/bogus/links/articles',
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
        response = self.app.patch('/api/person/1/links/bogus', data=data)
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
        response = self.app.patch('/api/person/1/links', data=dumps(data))
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
        response = self.app.patch('/api/person/1/links/articles', data=data)
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
        response = self.app.patch('/api/person/1/links/articles', data=data)
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
        response = self.app.patch('/api/person/1/links/articles', data=data)
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
        response = self.app.patch('/api/person/1/links/articles', data=data)
        assert response.status_code == 404
        # TODO check error message here

    def test_empty_request(self):
        """Test that attempting to delete from a relationship URL with no data
        yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.patch('/api/person/1/links/articles')
        assert response.status_code == 400
        # TODO check the error message here

    def test_empty_string(self):
        """Test that attempting to update a relationship with an empty string
        (which is invalid JSON) yields an error.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.patch('/api/person/1/links/articles', data='')
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
        response = self.app.patch('/api/person/1/links/articles', data=data)
        assert response.status_code == 400
        # TODO check error message here


class TestUpdatingToOne(ManagerTestBase):
    """Tests for updating a resource's to-one relationship via the relationship
    URL.

    """

    def setUp(self):
        super(TestUpdatingToOne, self).setUp()

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
        response = self.app.patch('/api/article/bogus/links/author',
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
        response = self.app.patch('/api/article/1/links/bogus', data=data)
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
        response = self.app.patch('/api/article/1/links', data=dumps(data))
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
        response = self.app.patch('/api/article/1/links/author', data=data)
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
        response = self.app.patch('/api/article/1/links/author', data=data)
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
        response = self.app.patch('/api/article/1/links/author', data=data)
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
        response = self.app.patch('/api/article/1/links/author', data=data)
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
        response = self.app.patch('/api/article/1/links/author')
        assert response.status_code == 400
        # TODO check the error message here

    def test_empty_string(self):
        """Test that attempting to update a relationship with an empty string
        (which is invalid JSON) yields an error.

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.patch('/api/article/1/links/author', data='')
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
        response = self.app.patch('/api/article/1/links/author', data=data)
        assert response.status_code == 400
        # TODO check error message here
