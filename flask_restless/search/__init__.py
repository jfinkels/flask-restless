# __init__.py - indicates that this directory is a Python package
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
"""Provides search queries for SQLAlchemy models.

The :func:`search` function creates a SQLAlchemy query object for a
given set of filters, sorting rules, etc. The
:func:`search_relationship` function creates a query restricted to a
relationship on a particular instance of a SQLAlchemy model.

The :func:`create_filters` function is a finer-grained tool: it allows
you to create the SQLAlchemy expressions without executing them.

The :exc:`FilterParsingError` and :exc:`FilterCreationError` exceptions
are the exceptions that may be raised by the func:`search` and
:func:`create_filters` functions.

"""
from .drivers import create_filters
from .drivers import search
from .drivers import search_relationship
from .filters import FilterCreationError
from .filters import FilterParsingError
from .operators import register_operator


__all__ = [
    'create_filters',
    'FilterCreationError',
    'FilterParsingError',
    'register_operator',
    'search',
    'search_relationship',
]
