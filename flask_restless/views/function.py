# function.py - views for evaluating SQL functions on SQLAlchemy models
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
"""Views for evaluating functions on a SQLAlchemy model.

The main class in this module, :class:`FunctionAPI`, is a
:class:`~flask.MethodView` subclass that creates endpoints for fetching
the result of evaluating a SQL function on a SQLAlchemy model.

"""
from flask import json
from flask import request
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql import func

from ..search import create_filters
from ..search import FilterParsingError
from ..search import FilterCreationError
from .base import error_response
from .base import jsonpify
from .base import ModelView
from .base import SingleKeyError


def create_function_query(session, model, functions):
    """Creates a SQLAlchemy query representing the given SQLAlchemy functions.

    `session` is the SQLAlchemy session in which all database
    transactions will be performed.

    `model` is the SQLAlchemy model class on which the specified
    functions will be evaluated.

    ``functions`` is a non-empty list of dictionaries of the form::

        {'name': 'avg', 'field': 'amount'}

    The return value of this function is a SQLAlchemy query with the
    given functions applied.

    If a field does not exist on a given model, :exc:`AttributeError` is
    raised. If a function does not exist,
    :exc:`sqlalchemy.exc.OperationalError` is raised. The former
    exception will have a ``field`` attribute which is the name of the
    field which does not exist. The latter exception will have a
    ``function`` attribute which is the name of the function with does
    not exist.

    """
    processed = []
    for function in functions:
        if 'name' not in function:
            raise KeyError('Missing `name` key in function object')
        if 'field' not in function:
            raise KeyError('Missing `field` key in function object')
        funcname, fieldname = function['name'], function['field']
        # We retrieve the function by name from the SQLAlchemy ``func``
        # module and the field by name from the model class.
        #
        # If the specified field doesn't exist, this raises AttributeError.
        funcobj = getattr(func, funcname)
        try:
            field = getattr(model, fieldname)
        except AttributeError as exception:
            exception.field = fieldname
            raise exception
        processed.append(funcobj(field))
    return session.query(*processed)


class FunctionAPI(ModelView):
    """Provides method-based dispatching for :http:method:`get` requests which
    wish to apply SQL functions to all instances of a model.

    .. versionadded:: 0.4

    """

    # TODO Currently, this method first creates a query from the given
    # functions, then applies the filters to the query
    # afterwards. However, in SQLAlchemy 1.0.0, we could use the
    # :func:`sqlalchemy.funcfilter` function for backends that support
    # the FILTER clause with aggregate functions.
    def get(self):
        """Returns the result of evaluating the SQL functions specified in the
        body of the request.

        For a description of the request and response formats, see
        :ref:`functionevaluation`.

        """
        # Get the functions list from the query parameters.
        if 'functions' not in request.args:
            detail = 'Must provide `functions` query parameter'
            return error_response(400, detail=detail)
        functions = request.args.get('functions')
        try:
            functions = json.loads(str(functions)) or []
        except (TypeError, ValueError, OverflowError) as exception:
            detail = 'Unable to decode JSON in `functions` query parameter'
            return error_response(400, cause=exception, detail=detail)

        # If there are no functions to execute, simply return the empty list.
        if not functions:
            return jsonpify({'data': []})

        # Create the function query.
        try:
            query = create_function_query(self.session, self.model, functions)
        except AttributeError as exception:
            detail = 'unknown field "{0}"'.format(exception.field)
            return error_response(400, cause=exception, detail=detail)
        except KeyError as exception:
            detail = str(exception)
            return error_response(400, cause=exception, detail=detail)

        # Get the filtering, sorting, and grouping parameters.
        try:
            filters, sort, group_by, single, ignorecase = \
                self.collection_parameters()
        except (TypeError, ValueError, OverflowError) as exception:
            detail = 'Unable to decode filter objects as JSON list'
            return error_response(400, cause=exception, detail=detail)
        except SingleKeyError as exception:
            detail = 'Invalid format for filter[single] query parameter'
            return error_response(400, cause=exception, detail=detail)

        try:
            # Create the filtered query according to the parameters.
            filters = create_filters(self.model, filters)
            # Apply the filters to the query.
            query = query.filter(*filters)
        except (FilterParsingError, FilterCreationError) as exception:
            detail = 'invalid filter object: {0}'.format(str(exception))
            return error_response(400, cause=exception, detail=detail)

        # Evaluate all the functions at once and get a list of results.
        try:
            result = list(query.one())
        except OperationalError as exception:
            # HACK original error message is of the form:
            #
            #    '(OperationalError) no such function: bogusfuncname'
            #
            original_msg = exception.args[0]
            bad_function = original_msg[37:]
            detail = 'unknown function "{0}"'.format(bad_function)
            return error_response(400, cause=exception, detail=detail)

        return jsonpify({'data': result})
