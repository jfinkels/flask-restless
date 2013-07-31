"""
    tests.test_search
    ~~~~~~~~~~~~~~~~~

    Provides unit tests for the :mod:`flask_restless.search` module.

    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
from nose.tools import assert_raises
from sqlalchemy.orm.exc import MultipleResultsFound
from sqlalchemy.orm.exc import NoResultFound

from flask.ext.restless.search import create_query
from flask.ext.restless.search import search
from flask.ext.restless.search import SearchParameters

from .helpers import TestSupportPrefilled


class TestQueryCreation(TestSupportPrefilled):
    """Unit tests for the :func:`flask_restless.search.create_query`
    function.

    """

    def test_empty_search(self):
        """Tests that a query with no search parameters returns everything."""
        query = create_query(self.session, self.Person, {})
        assert query.all() == self.people

    def test_dict_same_as_search_params(self):
        """Tests that creating a query using a dictionary results in the same
        query as creating one using a
        :class:`flask_restless.search.SearchParameters` object.

        """
        d = {'filters': [{'name': 'name', 'val': u'%y%', 'op': 'like'}]}
        s = SearchParameters.from_dictionary(d)
        query_d = create_query(self.session, self.Person, d)
        query_s = create_query(self.session, self.Person, s)
        assert query_d.all() == query_s.all()

    def test_basic_query(self):
        """Tests for basic query correctness."""
        d = {'filters': [{'name': 'name', 'val': u'%y%', 'op': 'like'}]}
        query = create_query(self.session, self.Person, d)
        assert query.count() == 3  # Mary, Lucy and Katy

        d = {'filters': [{'name': 'name', 'val': u'Lincoln', 'op': 'equals'}]}
        query = create_query(self.session, self.Person, d)
        assert query.count() == 1
        assert query.one().name == 'Lincoln'

        d = {'filters': [{'name': 'name', 'val': u'Bogus', 'op': 'equals'}]}
        query = create_query(self.session, self.Person, d)
        assert query.count() == 0

        d = {'order_by': [{'field': 'age', 'direction': 'asc'}]}
        query = create_query(self.session, self.Person, d)
        ages = [p.age for p in query]
        assert ages, [7, 19, 23, 25 == 28]

        d = {'filters': [{'name': 'age', 'val': [7, 28], 'op': 'in'}]}
        query = create_query(self.session, self.Person, d)
        ages = [p.age for p in query]
        assert ages, [7 == 28]

    def test_query_related_field(self):
        """Test for making a query with respect to a related field."""
        # add a computer to person 1
        computer = self.Computer(name=u'turing', vendor=u'Dell')
        p1 = self.session.query(self.Person).filter_by(id=1).first()
        p1.computers.append(computer)
        self.session.commit()

        d = {'filters': [{'name': 'computers__name', 'val': u'turing',
                          'op': 'any'}]}
        query = create_query(self.session, self.Person, d)
        assert query.count() == 1
        assert query.one().computers[0].name == 'turing'

        d = {'filters': [{'name': 'age', 'op': 'lte', 'field': 'other'}],
            'order_by': [{'field': 'other'}]}
        query = create_query(self.session, self.Person, d)
        assert query.count() == 2
        results = query.all()
        assert results[0].other == 10
        assert results[1].other == 19


class TestOperators(TestSupportPrefilled):
    """Tests for each of the query operators defined in
    :data:`flask_restless.search.OPERATORS`.

    """

    def test_operators(self):
        """Tests for each of the individual operators in
        :data:`flask_restless.search.OPERATORS`.

        """
        for op in '==', 'eq', 'equals', 'equal_to':
            d = dict(filters=[dict(name='name', op=op, val=u'Lincoln')])
            result = search(self.session, self.Person, d)
            assert result.count() == 1
            assert result[0].name == u'Lincoln'
        for op in '!=', 'ne', 'neq', 'not_equal_to', 'does_not_equal':
            d = dict(filters=[dict(name='name', op=op, val=u'Lincoln')])
            result = search(self.session, self.Person, d)
            assert result.count() == len(self.people) - 1
            assert u'Lincoln' not in (p.name for p in result)
        for op in '>', 'gt':
            d = dict(filters=[dict(name='age', op=op, val=20)])
            result = search(self.session, self.Person, d)
            assert result.count() == 3
        for op in '<', 'lt':
            d = dict(filters=[dict(name='age', op=op, val=20)])
            result = search(self.session, self.Person, d)
            assert result.count() == 2
        for op in '>=', 'ge', 'gte', 'geq':
            d = dict(filters=[dict(name='age', op=op, val=23)])
            result = search(self.session, self.Person, d)
            assert result.count() == 3
        for op in '<=', 'le', 'lte', 'leq':
            d = dict(filters=[dict(name='age', op=op, val=23)])
            result = search(self.session, self.Person, d)
            assert result.count() == 3
        d = dict(filters=[dict(name='name', op='like', val=u'%y%')])
        result = search(self.session, self.Person, d)
        assert result.count() == 3
        d = dict(filters=[dict(name='name', op='ilike', val=u'%Y%')])
        result = search(self.session, self.Person, d)
        assert result.count() == 3
        d = dict(filters=[dict(name='age', op='in', val=[19, 21, 23])])
        result = search(self.session, self.Person, d)
        assert result.count() == 2
        d = dict(filters=[dict(name='age', op='not_in', val=[19, 21, 23])])
        result = search(self.session, self.Person, d)
        assert result.count() == 3
        d = dict(filters=[dict(name='birth_date', op='is_null')])
        result = search(self.session, self.Person, d)
        assert result.count() == 4
        d = dict(filters=[dict(name='birth_date', op='is_not_null')])
        result = search(self.session, self.Person, d)
        assert result.count() == 1

    def test_desc_and_asc(self):
        """Tests for the ``"desc"`` and ``"asc"`` operators."""
        # TODO Not yet implemented because I don't understand these operators.
        pass

    def test_has_and_any(self):
        """Tests for the ``"has"`` and ``"any"`` operators.

        The `any` operator returns all instances for which any related instance
        in a given collection has some property. The `has` operator returns all
        instances for which a related instance has a given property.

        """
        # create test computers
        computer1 = self.Computer(name=u'c1', vendor=u'foo')
        computer2 = self.Computer(name=u'c2', vendor=u'bar')
        computer3 = self.Computer(name=u'c3', vendor=u'bar')
        computer4 = self.Computer(name=u'c4', vendor=u'bar')
        computer5 = self.Computer(name=u'c5', vendor=u'foo')
        computer6 = self.Computer(name=u'c6', vendor=u'foo')
        self.session.add_all((computer1, computer2, computer3, computer4,
                                 computer5, computer6))
        self.session.commit()
        # add the computers to three test people
        person1, person2, person3 = self.people[:3]
        person1.computers = [computer1, computer2, computer3]
        person2.computers = [computer4]
        person3.computers = [computer5, computer6]
        self.session.commit()
        # test 'any'
        d = dict(filters=[dict(name='computers__vendor', val=u'foo',
                               op='any')])
        result = search(self.session, self.Person, d)
        assert result.count() == 2
        # test 'has'
        d = dict(filters=[dict(name='owner__name', op='has', val=u'Lincoln')])
        result = search(self.session, self.Computer, d)
        assert result.count() == 3

    def test_has_and_any_suboperators(self):
        """Tests for the ``"has"`` and ``"any"`` operators with suboperators.

        The `any` operator returns all instances for which any related instance
        in a given collection has some property. The `has` operator returns all
        instances for which a related instance has a given property.

        """
        # create test computers
        computer1 = self.Computer(name=u'c1', vendor=u'foo')
        computer2 = self.Computer(name=u'c2', vendor=u'bar')
        computer3 = self.Computer(name=u'c3', vendor=u'bar')
        computer4 = self.Computer(name=u'c4', vendor=u'bar')
        computer5 = self.Computer(name=u'c5', vendor=u'foo')
        computer6 = self.Computer(name=u'c6', vendor=u'foo')
        self.session.add_all((computer1, computer2, computer3, computer4,
                                 computer5, computer6))
        self.session.commit()
        # add the computers to three test people
        person1, person2, person3 = self.people[:3]
        person1.computers = [computer1, computer2, computer3]
        person2.computers = [computer4]
        person3.computers = [computer5, computer6]
        self.session.commit()
        # test 'any'
        val = dict(name='vendor', op='like', val=u'%o%')
        d = dict(filters=[dict(name='computers', op='any', val=val)])
        result = search(self.session, self.Person, d)
        assert result.count() == 2
        # test 'has'
        val=dict(name='name', op='like', val=u'%incol%')
        d = dict(filters=[dict(name='owner', op='has', val=val)])
        result = search(self.session, self.Computer, d)
        assert result.count() == 3

    def test_has_and_any_nested_suboperators(self):
        """Tests for the ``"has"`` and ``"any"`` operators with nested
        suboperators.

        The `any` operator returns all instances for which any related instance
        in a given collection has some property. The `has` operator returns all
        instances for which a related instance has a given property.

        """
        # create test computers
        computer1 = self.Computer(name=u'c1', vendor=u'foo')
        computer2 = self.Computer(name=u'c2', vendor=u'bar')
        computer3 = self.Computer(name=u'c3', vendor=u'bar')
        computer4 = self.Computer(name=u'c4', vendor=u'bar')
        computer5 = self.Computer(name=u'c5', vendor=u'foo')
        computer6 = self.Computer(name=u'c6', vendor=u'foo')
        self.session.add_all((computer1, computer2, computer3, computer4,
                                 computer5, computer6))
        self.session.commit()
        # add the computers to three test people
        person1, person2, person3 = self.people[:3]
        person1.computers = [computer1, computer2, computer3]
        person2.computers = [computer4]
        person3.computers = [computer5, computer6]
        self.session.commit()
        # test 'any'
        innerval = dict(name='name', op='like', val=u'%incol%')
        val = dict(name='owner', op='has', val=innerval)
        d = dict(filters=[dict(name='computers', op='any', val=val)])
        result = search(self.session, self.Person, d)
        assert result.count() == 1
        # test 'has'
        innerval = dict(name='vendor', op='like', val='%o%')
        val = dict(name='computers', op='any', val=innerval)
        d = dict(filters=[dict(name='owner', op='has', val=val)])
        result = search(self.session, self.Computer, d)
        assert result.count() == 5


class TestSearch(TestSupportPrefilled):
    """Unit tests for the :func:`flask_restless.search.search` function.

    The :func:`~flask_restless.search.search` function is a essentially a
    wrapper around the :func:`~flask_restless.search.create_query` function
    which checks whether the parameters of the search indicate that a single
    result is expected.

    """

    def test_search(self):
        """Tests that asking for a single result raises an error unless the
        result of the query truly has only a single element.

        """
        # tests getting multiple results
        d = {'single': True,
             'filters': [{'name': 'name', 'val': u'%y%', 'op': 'like'}]}
        assert_raises(MultipleResultsFound, search, self.session, self.Person,
                      d)

        # tests getting no results
        d = {'single': True,
             'filters': [{'name': 'name', 'val': u'bogusname', 'op': '=='}]}
        assert_raises(NoResultFound, search, self.session, self.Person, d)

        # tests getting exactly one result
        d = {'single': True,
             'filters': [{'name': 'name', 'val': u'Lincoln', 'op': '=='}]}
        result = search(self.session, self.Person, d)
        assert result.name == u'Lincoln'
