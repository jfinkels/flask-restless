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

from .helpers import check_sole_error
from .helpers import dumps
from .helpers import loads
from .helpers import ManagerTestBase


class TestFunctionEvaluation(ManagerTestBase):
    """Unit tests for the :class:`flask_restless.views.FunctionAPI` class."""

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`testapp.Person` and
        :class:`testapp.Computer` models.

        """
        super(TestFunctionEvaluation, self).setUp()

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
        query_string = {'functions': dumps(functions)}
        response = self.app.get('/api/eval/person', query_string=query_string)
        assert response.status_code == 200
        document = loads(response.data)
        results = document['data']
        assert [45.0, 15.0, 3] == results

    def test_no_query(self):
        """Tests that a request to the function evaluation endpoint with no
        query parameter yields an error response.

        """
        response = self.app.get('/api/eval/person')
        check_sole_error(response, 400, ['functions', 'provide',
                                         'query parameter'])

    def test_empty_query(self):
        """Tests that a request to the function evaluation endpoint with an
        empty functions query yields an error response.

        """
        query_string = {'functions': ''}
        response = self.app.get('/api/eval/person', query_string=query_string)
        check_sole_error(response, 400, ['Unable', 'decode', 'JSON',
                                         'functions'])

    def test_no_functions(self):
        """Tests that if no functions are defined, an empty response is
        returned.

        """
        functions = []
        query_string = {'functions': dumps(functions)}
        response = self.app.get('/api/eval/person', query_string=query_string)
        assert response.status_code == 200
        document = loads(response.data)
        results = document['data']
        assert results == []

    def test_missing_function_name(self):
        functions = [dict(field='age')]
        query_string = {'functions': dumps(functions)}
        response = self.app.get('/api/eval/person', query_string=query_string)
        check_sole_error(response, 400, ['Missing', 'name', 'function'])

    def test_missing_field_name(self):
        functions = [dict(name='sum')]
        query_string = {'functions': dumps(functions)}
        response = self.app.get('/api/eval/person', query_string=query_string)
        check_sole_error(response, 400, ['Missing', 'field', 'function'])

    def test_bad_field_name(self):
        functions = [dict(name='sum', field='bogus')]
        query_string = {'functions': dumps(functions)}
        response = self.app.get('/api/eval/person', query_string=query_string)
        check_sole_error(response, 400, ['unknown', 'field', 'bogus'])

    def test_bad_function_name(self):
        """Tests that an unknown function name yields an error response."""
        functions = [dict(name='bogus', field='age')]
        query_string = {'functions': dumps(functions)}
        response = self.app.get('/api/eval/person', query_string=query_string)
        check_sole_error(response, 400, ['unknown', 'function', 'bogus'])

    def test_jsonp(self):
        """Test for JSON-P callbacks."""
        person = self.Person(age=10)
        self.session.add(person)
        self.session.commit()
        functions = [dict(name='sum', field='age')]
        query_string = {'functions': dumps(functions), 'callback': 'foo'}
        response = self.app.get('/api/eval/person', query_string=query_string)
        assert response.status_code == 200
        assert response.mimetype == 'application/javascript'
        assert response.data.startswith(b'foo(')
        assert response.data.endswith(b')')
        document = loads(response.data[4:-1])
        results = document['data']
        assert [10.0] == results

    def test_filter_before_functions(self):
        """Tests that filters are applied before functions are called.

        """
        person1 = self.Person(age=5)
        person2 = self.Person(age=10)
        person3 = self.Person(age=15)
        person4 = self.Person(age=20)
        self.session.add_all([person1, person2, person3, person4])
        self.session.commit()
        # This filter should exclude `person4`.
        filters = [{'name': 'age', 'op': '<', 'val': 20}]
        # Get the sum of the ages and the mean of the ages, in that order.
        functions = [
            {'name': 'sum', 'field': 'age'},
            {'name': 'avg', 'field': 'age'},
        ]
        query_string = {'filter[objects]': dumps(filters),
                        'functions': dumps(functions)}
        response = self.app.get('/api/eval/person', query_string=query_string)
        assert response.status_code == 200
        document = loads(response.data)
        results = document['data']
        assert [30, 10.0] == results

    def test_bad_filter_json(self):
        """Tests for invalid JSON in the ``filter[objects]`` query parameter.

        """
        functions = [{'name': 'sum', 'field': 'age'}]
        query_string = {'filter[objects]': 'bogus',
                        'functions': dumps(functions)}
        response = self.app.get('/api/eval/person', query_string=query_string)
        check_sole_error(response, 400, ['Unable', 'decode', 'filter objects'])

    def test_invalid_filter_object(self):
        """Tests that providing an incorrectly formatted argument to
        ``filter[objects]`` yields an error response.

        """
        functions = [{'name': 'sum', 'field': 'age'}]
        filters = [{'name': 'bogus', 'op': 'eq', 'val': 'foo'}]
        query_string = {'filter[objects]': dumps(filters),
                        'functions': dumps(functions)}
        response = self.app.get('/api/eval/person', query_string=query_string)
        check_sole_error(response, 400, ['invalid', 'filter', 'object',
                                         'bogus'])

    def test_bad_single(self):
        """Tests that providing an incorrectly formatted argument to
        ``filter[single]`` yields an error response.

        """
        functions = [{'name': 'sum', 'field': 'age'}]
        query_string = {'filter[single]': 'bogus',
                        'functions': dumps(functions)}
        response = self.app.get('/api/eval/person', query_string=query_string)
        check_sole_error(response, 400, ['Invalid', 'format', 'single',
                                         'query parameter'])
