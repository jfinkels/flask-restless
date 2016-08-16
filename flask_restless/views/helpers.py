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
