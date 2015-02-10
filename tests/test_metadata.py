"""
    tests.test_metadata
    ~~~~~~~~~~~~~~~~~~~

    Provides tests for metadata in responses.

    :copyright: 2015 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com> and
                contributors.
    :license: GNU AGPLv3+ or BSD

"""
from sqlalchemy import Column
from sqlalchemy import Integer

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

        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Person)

    def test_total(self):
        """Tests that a request for (a subset of) all instances of a model
        includes the total number of results as part of the JSON response.

        """
        people = [self.Person() for n in range(15)]
        self.session.add_all(people)
        self.session.commit()
        response = self.app.get('/api/person')
        document = loads(response.data)
        assert document['meta']['total'] == 15
