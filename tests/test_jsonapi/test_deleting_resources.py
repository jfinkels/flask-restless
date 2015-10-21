from sqlalchemy import Column
from sqlalchemy import Integer

from ..helpers import ManagerTestBase


class TestDeletingResources(ManagerTestBase):
    """Tests corresponding to the `Deleting Resources`_ section of the JSON API
    specification.

    .. _Deleting Resources: http://jsonapi.org/format/#crud-deleting

    """

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        class.

        """
        # create the database
        super(TestDeletingResources, self).setUp()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(self.Person, methods=['DELETE'])

    def test_delete(self):
        """Tests for deleting a resource.

        For more information, see the `Deleting Resources`_ section of the JSON
        API specification.

        .. _Deleting Resources: http://jsonapi.org/format/#crud-deleting

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.delete('/api/person/1')
        assert response.status_code == 204
        assert self.session.query(self.Person).count() == 0

    def test_delete_nonexistent(self):
        """Tests that deleting a nonexistent resource causes a
        :http:status:`404`.

        For more information, see the `404 Not Found`_ section of the JSON API
        specification.

        .. _404 Not Found: http://jsonapi.org/format/#crud-deleting-responses-404

        """
        response = self.app.delete('/api/person/1')
        assert response.status_code == 404
