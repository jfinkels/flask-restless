# -*- coding: utf-8; Mode: Python -*-
#
# Copyright (C) 2011 Lincoln de Sousa <lincoln@comum.org>
#
# This file is part of Flask-Restless.
#
# Flask-Restless is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# Flask-Restless is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Flask-Restless. If not, see <http://www.gnu.org/licenses/>.
"""
    flask.ext.restless.model
    ~~~~~~~~~~~~~~~~~~~~~~~~

    Provides a base classes for models which will be exposed by the
    :meth:`flask.ext.restless.manager.APIManager.create_api` method.

    Users of Flask-Restless must create their models as subclasses of
    :class:`flask.ext.restless.model.Entity` instead of :class:`elixir.Entity`.

    :copyright:2011 by Lincoln de Sousa <lincoln@comum.org>
    :license: GNU AGPLv3, see COPYING for more details

"""

from datetime import date, datetime
from elixir import EntityBase, EntityMeta, session
from sqlalchemy.orm.properties import RelationshipProperty as RelProperty
from sqlalchemy.types import Date
from sqlalchemy.types import DateTime


#: The ISO 8601 string format for :class:`datetime.date` objects.
ISO8601_DATE = "%Y-%m-%d"

#: The ISO 8601 string format for :class:`datetime.datetime` objects.
ISO8601_DATETIME = "%Y-%m-%dT%H:%M:%S"


class Entity(EntityBase):
    """An extension to the original :class:`elixir.entity.Entity` class which
    provides some extra functionality and fixes some deficiencies.

    First, the original method :meth:`elixir.entity.Entity.to_dict` returns
    dates formatted as Python :class:`datetime.date` or
    :class:`datetime.datetime` objects instead of strings, making serialization
    to JSON difficult. This class overrides this method to serialize
    :class:`datetime.date` and :class:`datetime.datetime` objects to strings in
    ISO 8601 format.

    Second, this class provides some additional convenience functions for
    internal code, including :func:`get_columns`, :func:`get_relations`, and
    :func:`get_or_create`.

    Classes which will be exposed by the API *must* inherit from this class
    instead of :class:`elixir.Entity`.

    """
    __metaclass__ = EntityMeta

    @classmethod
    def get_column(cls, columnname):
        """Returns the column of this entity with the specified name."""
        return cls.get_columns()[columnname]

    @classmethod
    def get_columns(cls):
        """Returns a dictionary-like object containing all the columns of this
        entity.

        """
        return cls._sa_class_manager

    @classmethod
    def get_related_model(cls, relationname):
        """Gets the :class:`~elixir.Entity` class of the model to which `cls`
        is related by the attribute whose name is `relationname`.

        """
        return cls.get_column(relationname).property.mapper.class_

    @classmethod
    def get_relations(cls):
        """Returns a list of relation names of this model (as a list of
        strings).

        """
        cols = cls._sa_class_manager
        return [k for k in cols if isinstance(cols[k].property, RelProperty)]

    @classmethod
    def get_or_create(cls, **kwargs):
        """Returns the first instance of the specified model filtered by the
        keyword arguments, or creates a new instance of the model and returns
        that.

        This function returns a two-tuple in which the first element is the
        created or retrieved instance and the second is a boolean value
        which is ``True`` if and only if an instance was created.

        The idea for this function is based on Django's
        ``Model.get_or_create()`` method.

        ``kwargs`` are the keyword arguments which will be passed to the
        :func:`sqlalchemy.orm.query.Query.filter_by` function.

        """
        instance = cls.query.filter_by(**kwargs).first()
        if instance:
            return instance, False
        else:
            instance = cls(**kwargs)
            session.add(instance)
            session.commit()
            return instance, True

    @classmethod
    def is_date_or_datetime(cls, fieldname):
        """Returns ``True`` if and only if the field of this model with the
        specified name corresponds to either a :class:`datetime.date` object or
        a :class:`datetime.datetime` object.

        """
        fieldtype = getattr(cls, fieldname).property.columns[0].type
        return isinstance(fieldtype, Date) or isinstance(fieldtype, DateTime)

    def to_dict(self, deep=None, exclude=None):
        """Returns a dictionary representation of this instance of the entity
        with any :class:`datetime.date` or :class:`datetime.datetime` objects
        formatted as a string in ISO 8601 format.

        For example::

            >>> from restful.model import Entity
            >>> from elixir import Field, Date, DateTime, setup_all
            >>> from datetime import datetime, date
            >>>
            >>> class Foo(Entity):
            ...     mydate = Field(Date)
            ...     mydatetime = Field(DateTime)
            ...
            >>> f = Foo(mydate=date.today(), mydatetime=datetime.now())
            >>> f.to_dict()
            {'mydate': '2012-02-27', 'id': None,
             'mydatetime': '2012-02-27T15:59:43'}

        The `deep` dictionary and `exclude` list are passed directly to the
        :meth:`elixir.entity.Entity.to_dict` method.

        """
        data = super(Entity, self).to_dict(deep or {}, exclude or [])
        # Iterate over each pair of the returned dictionary and convert date or
        # datetime objects to their ISO 8601 string representations. Do not
        # modify any other objects.
        #
        # Use data.items() here instead of data.iteritems() because the former
        # returns a copy of the list and we are modifying the original list
        # in-place. Note that in Python 3, data.items() returns a view of the
        # dictionary, but this should allow modifying while iterating.
        for key, value in data.items():
            # Objects of type datetime satisfy both the first condition and the
            # second condition (since datetime is a subclass of date).
            # Therefore, we use if/elif to make sure at most one of these lines
            # is executed.
            if isinstance(value, datetime):
                data[key] = value.strftime(ISO8601_DATETIME)
            elif isinstance(value, date):
                data[key] = value.strftime(ISO8601_DATE)
        return data
