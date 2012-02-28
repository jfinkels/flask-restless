# -*- coding: utf-8; Mode: Python -*-
#
# Copyright (C) 2011 Lincoln de Sousa <lincoln@comum.org>
# Copyright 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Provides querying, searching, and function evaluation on Elixir models.

:copyright:2011 by Lincoln de Sousa <lincoln@comum.org>
:copyright:2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
:license: AGPLv3, see COPYTING for more details

"""

from elixir import session
from sqlalchemy.sql import func

__all__ = ['create_query', 'evaluate_functions', 'search']

OPERATORS = {
    '==': lambda f, a, fn: f == a,
    'eq': lambda f, a, fn: f == a,
    'equals': lambda f, a, fn: f == a,
    'equal_to': lambda f, a, fn: f == a,
    '!=': lambda f, a, fn: f != a,
    'neq': lambda f, a, fn: f != a,
    'not_equal_to': lambda f, a, fn: f != a,
    'does_not_equal': lambda f, a, fn: f != a,
    '>': lambda f, a, fn: f > a,
    'gt': lambda f, a, fn: f > a,
    '<': lambda f, a, fn: f < a,
    'lt': lambda f, a, fn: f < a,
    '>=': lambda f, a, fn: f >= a,
    'gte': lambda f, a, fn: f >= a,
    '<=': lambda f, a, fn: f <= a,
    'lte': lambda f, a, fn: f <= a,
    'like': lambda f, a, fn: f.like(a),
    'in': lambda f, a, fn: f.in_(a),
    'not_in': lambda f, a, fn: ~f.in_(a),
    'is_null': lambda f, a, fn: f == None,
    'is_not_null': lambda f, a, fn: f != None,
    'desc': lambda f, a, fn: f.desc,
    'asc': lambda f, a, fn: f.asc,
    'has': lambda f, a, fn: f.has(**{fn: a}),
    'any': lambda f, a, fn: f.any(**{fn: a})
}
"""The mapping from operator name (as accepted by the search method) to a
function which returns the SQLAlchemy expression corresponding to that
operator.

The function in each of the values takes three arguments. The first argument is
the field object on which to apply the operator. The second argument is the
second argument to the operator, should one exist. The third argument is the
name of the field. All functions use the first argument, some use the second,
and few use the third.

Some operations have multiple names. For example, the equality operation can be
described by the strings ``'=='``, ``'eq'``, ``'equals'``, etc.

"""


class IllegalArgumentError(Exception):
    pass


class OrderBy(object):
    def __init__(self, field, direction='asc'):
        self.field = field
        self.direction = direction

    def __repr__(self):
        return '<OrderBy {}, {}>'.format(self.field, self.direction)


class Filter(object):
    def __init__(self, fieldname, operator, argument=None, otherfield=None):
        if (argument and otherfield) or not (argument or otherfield):
            raise IllegalArgumentError('Must specify exactly one of argument'
                                       ' and otherfield')
        self.fieldname = fieldname
        self.operator = operator
        self.argument = argument
        self.otherfield = otherfield

    def __repr__(self):
        return '<Filter {} {} {}>'.format(self.fieldname, self.operator,
                                          self.argument or self.otherfield)

    @staticmethod
    def from_dictionary(dictionary):
        fieldname = dictionary.get('name')
        operator = dictionary.get('op')
        argument = dictionary.get('val')
        otherfield = dictionary.get('field')
        return Filter(fieldname, operator, argument, otherfield)


class SearchParameters(object):
    def __init__(self, filters=[], searchtype=None, limit=None, offset=None,
                 order_by=[]):
        self.filters = filters
        self.searchtype = searchtype
        self.limit = limit
        self.offset = offset
        self.order_by = order_by

    def __repr__(self):
        return ('<SearchParameters filters={}, order_by={}, limit={},'
                ' offset={}, type={}>').format(self.filters, self.order_by,
                                               self.limit, self.offset,
                                               self.searchtype)

    @staticmethod
    def from_dictionary(dictionary):
        # for the sake of brevity...
        from_dict = Filter.from_dictionary
        filters = [from_dict(f) for f in dictionary.get('filters', [])]
        order_by = [OrderBy(**o) for o in dictionary.get('order_by', [])]
        searchtype = dictionary.get('type')
        limit = dictionary.get('limit')
        offset = dictionary.get('offset')
        return SearchParameters(filters=filters, searchtype=searchtype,
                                limit=limit, offset=offset, order_by=order_by)


class QueryBuilder(object):

    @staticmethod
    def _create_operation(model, fieldname, operator, argument, relation=None):
        """Translates an operation described as a string to a valid SQLAlchemy
        query parameter using a field or relation of the specified model.

        More specifically, this translates the string representation of an
        operation, for example ``'gt'``, to an expression corresponding to a
        SQLAlchemy expression, ``field > argument``. The recognized operators
        are given by the keys of :data:`OPERATORS`.

        If ``relation`` is not ``None``, the returned search parameter will
        correspond to a search on the field named ``fieldname`` on the entity
        related to ``model`` whose name, as a string, is ``relation``.

        ``model`` is an instance of a :class:`elixir.entity.Entity` being
        searched.

        ``fieldname`` is the name of the field of ``model`` to which the
        operation will be applied as part of the search. If ``relation`` is
        specified, the operation will be applied to the field with name
        ``fieldname`` on the entity related to ``model`` whose name, as a
        string, is ``relation``.

        ``operation`` is a string representating the operation which will be
         executed between the field and the argument received. For example,
         ``'gt'``, ``'lt'``, ``'like'``, ``'in'`` etc.

        ``argument`` is the argument to which to apply the ``operator``.

        ``relation`` is the name of the relationship attribute of ``model`` to
        which the operation will be applied as part of the search, or ``None``
        if this function should not use a related entity in the search.

        """
        field = getattr(model, relation or fieldname)
        return OPERATORS.get(operator)(field, argument, fieldname)

    @staticmethod
    def _extract_operators(model, search_params):
        """Returns the list of operations on ``model`` specified in the
        :attr:`filters` attribute on the ``search_params`` object.

        ``search_params`` is an instance of the :class:`SearchParameters`
        class whose fields represent the parameters of the search.

        """
        operations = []
        for f in search_params.filters:
            fname = f.fieldname
            val = f.argument

            # get the relationship from the field name, if it exists
            # TODO document that field names must not contain "__"
            relation = None
            if '__' in fname:
                relation, fname = fname.split('__')

            # for the sake of brevity
            makeop = QueryBuilder._create_operation
            # We are going to compare a field with another one, so there's
            # no reason to parse
            if f.otherfield:
                otherfield = getattr(model, f.otherfield)
                param = makeop(model, fname, f.operator, otherfield, relation)
                operations.append(param)
                continue

            # Collecting the query
            param = makeop(model, fname, f.operator, val, relation)
            operations.append(param)

        return operations

    @staticmethod
    def create_query(model, search_params):
        """Builds an SQLAlchemy query instance based on the search parameters
        present in ``search_params``, an instance of :class:`SearchParameters`.

        This method returns a SQLAlchemy query in which all matched instances
        meet the requirements specified in ``search_params``.

        ``model`` is an :class:`elixir.entity.Entity` on which to create a
        query.

        ``search_params`` is an instance of :class:`SearchParameters` which
        specify the filters, order, limit, offset, etc. of the query.

        Building the query proceeds in this order:
        1. filtering the query
        2. ordering the query
        3. limiting the query
        4. offsetting the query

        """
        # Adding field filters
        query = model.query
        operations = QueryBuilder._extract_operators(model, search_params)
        for i in operations:
            query = query.filter(i)

        # Order the search
        for val in search_params.order_by:
            field = getattr(model, val.field)
            direction = getattr(field, val.direction)
            query = query.order_by(direction())

        # Limit it
        if search_params.limit:
            query = query.limit(search_params.limit)
        if search_params.offset:
            query = query.offset(search_params.offset)
        return query


def evaluate_functions(model, functions):
    """Executes the each of the SQLAlchemy functions specified in
    ``functions``, a list of dictionaries of the form described below, on the
    given model and returns a dictionary mapping function name (slightly
    modified, see below) to result of evaluation of that function.

    ``functions`` is a list of dictionaries of the form::

        {'name': 'avg', 'field': 'amount'}

    For example, if you want the sum and the average of the field named
    "amount"::

        >>> # assume instances of Person exist in the database...
        >>> f1 = dict(name='sum', field='amount')
        >>> f2 = dict(name='avg', field='amount')
        >>> evaluate_functions(Person, [f1, f2])
        {'avg__amount': 456, 'sum__amount': 123}

    The return value is a dictionary mapping ``'<funcname>__<fieldname>'``
    to the result of evaluating that function on that field.

    """
    processed = []
    funcnames = []
    for f in functions:
        # We retrieve the function by name from the SQLAlchemy ``func``
        # module and the field by name from the model class.
        funcobj = getattr(func, f['name'])
        field = getattr(model, f['field'])
        # Time to store things to be executed. The processed list stores
        # functions that will be executed in the database and funcnames
        # contains names of the entries that will be returned to the
        # caller.
        funcnames.append('{}__{}'.format(f['name'], f['field']))
        processed.append(funcobj(field))
    # evaluate all the functions at once and get an iterable of results
    evaluated = session.query(*processed).one()
    return dict(zip(funcnames, evaluated))


def create_query(model, searchparams):
    """Returns a SQLAlchemy query object on the given ``model`` where the
    search for the query is defined by ``searchparams``.

    The returned query matches the set of all instances of ``model`` which meet
    the parameters of the search given by ``searchparams``. For more
    information on search parameters, see :ref:`search`.

    ``model`` is a :class:`elixir.Entity` representing the database model to
    query.

    ``searchparams`` is either a dictionary (as parsed from a JSON request from
    the client, for example) or a :class:`SearchParameters` instance defining
    the parameters of the query (as returned by
    :func:`SearchParameters.from_dictionary`, for example).

    """
    if isinstance(searchparams, dict):
        searchparams = SearchParameters.from_dictionary(searchparams)
    return QueryBuilder.create_query(model, searchparams)


def search(model, search_params):
    """Performs the search specified by the given parameters on the model
    specified in the constructor of this class.

    This function essentially calls :func:`create_query` to create a query
    which matches the set of all instances of ``model`` which meet the search
    parameters defined in ``search_params``, then returns all results (or just
    one if ``search_params['type'] == 'one'``).

    This function returns a single instance of the model matching the search
    parameters if the type of the search is ``'one'``, or a list of all such
    instances otherwise.

    ``model`` is a :class:`elixir.Entity` representing the database model to
    query.

    ``search_params`` is a dictionary containing all available search
    parameters. For more information on available search parameters, see
    :ref:`search`.

    If ``search_params`` specifies that the type of the search is
    ``'one'``, then this method will raise
    :exc:`sqlalchemy.orm.exc.NoResultFound` if no results are found and
    :exc:`sqlalchemy.orm.exc.MultipleResultsFound` if multiple results are
    found.

    """
    query = create_query(model, search_params)
    if search_params.get('type') == 'one':
        # may raise NoResultFound or MultipleResultsFound
        return query.one()
    else:
        return query.all()
