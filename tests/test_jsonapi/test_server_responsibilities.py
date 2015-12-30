# test_server_responsibilities.py - tests JSON API server responsibilities
#
# Copyright 2011 Lincoln de Sousa <lincoln@comum.org>.
# Copyright 2012, 2013, 2014, 2015 Jeffrey Finkelstein
#           <jeffrey.finkelstein@gmail.com> and contributors.
#
# This file is part of Flask-Restless.
#
# Flask-Restless is distributed under both the GNU Affero General Public
# License version 3 and under the 3-clause BSD license. For more
# information, see LICENSE.AGPL and LICENSE.BSD.
"""Tests that Flask-Restless handles the responsibilities of a server
according to the JSON API specification.

The tests in this module correspond to the `Server Responsibilities`_
section of the JSON API specification.

.. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

"""
from sqlalchemy import Column
from sqlalchemy import Integer

from flask.ext.restless import CONTENT_TYPE

from ..helpers import loads
from ..helpers import ManagerTestBase


class TestServerResponsibilities(ManagerTestBase):
    """Tests corresponding to the `Server Responsibilities`_ section of
    the JSON API specification.

    .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

    """

    def setup(self):
        super(TestServerResponsibilities, self).setup()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        #self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Person)

    def test_response_content_type(self):
        """"Tests that a server responds with the correct content type.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

        """
        response = self.app.get('/api/person')
        assert response.mimetype == CONTENT_TYPE

    def test_no_response_media_type_params(self):
        """"Tests that a server responds with :http:status:`415` if any
        media type parameters appear in the request content type header.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

        """
        headers = {'Content-Type': '{0}; version=1'.format(CONTENT_TYPE)}
        response = self.app.get('/api/person', headers=headers)
        assert response.status_code == 415
        document = loads(response.data)
        message = document['errors'][0]['detail']
        assert 'Content-Type' in message
        assert 'media type parameter' in message

    def test_no_accept_media_type_params(self):
        """"Tests that a server responds with :http:status:`406` if each
        :http:header:`Accept` header is the JSON API media type, but
        each instance of that media type has a media type parameter.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

        """
        headers = {'Accept': '{0}; q=.8, {0}; q=.9'.format(CONTENT_TYPE)}
        response = self.app.get('/api/person', headers=headers)
        assert response.status_code == 406
        document = loads(response.data)
        message = document['errors'][0]['detail']
        assert 'Accept' in message
        assert 'media type parameter' in message
