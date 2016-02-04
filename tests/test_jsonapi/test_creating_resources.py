# test_creating_resources.py - tests creating resources according to JSON API
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
"""Unit tests for requests that create resources.

The tests in this module correspond to the `Creating Resources`_ section
of the JSON API specification.

.. _Creating Resources: http://jsonapi.org/format/#crud-creating

"""
import uuid

from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Unicode
from sqlalchemy.orm import relationship

from ..helpers import dumps
from ..helpers import GUID
from ..helpers import loads
from ..helpers import ManagerTestBase


class TestCreatingResources(ManagerTestBase):
    """Tests corresponding to the `Creating Resources`_ section of the JSON API
    specification.

    .. _Creating Resources: http://jsonapi.org/format/#crud-creating

    """

    def setup(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        and :class:`TestSupport.Article` models.

        """
        super(TestCreatingResources, self).setup()

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
