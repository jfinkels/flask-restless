"""
    flask.ext.restless.search
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    Provides querying, searching, and function evaluation on SQLAlchemy models.

    The most important functions in this module are the :func:`create_query`
    and :func:`search` functions, which create a SQLAlchemy query object and
    execute that query on a given model, respectively.

    :copyright: 2011 by Lincoln de Sousa <lincoln@comum.org>
    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
import inspect

from .helpers import unicode_keys_to_strings

#: The mapping from operator name (as accepted by the search method) to a
#: function which returns the SQLAlchemy expression corresponding to that
#: operator.
#:
#: Each of these functions accepts either one, two, or three arguments. The
#: first argument is the field object on which to apply the operator. The
#: second argument, where it exists, is the second argument to the operator.
#: The third argument, where it exists, is the name of the field.
#:
#: Some operations have multiple names. For example, the equality operation can
#: be described by the strings ``'=='``, ``'eq'``, ``'equals'``, etc.
OPERATORS = {
    # Operators which accept a single argument.
    'is_null': lambda f: f == None,
    'is_not_null': lambda f: f != None,
    # TODO what are these?
    'desc': lambda f: f.desc,
    'asc': lambda f: f.asc,
    # Operators which accept two arguments.
    '==': lambda f, a: f == a,
    'eq': lambda f, a: f == a,
    'equals': lambda f, a: f == a,
    'equal_to': lambda f, a: f == a,
    '!=': lambda f, a: f != a,
    'ne': lambda f, a: f != a,
    'neq': lambda f, a: f != a,
    'not_equal_to': lambda f, a: f != a,
    'does_not_equal': lambda f, a: f != a,
    '>': lambda f, a: f > a,
    'gt': lambda f, a: f > a,
    '<': lambda f, a: f < a,
    'lt': lambda f, a: f < a,
    '>=': lambda f, a: f >= a,
    'ge': lambda f, a: f >= a,
    'gte': lambda f, a: f >= a,
    'geq': lambda f, a: f >= a,
    '<=': lambda f, a: f <= a,
    'le': lambda f, a: f <= a,
    'lte': lambda f, a: f <= a,
    'leq': lambda f, a: f <= a,
    'ilike': lambda f, a: f.ilike(a),
    'like': lambda f, a: f.like(a),
    'in': lambda f, a: f.in_(a),
    'not_in': lambda f, a: ~f.in_(a),
    # Operators which accept three arguments.
    # HACK For Python 2.5, unicode dictionary keys are not allowed.
    'has': lambda f, a, fn: f.has(**{str(fn): a}),
    'any': lambda f, a, fn: f.any(**{str(fn): a})
}


class OrderBy(object):
    """Represents an "order by" in a SQL query expression."""

    def __init__(self, field, direction='asc'):
        """Instantiates this object with the specified attributes.

        `field` is the name of the field by which to order the result set.

        `direction` is either ``'asc'`` or ``'desc'``, for "ascending" and
        "descending", respectively.

        """
        self.field = field
        self.direction = direction

    def __repr__(self):
        """Returns a string representation of this object."""
        return '<OrderBy {}, {}>'.format(self.field, self.direction)


class Filter(object):
    """Represents a filter to apply to a SQL query.

    A filter can be, for example, a comparison operator applied to a field of a
    model and a value or a comparison applied to two fields of the same
    model. For more information on possible filters, see :ref:`search`.

    """

    def __init__(self, fieldname, operator, argument=None, otherfield=None):
        """Instantiates this object with the specified attributes.

        `fieldname` is the name of the field of a model which will be on the
        left side of the operator.

        `operator` is the string representation of an operator to apply. The
        full list of recognized operators can be found at :ref:`search`.

        If `argument` is specified, it is the value to place on the right side
        of the operator. If `otherfield` is specified, that field on the model
        will be placed on the right side of the operator.

        .. admonition:: About `argument` and `otherfield`

           Some operators don't need either argument and some need exactly one.
           However, this constructor will not raise any errors or otherwise
           inform you of which situation you are in; it is basically just a
           named tuple. Calling code must handle errors caused by missing
           required arguments.

        """
        self.fieldname = fieldname
        self.operator = operator
        self.argument = argument
        self.otherfield = otherfield

    def __repr__(self):
        """Returns a string representation of this object."""
        return '<Filter {} {} {}>'.format(self.fieldname, self.operator,
                                          self.argument or self.otherfield)

    @staticmethod
    def from_dictionary(dictionary):
        """Returns a new :class:`Filter` object with arguments parsed from
        `dictionary`.

        `dictionary` is a dictionary of the form::

            {'name': 'age', 'op': 'lt', 'val': 20}

        or::

            {'name': 'age', 'op': 'lt', 'other': height}

        where ``dictionary['name']`` is the name of the field of the model on
        which to apply the operator, ``dictionary['op']`` is the name of the
        operator to apply, ``dictionary['val']`` is the value on the right to
        which the operator will be applied, and ``dictionary['other']`` is the
        name of the other field of the model to which the operator will be
        applied.

        """
        fieldname = dictionary.get('name')
        operator = dictionary.get('op')
        argument = dictionary.get('val')
        otherfield = dictionary.get('field')
        return Filter(fieldname, operator, argument, otherfield)


class SearchParameters(object):
    """Aggregates the parameters for a search, including filters, search type,
    limit, offset, and order by directives.

    """

    def __init__(self, filters=None, limit=None, offset=None, order_by=None):
        """Instantiates this object with the specified attributes.

        `filters` is a list of :class:`Filter` objects, representing filters to
        be applied during the search.

        `limit`, if not ``None``, specifies the maximum number of results to
        return in the search.

        `offset`, if not ``None``, specifies the number of initial results to
        skip in the result set.

        `order_by` is a list of :class:`OrderBy` objects, representing the
        ordering directives to apply to the result set which matches the
        search.

        """
        self.filters = filters or []
        self.limit = limit
        self.offset = offset
        self.order_by = order_by or []

    def __repr__(self):
        """Returns a string representation of the search parameters."""
        return ('<SearchParameters filters={}, order_by={}, limit={},'
                ' offset={}>').format(self.filters, self.order_by, self.limit,
                                      self.offset)

    @staticmethod
    def from_dictionary(dictionary):
        """Returns a new :class:`SearchParameters` object with arguments parsed
        from `dictionary`.

        `dictionary` is a dictionary of the form::

            {
              'filters': [{'name': 'age', 'op': 'lt', 'val': 20}, ...],
              'order_by': [{'field': 'age', 'direction': 'desc'}, ...]
              'limit': 10,
              'offset': 3
            }

        where ``dictionary['filters']`` is the list of :class:`Filter` objects
        (in dictionary form), ``dictionary['order_by']`` is the list of
        :class:`OrderBy` objects (in dictionary form), ``dictionary['limit']``
        is the maximum number of matching entries to return, and
        ``dictionary['offset']`` is the number of initial entries to skip in
        the matching result set.

        The provided dictionary may have other key/value pairs, but they are
        ignored.

        """
        # for the sake of brevity...
        from_dict = Filter.from_dictionary
        filters = [from_dict(f) for f in dictionary.get('filters', [])]
        # HACK In Python 2.5, unicode dictionary keys are not allowed.
        order_by_list = dictionary.get('order_by', [])
        order_by_list = (unicode_keys_to_strings(o) for o in order_by_list)
        order_by = [OrderBy(**o) for o in order_by_list]
        limit = dictionary.get('limit')
        offset = dictionary.get('offset')
        return SearchParameters(filters=filters, limit=limit, offset=offset,
                                order_by=order_by)


class QueryBuilder(object):
    """Provides a static function for building a SQLAlchemy query object based
    on a :class:`SearchParameters` instance.

    Use the static :meth:`create_query` method to create a SQLAlchemy query on
    a given model.

    """

    @staticmethod
    def _create_operation(model, fieldname, operator, argument, relation=None):
        """Translates an operation described as a string to a valid SQLAlchemy
        query parameter using a field or relation of the specified model.

        More specifically, this translates the string representation of an
        operation, for example ``'gt'``, to an expression corresponding to a
        SQLAlchemy expression, ``field > argument``. The recognized operators
        are given by the keys of :data:`OPERATORS`. For more information on
        recognized search operators, see :ref:`search`.

        If `relation` is not ``None``, the returned search parameter will
        correspond to a search on the field named `fieldname` on the entity
        related to `model` whose name, as a string, is `relation`.

        `model` is an instance of a SQLAlchemy declarative model being
        searched.

        `fieldname` is the name of the field of `model` to which the operation
        will be applied as part of the search. If `relation` is specified, the
        operation will be applied to the field with name `fieldname` on the
        entity related to `model` whose name, as a string, is `relation`.

        `operation` is a string representating the operation which will be
         executed between the field and the argument received. For example,
         ``'gt'``, ``'lt'``, ``'like'``, ``'in'`` etc.

        `argument` is the argument to which to apply the `operator`.

        `relation` is the name of the relationship attribute of `model` to
        which the operation will be applied as part of the search, or ``None``
        if this function should not use a related entity in the search.

        This function raises the following errors:
        * :exc:`KeyError` if the `operator` is unknown (that is, not in
          :data:`OPERATORS`)
        * :exc:`TypeError` if an incorrect number of arguments are provided for
          the operation (for example, if `operation` is `'=='` but no
          `argument` is provided)
        * :exc:`AttributeError` if no column with name `fieldname` or
          `relation` exists on `model`

        """
        # raises KeyError if operator not in OPERATORS
        opfunc = OPERATORS[operator]
        argspec = inspect.getargspec(opfunc)
        # in Python 2.6 or later, this should be `argspec.args`
        numargs = len(argspec[0])
        # raises AttributeError if `fieldname` or `relation` does not exist
        field = getattr(model, relation or fieldname)
        # each of these will raise a TypeError if the wrong number of argments
        # is supplied to `opfunc`.
        if numargs == 1:
            return opfunc(field)
        if argument is None:
            raise TypeError
        if numargs == 2:
            return opfunc(field, argument)
        return opfunc(field, argument, fieldname)

    @staticmethod
    def _create_filters(model, search_params):
        """Returns the list of operations on `model` specified in the
        :attr:`filters` attribute on the `search_params` object.

        `search-params` is an instance of the :class:`SearchParameters` class
        whose fields represent the parameters of the search.

        Raises one of :exc:`AttributeError`, :exc:`KeyError`, or
        :exc:`TypeError` if there is a problem creating the query. See the
        documentation for :func:`_create_operation` for more information.

        """
        filters = []
        for filt in search_params.filters:
            fname = filt.fieldname
            val = filt.argument
            # get the relationship from the field name, if it exists
            relation = None
            if '__' in fname:
                relation, fname = fname.split('__')
            # get the other field to which to compare, if it exists
            if filt.otherfield:
                val = getattr(model, filt.otherfield)
            # for the sake of brevity...
            create_op = QueryBuilder._create_operation
            param = create_op(model, fname, filt.operator, val, relation)
            filters.append(param)
        return filters

    @staticmethod
    def create_query(session, model, search_params):
        """Builds an SQLAlchemy query instance based on the search parameters
        present in ``search_params``, an instance of :class:`SearchParameters`.

        This method returns a SQLAlchemy query in which all matched instances
        meet the requirements specified in ``search_params``.

        `model` is SQLAlchemy declarative model on which to create a query.

        `search_params` is an instance of :class:`SearchParameters` which
        specify the filters, order, limit, offset, etc. of the query.

        Building the query proceeds in this order:
        1. filtering the query
        2. ordering the query
        3. limiting the query
        4. offsetting the query

        Raises one of :exc:`AttributeError`, :exc:`KeyError`, or
        :exc:`TypeError` if there is a problem creating the query. See the
        documentation for :func:`_create_operation` for more information.

        """
        # Adding field filters
        query = session.query(model)
        # may raise exception here
        filters = QueryBuilder._create_filters(model, search_params)
        for filt in filters:
            query = query.filter(filt)

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


def create_query(session, model, searchparams):
    """Returns a SQLAlchemy query object on the given `model` where the search
    for the query is defined by `searchparams`.

    The returned query matches the set of all instances of `model` which meet
    the parameters of the search given by `searchparams`. For more information
    on search parameters, see :ref:`search`.

    `model` is a SQLAlchemy declarative model representing the database model
    to query.

    `searchparams` is either a dictionary (as parsed from a JSON request from
    the client, for example) or a :class:`SearchParameters` instance defining
    the parameters of the query (as returned by
    :func:`SearchParameters.from_dictionary`, for example).

    """
    if isinstance(searchparams, dict):
        searchparams = SearchParameters.from_dictionary(searchparams)
    return QueryBuilder.create_query(session, model, searchparams)


def search(session, model, search_params):
    """Performs the search specified by the given parameters on the model
    specified in the constructor of this class.

    This function essentially calls :func:`create_query` to create a query
    which matches the set of all instances of ``model`` which meet the search
    parameters defined in ``search_params``, then returns all results (or just
    one if ``search_params['single'] == True``).

    This function returns a single instance of the model matching the search
    parameters if ``search_params['single']`` is ``True``, or a list of all
    such instances otherwise. If ``search_params['single']`` is ``True``, then
    this method will raise :exc:`sqlalchemy.orm.exc.NoResultFound` if no
    results are found and :exc:`sqlalchemy.orm.exc.MultipleResultsFound` if
    multiple results are found.

    `model` is a SQLAlchemy declarative model class representing the database
    model to query.

    `search_params` is a dictionary containing all available search
    parameters. For more information on available search parameters, see
    :ref:`search`. Implementation note: this dictionary will be converted to a
    :class:`SearchParameters` object when the :func:`create_query` function is
    called.

    """
    # `is_single` is True when 'single' is a key in ``search_params`` and its
    # corresponding value is anything except those values which evaluate to
    # False (False, 0, the empty string, the empty list, etc.).
    is_single = search_params.get('single')
    query = create_query(session, model, search_params)
    if is_single:
        # may raise NoResultFound or MultipleResultsFound
        return query.one()
    return query.all()
