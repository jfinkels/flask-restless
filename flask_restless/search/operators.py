# operators.py - parsing and creation of SQLAlchemy operators
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
"""Functions for parsing and creating SQLAlchemy operators.

The :func:`create_operation` function allows you to create a single
SQLAlchemy operation that can be used by the
:meth:`sqlalchemy.orm.Query.filter` method. The
:exc:`.OperatorCreationError` exception is raised when there is a problem
creating the expression.

"""
#: Special symbol that represents the absence of a `val` element in a
#: dictionary representing a filter object.
NO_ARGUMENT = object()


class OperatorCreationError(Exception):
    """Raised when there is a problem creating an operator expression."""


def is_null(arg):
    # This is intentionally `arg == None` instead of `arg is None`
    # because that's how SQLAlchemy expects a comparison to NULL. The
    # same comment goes for the `is_not_null` function below.
    return arg == None  # NOQA


def is_not_null(arg):
    return arg != None  # NOQA


def equals(arg1, arg2):
    return arg1 == arg2


def not_equals(arg1, arg2):
    return arg1 != arg2


def greater_than(arg1, arg2):
    return arg1 > arg2


def greater_than_equals(arg1, arg2):
    return arg1 >= arg2


def less_than(arg1, arg2):
    return arg1 < arg2


def less_than_equals(arg1, arg2):
    return arg1 <= arg2


def generic_op(arg1, arg2, op):
    return arg1.op(op)(arg2)


def inet_is_contained_by(arg1, arg2):
    return generic_op(arg1, arg2, '<<')


def inet_is_contained_by_or_equals(arg1, arg2):
    return generic_op(arg1, arg2, '<<=')


def inet_contains(arg1, arg2):
    return generic_op(arg1, arg2, '>>')


def inet_contains_or_equals(arg1, arg2):
    return generic_op(arg1, arg2, '>>=')


def inet_not_equals(arg1, arg2):
    return generic_op(arg1, arg2, '<>')


def inet_contains_or_is_contained_by(arg1, arg2):
    return generic_op(arg1, arg2, '&&')


def ilike(arg1, arg2):
    return arg1.ilike(arg2)


def like(arg1, arg2):
    return arg1.like(arg2)


def not_like(arg1, arg2):
    return ~arg1.like(arg2)


def in_(arg1, arg2):
    return arg1.in_(arg2)


def not_in(arg1, arg2):
    return ~arg1.in_(arg2)


def has(arg1, arg2):
    return arg1.has(arg2)


def any_(arg1, arg2):
    return arg1.any(arg2)


#: Operator functions keyed by name.
#:
#: Each of these functions accepts either one or two arguments. The
#: first argument is the field object on which to apply the operator.
#: The second argument, where it exists, is the second argument to the
#: operator.
#:
#: Some operations have multiple names. For example, the equality
#: operation can be described by the strings '==', 'eq', 'equals', etc.
OPERATORS = {
    # Unary operators.
    'is_null': is_null,
    'is_not_null': is_not_null,
    # Binary operators.
    '==': equals,
    'eq': equals,
    'equals': equals,
    'equal_to': equals,
    '!=': not_equals,
    'ne': not_equals,
    'neq': not_equals,
    'not_equal_to': not_equals,
    'does_not_equal': not_equals,
    '>': greater_than,
    'gt': greater_than,
    '<': less_than,
    'lt': less_than,
    '>=': greater_than_equals,
    'ge': greater_than_equals,
    'gte': greater_than_equals,
    'geq': greater_than_equals,
    '<=': less_than_equals,
    'le': less_than_equals,
    'lte': less_than_equals,
    'leq': less_than_equals,
    '<<': inet_is_contained_by,
    '<<=': inet_is_contained_by_or_equals,
    '>>': inet_contains,
    '>>=': inet_contains_or_equals,
    '<>': inet_not_equals,
    '&&': inet_contains_or_is_contained_by,
    'ilike': ilike,
    'like': like,
    'not_like': not_like,
    'in': in_,
    'not_in': not_in,
    # (Binary) relationship operators.
    'has': has,
    'any': any_,
}


def register_operator(name, op):
    """Register an operator so the system can create expressions involving it.

    `name` is a string naming the operator and `op` is a function that
    takes up to two arguments as input. If the name provided is one of
    the built-in operators (see :ref:`operators`), it will override the
    default behavior of that operator. For example, calling ::

        register_operator('gt', myfunc)

    will cause ``myfunc()`` to be invoked in the SQLAlchemy expression
    created for this operator instead of the default "greater than"
    operator.

    """
    OPERATORS[name] = op


def create_operation(arg1, operator, arg2):
    """Creates a SQLAlchemy expression for the given operation.

    More specifically, this translates the string representation of an
    operation, for example 'gt', to an expression corresponding to a
    SQLAlchemy expression, ``arg1 > arg2``. The recognized operators are
    given by the keys of :data:`OPERATORS`. For more information on
    recognized search operators, see :doc:`filtering`.

    `operator` is a string representating the operation which will be
     executed between the field and the argument received. For example,
     'gt', 'lt', 'like', 'in', 'has', etc. `operator` must not be
     None. If the operator is unknown, an :exc:`OperatorCreationError`
     exception is raised.

    `arg1` and `arg2` are the arguments to the operator. If the operator
    is unary, like the 'is_null' operator, then the second argument is
    ignored. Calling code may provide :data:`NO_ARGUMENT` as the second
    argument in case no argument was provided by the ultimate end
    user. If the operator expects two arguments but `arg2 is
    :data:`NO_ARGUMENT`, an :exc:`OperatorCreationError` is
    raised. Also, the same exception is raised if the operator expects
    two arguments but `arg2` is None, since comparisons to ``NULL``
    should use the 'is_null' or 'is_not_null' unary operators instead.

    """
    if operator not in OPERATORS:
        raise OperatorCreationError('unknown operator "{0}"'.format(operator))
    opfunc = OPERATORS[operator]
    # If the operator is a comparison to null, the function is unary.
    if opfunc in (is_null, is_not_null):
        # In this case we expect the argument to be `NO_ARGUMENT`.
        # However, we don't explicitly check this, we just ignore
        # whatever argument was provided.
        return opfunc(arg1)
    # Otherwise, the function will accept two arguments.
    #
    # If None is given as an argument, the user is trying to compare a
    # value to NULL, so we politely suggest using the unary `is_null` or
    # `is_not_null` operators intead.
    #
    # It is also possible that no argument was given (as opposed to an
    # argument of `None`), as indicated by an argument of value
    # `NO_ARGUMENT`. This should happen only when the operator is unary,
    # so we raise an exception in that case as well.
    if arg2 is None:
        message = ('To compare a value to NULL, use the unary'
                   ' is_null/is_not_null operators.')
        raise OperatorCreationError(message)
    if arg2 is NO_ARGUMENT:
        msg = 'expected an argument for this operator but none was given'
        raise OperatorCreationError(msg)
    return opfunc(arg1, arg2)
