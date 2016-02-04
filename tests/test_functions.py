# test_functions.py - unit tests for function evaluation endpoints
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
"""Unit tests for function evaluation endpoints."""
from sqlalchemy import Column
from sqlalchemy import Integer

from .helpers import dumps
from .helpers import loads
from .helpers import ManagerTestBase


class TestFunctionEvaluation(ManagerTestBase):
    """Unit tests for the :class:`flask_restless.views.FunctionAPI` class."""

    def setup(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`testapp.Person` and
        :class:`testapp.Computer` models.

        """
        super(TestFunctionEvaluation, self).setup()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            age = Column(Integer)

        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Person, allow_functions=True)

    def test_multiple_functions(self):
        """Test that the :http:get:`/api/eval/person` endpoint returns the
        result of evaluating multiple functions.

        """
        person1 = self.Person(age=10)
        person2 = self.Person(age=15)
        person3 = self.Person(age=20)
        self.session.add_all([person1, person2, person3])
        self.session.commit()
        functions = [dict(name='sum', field='age'),
                     dict(name='avg', field='age'),
                     dict(name='count', field='id')]
        query = dumps(functions)
        response = self.app.get('/api/eval/person?functions={0}'.format(query))
        assert response.status_code == 200
        document = loads(response.data)
        results = document['data']
        assert [45.0, 15.0, 3] == results

    def test_no_query(self):
        """Tests that a request to the function evaluation endpoint with no
        query parameter yields an error response.

        """
        response = self.app.get('/api/eval/person')
        assert response.status_code == 400
        # TODO check error message

    def test_empty_query(self):
        """Tests that a request to the function evaluation endpoint with an
        empty functions query yields an error response.

        """
        response = self.app.get('/api/eval/person?functions=')
        assert response.status_code == 400

    def test_no_functions(self):
        """Tests that if no functions are defined, an empty response is
        returned.

        """
        response = self.app.get('/api/eval/person?functions=[]')
        assert response.status_code == 200
        document = loads(response.data)
        results = document['data']
        assert results == []

    def test_missing_function_name(self):
        functions = [dict(field='age')]
        query = dumps(functions)
        response = self.app.get('/api/eval/person?functions={0}'.format(query))
        assert response.status_code == 400
        # TODO check error message here

    def test_missing_field_name(self):
        functions = [dict(name='sum')]
        query = dumps(functions)
        response = self.app.get('/api/eval/person?functions={0}'.format(query))
        assert response.status_code == 400
        # TODO check error message here

    def test_bad_field_name(self):
        functions = [dict(name='sum', field='bogus')]
        query = dumps(functions)
        response = self.app.get('/api/eval/person?functions={0}'.format(query))
        assert response.status_code == 400
        # TODO check error message here

    def test_bad_function_name(self):
        """Tests that an unknown function name yields an error response."""
        functions = [dict(name='bogus', field='age')]
        query = dumps(functions)
        response = self.app.get('/api/eval/person?functions={0}'.format(query))
        assert response.status_code == 400
        # TODO check error message here

    def test_jsonp(self):
        """Test for JSON-P callbacks."""
        person = self.Person(age=10)
        self.session.add(person)
        self.session.commit()
        functions = [dict(name='sum', field='age')]
        response = self.app.get('/api/eval/person?functions={0}'
                                '&callback=foo'.format(dumps(functions)))
        assert response.status_code == 200
        assert response.mimetype == 'application/javascript'
        assert response.data.startswith(b'foo(')
        assert response.data.endswith(b')')
        document = loads(response.data[4:-1])
        results = document['data']
        assert [10.0] == results
