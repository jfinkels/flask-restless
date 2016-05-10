# filters.py - parsing and creation of SQLAlchemy filter expressions
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
"""Functions for parsing and creating SQLAlchemy filter expressions.

The :func:`create_filters` function allows you to create SQLAlchemy
expressions that can be used by the :meth:`sqlalchemy.orm.Query.filter`
method. It parses a dictionary representation of a filter as described
in :doc:`filtering` into an executable SQLAlchemy expression.

The :exc:`FilterParsingError` and :exc:`FilterCreationError` exceptions
provide information about problems that arise from parsing filters and
generating the SQLAlchemy expressions, respectively.

"""
from operator import methodcaller
from functools import partial

from sqlalchemy import and_
from sqlalchemy import not_
from sqlalchemy import or_

from ..helpers import get_related_model_from_attribute
from ..helpers import string_to_datetime
from .operators import create_operation
from .operators import NO_ARGUMENT
from .operators import OperatorCreationError


class FilterCreationError(Exception):
    """Raised when there is a problem creating a SQLAlchemy filter object."""


class FilterParsingError(Exception):
    """Raised if there is a problem parsing a filter object from a
    dictionary into an instance of the :class:`.Filter` class.

    """


class Filter(object):
    """Represents a filter to apply to a SQLAlchemy query object.

    This is an abstract base class. Subclasses must override and
    implement the :meth:`.to_expression` method.

    The :meth:`.to_expression` method returns the SQLAlchemy operator
    expression represented by this filter object.

    """

    def to_expression(self):
        """Returns the SQLAlchemy expression represented by this filter.

        **This method is not implemented in this base class; subclasses
        must override this method.**

        """
        raise NotImplementedError


class FieldFilter(Filter):
    """Represents a filter on a field of a model.

    `field` is the field (i.e. the actual column or relationship object)
    to be placed on the left side of the operator.

    `operator` is a string representing the SQLAlchemy operator to apply
    to the field named by `fieldname`. This must be one of the
    operations named in :mod:`.operators`.

    `argument` is the second argument to the operator, which may be a
    value (such as a string or an integer) or another field object. This
    may also be None in case the operator is unary (such as the "is
    null" operator).

    """

    def __init__(self, field, operator, argument):
        self.field = field
        self.operator = operator
        self.argument = argument

    def __repr__(self):
        s = '<FieldFilter {0} {1} {2}>'
        s = s.format(self.field, self.operator, self.argument)
        return s

    def to_expression(self):
        """Returns the SQLAlchemy expression represented by this filter.

        For example::

            >>> f = FieldFilter(Person.age, '>', 10)
            >>> print(f.to_expression())
            person.age > :age_1
            >>> f = FieldFilter(Person.age, '>', Person.id)
            >>> print(f.to_expression())
            person.age > person.id

        This method raises :exc:`FilterCreationError` if there is a
        problem creating the operator expression.

        """
        argument = self.argument
        # In the case of relationship operators 'has' and 'any', the
        # argument is another Filter object entirely, so we need to
        # recursively generate the expression for that Filter object as
        # well.
        if isinstance(self.argument, Filter):
            argument = self.argument.to_expression()
        try:
            return create_operation(self.field, self.operator, argument)
        except OperatorCreationError as exception:
            raise FilterCreationError(str(exception))


class BooleanFilter(Filter):
    """A Boolean expression comprising other filters.

    This is an abstract base class. Subclasses must override and
    implement the :meth:`.to_expression` method.

    """


class NegationFilter(BooleanFilter):
    """A negation of another filter.

    `subfilter` is the :class:`.Filter` object being negated.

    """

    def __init__(self, subfilter):
        self.subfilter = subfilter

    def __repr__(self):
        return 'not_({0})'.format(repr(self.subfilter))

    def to_expression(self):
        return not_(self.subfilter.to_expression())


class JunctionFilter(Filter):
    """A conjunction or disjunction of other filters.

    This is an abstract base class. Subclasses must override and
    implement the :meth:`.to_expression` method.

    `subfilters` is an iterable of :class:`.Filter` objects.

    """

    def __init__(self, subfilters):
        self.subfilters = subfilters


class ConjunctionFilter(JunctionFilter):
    """A conjunction of other filters."""

    def __repr__(self):
        return 'and_{0}'.format(tuple(map(repr, self.subfilters)))

    def to_expression(self):
        return and_(f.to_expression() for f in self.subfilters)


class DisjunctionFilter(JunctionFilter):
    """A disjunction of other filters."""

    def __repr__(self):
        return 'or_{0}'.format(tuple(map(repr, self)))

    def to_expression(self):
        return or_(f.to_expression() for f in self.subfilters)


def from_dictionary(model, dictionary):
    """Returns a new :class:`Filter` object with arguments parsed from
    `dictionary`.

    `dictionary` is a dictionary of the form::

        {'name': 'age', 'op': 'lt', 'val': 20}

    or::

        {'name': 'age', 'op': 'lt', 'other': 'height'}

    where ``dictionary['name']`` is the name of the field of the model on
    which to apply the operator, ``dictionary['op']`` is the name of the
    operator to apply, ``dictionary['val']`` is the value on the right to
    which the operator will be applied, and ``dictionary['other']`` is the
    name of the other field of the model to which the operator will be
    applied.

    'dictionary' may also be an arbitrary Boolean formula consisting of
    dictionaries such as these. For example::

        {'or':
             [{'and':
                   [dict(name='name', op='like', val='%y%'),
                    dict(name='age', op='ge', val=10)]},
              dict(name='name', op='eq', val='John')
              ]
         }

    The returned object is an instance of a subclass of :class:`Filter`,
    representing the root of the Boolean formula parsed from the given
    dictionary.

    This method raises :exc:`FilterParsingError` if one of several
    possible errors occurs while parsing the dictionary.

    """
    # If there are no ANDs, ORs, and NOTs, we are in the base case
    # of the recursion.
    d = dictionary
    if 'or' not in d and 'and' not in d and 'not' not in d:
        # First, get the field on which to operate.
        if 'name' not in dictionary:
            raise FilterParsingError('missing field name')
        fieldname = dictionary.get('name')
        if not hasattr(model, fieldname):
            message = 'no such field "{0}"'.format(fieldname)
            raise FilterParsingError(message)
        field = getattr(model, fieldname)
        # Next, get the operator to apply to the field.
        if 'op' not in dictionary:
            raise FilterParsingError('missing operator')
        operator = dictionary.get('op')
        # Finally, get the second argument to the operator. The argument
        # may be another field, a simple value, or another filter.
        if 'field' in dictionary:
            otherfield = dictionary.get('field')
            if not hasattr(model, otherfield):
                message = 'no such field "{0}"'.format(otherfield)
                raise FilterParsingError(message)
            argument = getattr(model, otherfield)
            return FieldFilter(field, operator, argument)
        else:
            # We need to be able to distinguish the case of an argument
            # of value ``None`` and the absence of an argument. The
            # `NO_ARGUMENT` constant is a sentinel value that signals
            # the absence of the `val` key in the dicionary.
            argument = dictionary.get('val', NO_ARGUMENT)
            # In the special case that the operator is one of the
            # relationship operators 'has' or 'any', the argument is
            # another filter object entirely, so we need to recursively
            # construct a filter from the argument.
            if operator in ('has', 'any'):
                # Get the remote model of the relationship, since
                # `field` is either an InstrumentedAttribute or an
                # AssociationProxy.
                related_model = get_related_model_from_attribute(field)
                argument = from_dictionary(related_model, argument)
                return FieldFilter(field, operator, argument)
            # HACK: need to deal with the special case of converting dates.
            argument = string_to_datetime(model, fieldname, argument)
            return FieldFilter(field, operator, argument)
    from_dict = partial(from_dictionary, model)
    # If there is an OR or an AND in the dictionary, recurse on the
    # provided list of filters.
    if 'or' in dictionary:
        subfilters = map(from_dict, dictionary.get('or'))
        return DisjunctionFilter(subfilters)
    if 'and' in dictionary:
        subfilters = map(from_dict, dictionary.get('and'))
        return ConjunctionFilter(subfilters)
    # At this point, the only remaining possibility is for 'not'.
    subfilter = dictionary.get('not')
    return NegationFilter(from_dict(subfilter))


def create_filters(model, filters):
    """Returns an iterator over SQLAlchemy filter expressions.

    The objects generated by this function can be provided as the
    positional arguments in an invocation of
    :meth:`sqlalchemy.orm.Query.filter`.

    `model` is the SQLAlchemy model on which the filters will be
    applied.

    `filters` is an iterable of dictionaries representing filter
    objects, as described in the Flask-Restless documentation
    (:ref:`filtering`).

    This function may raise :exc:`FilterParsingError` if there is a
    problem converting a dictionary filter into an intermediate
    representation (the :class:`.Filter` object) and
    :exc:`FilterCreationError` if there is a problem converting the
    intermediate representation into a SQLAlchemy expression.

    """
    from_dict = partial(from_dictionary, model)
    # `Filter.from_dictionary()` converts the dictionary representation
    # of a filter object into an intermediate representation, an
    # instance of :class:`.Filter` that facilitates the construction of
    # the actual SQLAlchemy code in `create_filter` below.
    filters = map(from_dict, filters)
    # Each of these function calls may raise a FilterCreationError.
    #
    # TODO In Python 3.3+, this should be `yield from ...`.
    return map(methodcaller('to_expression'), filters)
