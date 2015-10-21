from sqlalchemy import Column
from sqlalchemy import Integer

from flask.ext.restless import CONTENT_TYPE

from ..helpers import ManagerTestBase


class TestServerResponsibilities(ManagerTestBase):
    """Tests corresponding to the `Server Responsibilities`_ section of
    the JSON API specification.

    .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

    """

    def setUp(self):
        super(TestServerResponsibilities, self).setUp()

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
        headers = {'Content-Type': '{}; version=1'.format(CONTENT_TYPE)}
        response = self.app.get('/api/person', headers=headers)
        assert response.status_code == 415

    def test_no_accept_media_type_params(self):
        """"Tests that a server responds with :http:status:`406` if each
        :http:header:`Accept` header is the JSON API media type, but
        each instance of that media type has a media type parameter.

        For more information, see the `Server Responsibilities`_ section
        of the JSON API specification.

        .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

        """
        headers = [('Accept', '{}; version=1'.format(CONTENT_TYPE)),
                   ('Accept', '{}; foo=bar'.format(CONTENT_TYPE))]
        response = self.app.get('/api/person', headers=headers)
        assert response.status_code == 406
