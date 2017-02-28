# test_metadata.py - unit tests for response metadata
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
"""Unit tests for metadata in server responses."""
from unittest2 import skip

from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import Unicode

from flask_restless import JSONAPI_MIMETYPE

from .helpers import loads
from .helpers import ManagerTestBase


class TestMetadata(ManagerTestBase):
    """Tests for receiving metadata in responses."""

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`.

        """
        super(TestMetadata, self).setUp()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)

        self.Person = Person
        self.Base.metadata.create_all()

    def test_total(self):
        """Tests that a request for (a subset of) all instances of a model
        includes the total number of results as part of the JSON response.

        """
        people = [self.Person() for n in range(15)]
        self.session.add_all(people)
        self.session.commit()
        self.manager.create_api(self.Person)
        response = self.app.get('/api/person')
        document = loads(response.data)
        assert document['meta']['total'] == 15

    @skip('Not sure whether this should be implemented')
    def test_http_headers(self):
        """Tests that HTTP headers appear as elements in the JSON metadata."""
        self.manager.create_api(self.Person)
        response = self.app.get('/api/person')
        document = loads(response.data)
        meta = document['meta']
        assert meta['Content-Type'] == JSONAPI_MIMETYPE

    def test_model_info(self):
        """Test for getting schema metadata.

        For more information, see GitHub issue #625.

        """
        self.manager.create_api(self.Person)
        response = self.app.get('/api')
        document = loads(response.data)
        info = document['meta']['modelinfo']
        self.assertEqual(list(info.keys()), ['person'])
        self.assertEqual(sorted(info['person']), ['primarykey', 'url'])
        self.assertEqual(info['person']['primarykey'], 'id')
        self.assertTrue(info['person']['url'].endswith('/api/person'))

    def test_model_info_custom_primary_key(self):
        """Test for getting schema metadata with custom primary key.

        For more information, see GitHub issue #625.

        """
        self.manager.create_api(self.Person, primary_key='name')
        response = self.app.get('/api')
        document = loads(response.data)
        info = document['meta']['modelinfo']
        self.assertEqual(info['person']['primarykey'], 'name')
