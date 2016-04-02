# helpers.py - helper functions for view classes
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
"""Helper functions for view classes."""
from sqlalchemy.exc import OperationalError
from sqlalchemy.inspection import inspect as sqlalchemy_inspect
from sqlalchemy.sql import func


def upper_keys(dictionary):
    """Returns a new dictionary with the keys of ``dictionary``
    converted to upper case and the values left unchanged.

    """
    # In Python 3, this should be
    #
    #     return {k.upper(): v for k, v in dictionary.items()}
    #
    return dict((k.upper(), v) for k, v in dictionary.items())


def evaluate_functions(session, model, functions):
    """Executes each of the SQLAlchemy functions specified in ``functions``, a
    list of dictionaries of the form described below, on the given model and
    returns a dictionary mapping function name (slightly modified, see below)
    to result of evaluation of that function.

    `session` is the SQLAlchemy session in which all database transactions will
    be performed.

    `model` is the SQLAlchemy model class on which the specified functions will
    be evaluated.

    ``functions`` is a list of dictionaries of the form::

        {'name': 'avg', 'field': 'amount'}

    For example, if you want the sum and the average of the field named
    "amount"::

        >>> # assume instances of Person exist in the database...
        >>> f1 = dict(name='sum', field='amount')
        >>> f2 = dict(name='avg', field='amount')
        >>> evaluate_functions(Person, [f1, f2])
        {'avg__amount': 456, 'sum__amount': 123}

    The return value is a dictionary mapping ``'<funcname>__<fieldname>'`` to
    the result of evaluating that function on that field. If `model` is
    ``None`` or `functions` is empty, this function returns the empty
    dictionary.

    If a field does not exist on a given model, :exc:`AttributeError` is
    raised. If a function does not exist,
    :exc:`sqlalchemy.exc.OperationalError` is raised. The former exception will
    have a ``field`` attribute which is the name of the field which does not
    exist. The latter exception will have a ``function`` attribute which is the
    name of the function with does not exist.

    """
    if not model or not functions:
        return []
    processed = []
    # funcnames = []
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
        # Store the functions that will be executed in the database.
        # funcnames.append('{0}__{1}'.format(funcname, fieldname))
        processed.append(funcobj(field))
    # Evaluate all the functions at once and get an iterable of results.
    try:
        evaluated = session.query(*processed).one()
    except OperationalError as exception:
        # HACK original error message is of the form:
        #
        #    '(OperationalError) no such function: bogusfuncname'
        #
        original_error_msg = exception.args[0]
        bad_function = original_error_msg[37:]
        exception.function = bad_function
        raise exception
    return list(evaluated)


def count(session, query):
    """Returns the count of the specified `query`.

    This function employs an optimization that bypasses the
    :meth:`sqlalchemy.orm.Query.count` method, which can be very slow
    for large queries.

    """
    counts = query.selectable.with_only_columns([func.count()])
    num_results = session.execute(counts.order_by(None)).scalar()
    if num_results is None or query._limit is not None:
        return query.order_by(None).count()
    return num_results


def changes_on_update(model):
    """Returns a best guess at whether the specified SQLAlchemy model class is
    modified on updates.

    We guess whether this happens by checking whether any columns of model have
    the :attr:`sqlalchemy.Column.onupdate` attribute set.

    """
    return any(column.onupdate is not None
               for column in sqlalchemy_inspect(model).columns)
