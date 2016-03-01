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
"""Tests that Flask-Restless handles the responsibilities of a server
according to the JSON API specification.

The tests in this module correspond to the `Server Responsibilities`_
section of the JSON API specification.

.. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

"""
from sqlalchemy import Column
from sqlalchemy import Unicode
from sqlalchemy import Integer

from flask.ext.restless import CONTENT_TYPE

from ..helpers import check_sole_error
from ..helpers import dumps
from ..helpers import loads
from ..helpers import ManagerTestBase
from ..helpers import skip


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
            name = Column(Unicode)

        #self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Person, methods=['GET', 'POST', 'PATCH',
                                                 'DELETE'])

    def test_get_content_type(self):
        """"Tests that a response to a :http:method:`get` request has
        the correct content type.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

        """
        response = self.app.get('/api/person')
        assert response.mimetype == CONTENT_TYPE

    def test_post_content_type(self):
        """"Tests that a response to a :http:method:`post` request has
        the correct content type.

        Our implementation of the JSON API specification always responds
        to a :http:method:`post` request with a representation of the
        created resource.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

        """
        data = {'data': {'type': 'person'}}
        response = self.app.post('/api/person', data=dumps(data))
        assert response.mimetype == CONTENT_TYPE

    @skip('we currently do not support updates that have side-effects')
    def test_patch_content_type(self):
        """"Tests that the response for a :http:method:`patch` request
        that has side-effects has the correct content type.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = {
            'data': {
                'type': 'person',
                'id': 1,
                'attributes': {
                    'name': 'bar'
                }
            }
        }
        # TODO Need to make a request that has side-effects.
        response = self.app.patch('/api/person/1', data=dumps(data))
        assert response.mimetype == CONTENT_TYPE

    def test_no_response_media_type_params(self):
        """"Tests that a server responds with :http:status:`415` if any
        media type parameters appear in the request content type header.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

        """
        data = {
            'data': {
                'type': 'person',
            }
        }
        headers = {'Content-Type': '{0}; version=1'.format(CONTENT_TYPE)}
        response = self.app.post('/api/person', data=dumps(data),
                                 headers=headers)
        check_sole_error(response, 415, ['Content-Type',
                                         'media type parameters'])

    def test_empty_accept_header(self):
        """Tests that an empty :http:header:`Accept` header, which is
        technically legal according to :rfc:`2616#sec14.1`, is allowed,
        since it is not explicitly forbidden by JSON API.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

        """
        headers = {'Accept': ''}
        response = self.app.get('/api/person', headers=headers)
        assert response.status_code == 200
        document = loads(response.data)
        assert len(document['data']) == 0

    def test_valid_accept_header(self):
        """Tests that we handle requests with an :http:header:`Accept`
        header specifying the JSON API mimetype are handled normally.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

        """
        headers = {'Accept': CONTENT_TYPE}
        response = self.app.get('/api/person', headers=headers)
        assert response.status_code == 200
        document = loads(response.data)
        assert len(document['data']) == 0

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
        check_sole_error(response, 406, ['Accept', 'media type parameter'])
