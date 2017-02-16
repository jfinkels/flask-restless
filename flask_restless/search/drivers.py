# drivers.py - high-level functions for filtering SQLAlchemy queries
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
"""High-level functions for creating filtered SQLAlchemy queries.

The :func:`search` and :func:`search_relationship` functions return
filtered queries on a SQLAlchemy model. The latter specifically
restricts the query to only those instances of a model that are related
to a particular object via a given to-many relationship.

"""
from sqlalchemy.orm import aliased
from sqlalchemy.sql import false as FALSE

from ..helpers import get_model
from ..helpers import get_related_model
from ..helpers import primary_key_names
from ..helpers import primary_key_value
from ..helpers import session_query
from .filters import create_filters


def search_relationship(session, instance, relation, filters=None, sort=None,
                        group_by=None, ignorecase=False):
    """Returns a filtered, sorted, and grouped SQLAlchemy query
    restricted to those objects related to a given instance.

    `session` is the SQLAlchemy session in which to create the query.

    `instance` is an instance of a SQLAlchemy model whose relationship
    will be queried.

`   `relation` is a string naming a to-many relationship of `instance`.

    `filters`, `sort`, `group_by`, and `ignorecase` are identical to the
    corresponding arguments of :func:`.search`.

    """
    model = get_model(instance)
    related_model = get_related_model(model, relation)
    query = session_query(session, related_model)

    # Filter by only those related values that are related to `instance`.
    relationship = getattr(instance, relation)
    # TODO In Python 2.7+, this should be a set comprehension.
    primary_keys = set(primary_key_value(inst) for inst in relationship)
    # If the relationship is empty, we can avoid a potentially expensive
    # filtering operation by simply returning an intentionally empty
    # query.
    if not primary_keys:
        return query.filter(FALSE())
    query = query.filter(primary_key_value(related_model).in_(primary_keys))

    return search(session, related_model, filters=filters, sort=sort,
                  group_by=group_by, ignorecase=ignorecase,
                  _initial_query=query)


def search(session, model, filters=None, sort=None, group_by=None,
           ignorecase=False, _initial_query=None):
    """Returns a filtered, sorted, and grouped SQLAlchemy query.

    `session` is the SQLAlchemy session in which to create the query.

    `model` is the SQLAlchemy model on which to create a query.

    `filters` is a list of filter objects. Each filter object is a
    dictionary representation of the filters to apply to the
    query. (This dictionary is provided directly to the
    :func:`.filters.create_filters` function.) For more information on
    the format of this dictionary, see :doc:`filtering`.

    `sort` is a list of pairs of the form ``(direction, fieldname)``,
    where ``direction`` is either '+' or '-' and ``fieldname`` is a
    string representing an attribute of the model or a dot-separated
    relationship path (for example, 'owner.name'). If `ignorecase` is
    True, the sorting will be case-insensitive (so 'a' will precede 'B'
    instead of the default behavior in which 'B' precedes 'a').

    `group_by` is a list of dot-separated relationship paths on which to
    group the query results.

    If `_initial_query` is provided, the filters, sorting, and grouping
    will be appended to this query. Otherwise, an empty query will be
    created for the specified model.

    When building the query, filters are applied first, then sorting,
    then grouping.

    """
    query = _initial_query
    if query is None:
        query = session_query(session, model)

    # Filter the query.
    #
    # This function call may raise an exception.
    filters = create_filters(model, filters)
    query = query.filter(*filters)

    # Order the query. If no order field is specified, order by primary
    # key.
    # if not _ignore_sort:
    if sort:
        for (symbol, field_name) in sort:
            direction_name = 'asc' if symbol == '+' else 'desc'
            if '.' in field_name:
                field_name, field_name_in_relation = field_name.split('.')
                relation_model = aliased(get_related_model(model, field_name))
                field = getattr(relation_model, field_name_in_relation)
                if ignorecase:
                    field = field.collate('NOCASE')
                direction = getattr(field, direction_name)
                query = query.join(relation_model)
                query = query.order_by(direction())
            else:
                field = getattr(model, field_name)
                if ignorecase:
                    field = field.collate('NOCASE')
                direction = getattr(field, direction_name)
                query = query.order_by(direction())
    else:
        pks = primary_key_names(model)
        pk_order = (getattr(model, field).asc() for field in pks)
        query = query.order_by(*pk_order)

    # Group the query.
    if group_by:
        for field_name in group_by:
            if '.' in field_name:
                field_name, field_name_in_relation = field_name.split('.')
                relation_model = aliased(get_related_model(model, field_name))
                field = getattr(relation_model, field_name_in_relation)
                query = query.join(relation_model)
                query = query.group_by(field)
            else:
                field = getattr(model, field_name)
                query = query.group_by(field)

    return query
