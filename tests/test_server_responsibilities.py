# test_server_responsibilities.py - tests JSON API server responsibilities
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
"""Tests for server-side content negotiation responsibilities."""
from sqlalchemy import Column
from sqlalchemy import Integer

from .helpers import loads
from .helpers import ManagerTestBase


class TestServerResponsibilities(ManagerTestBase):
    """Tests for server-side content negotiation responsibilities."""

    def setUp(self):
        super(TestServerResponsibilities, self).setUp()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Person)

    def test_accept_star_star(self):
        """"Test for the Accept: */* header.

        For more information, see GitHub issue #548.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        headers = {'Accept': '*/*'}
        response = self.app.get('/api/person/1', headers=headers)
        self.assertEqual(response.status_code, 200)
        document = loads(response.data)
        person = document['data']
        self.assertEqual(person['id'], '1')
        self.assertEqual(person['type'], 'person')

    def test_no_duplicate_headers(self):
        """Test that each header appears only once in the response.

        For more information, see GitHub issue #479.

        """
        response = self.app.get('/api/person')
        self.assertIn('Content-Type', response.headers)
        self.assertIn('Link', response.headers)
        headers_list = response.headers.to_wsgi_list()
        # TODO In Python 2.7+, this should be a set comprehension.
        headers_set = set(k for k, v in headers_list)
        self.assertEqual(len(headers_list), len(headers_set))

    def test_jsonp_content_type(self):
        """Test that the Content-Type for JSONP is application/javascript."""
        response = self.app.get('/api/person?callback=foo')
        self.assertEqual(response.content_type, 'application/javascript')

    def test_jsonp_one_content_type(self):
        """Test that a JSONP response has only one Content-Type header.

        For more information, see GitHub issue #479.

        """
        response = self.app.get('/api/person?callback=foo')
        headers_list = response.headers.to_wsgi_list()
        # TODO In Python 2.7+, this should be a set comprehension.
        headers_set = set(k for k, v in headers_list)
        self.assertEqual(len(headers_list), len(headers_set))
