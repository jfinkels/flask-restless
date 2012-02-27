# -*- coding: utf-8; Mode: Python -*-
#
# Copyright (C) 2011  Lincoln de Sousa <lincoln@comum.org>
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

"""
    restful.model
    ~~~~~~~~~~~~~

    Provides a base class to be used by models that are going to be
    exposed by the ReSTful API.

    :copyright:2011 by Lincoln de Sousa <lincoln@comum.org>
    :license: AGPLv3, see COPYTING for more details
"""

from datetime import date, datetime
from elixir import EntityBase, EntityMeta, session
from sqlalchemy.orm.properties import RelationshipProperty


ISO8601_DATE = "%Y-%m-%d"
"""The ISO 8601 string format for :class:`datetime.date` objects."""

ISO8601_DATETIME = "%Y-%m-%dT%H:%M:%S"
"""The ISO 8601 string format for :class:`datetime.datetime`."""


class Entity(EntityBase):
    """An extension to the original :class:`elixir.entity.Entity` class which
    provides some extra functionality and fixes some deficiencies.

    First, the original method :meth:`elixir.entity.Entity.to_dict` returns
    dates formatted as Python :class:`datetime.date` or
    :class:`datetime.datetime` objects instead of strings, making serialization
    to JSON difficult. This class overrides this method to serialize
    :class:`datetime.date` and :class:`datetime.datetime` objects to strings in
    ISO 8601 format.

    Second, this class provides some additional convenience functions,
    including :func:`get_columns`, :func:`get_relations`, and
    :func:`get_or_create`.

    """
    __metaclass__ = EntityMeta

    @classmethod
    def get_columns(cls):
        """Returns a dictionary-like object containing all the columns of this
        entity.

        """
        return cls._sa_class_manager

    @classmethod
    def get_relations(cls):
        """Returns a list of relation names of this model (as a list of
        strings).

        """
        cols = cls._sa_class_manager
        relations = []
        for key, val in cols.items():
            if isinstance(val.property, RelationshipProperty):
                relations.append(key)
        return relations

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

    def to_dict(self, deep={}, exclude=[]):
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

        The ``deep`` dictionary and ``exclude`` list are passed directly to the
        :meth:`elixir.entity.Entity.to_dict` method.

        """
        data = super(Entity, self).to_dict(deep, exclude)

        for key, value in data.items():
            if isinstance(value, date):
                data[key] = value.strftime(ISO8601_DATE)
            if isinstance(value, datetime):
                data[key] = value.strftime(ISO8601_DATETIME)
        return data
