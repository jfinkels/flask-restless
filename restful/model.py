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
    exposed by restful API.

    :copyright:2011 by Lincoln de Sousa <lincoln@comum.org>
    :license: AGPLv3, see COPYTING for more details
"""

from datetime import date, datetime
from elixir import EntityBase, EntityMeta, session
from sqlalchemy.orm.properties import RelationshipProperty


def get_or_create(model, **kwargs):
    """Helper function to search for an object or create it otherwise,
    based on the Django's Model.get_or_create() method.
    """
    instance = model.query.filter_by(**kwargs).first()
    if instance:
        return instance, False
    else:
        params = {}
        for key, val in kwargs.iteritems():
            params[key] = val
        instance = model(**params)
        session.add(instance)
        session.flush()
        return instance, True


class Entity(EntityBase):
    """An extension to the elixir Entity class to fix `to_dict` method.

    The method `elixir.Entity.to_dict` does not format dates
    properly. They're returned as python objects not as strings. This
    class overrides this method to fix this little problem.
    """
    __metaclass__ = EntityMeta

    @classmethod
    def get_columns(cls):
        """Returns a dict-like object with all columns of the entity"""
        return cls._sa_class_manager

    @classmethod
    def get_relations(cls):
        """Returns a list of relation names of a given model"""
        cols = cls._sa_class_manager
        relations = []
        for key, val in cols.items():
            if isinstance(val.property, RelationshipProperty):
                relations.append(key)
        return relations

    def to_dict(self, deep=None, exclude=None):
        """Returns a json-style structure of an instance with date
        formatted as a string.
        """
        iso8601_datetime = "%Y-%m-%dT%H:%M:%S"
        iso8601_date = "%Y-%m-%d"
        data = super(Entity, self).to_dict(deep or {}, exclude or [])

        for key, value in data.items():
            if isinstance(value, date):
                data[key] = value.strftime(iso8601_date)
            if isinstance(value, datetime):
                data[key] = value.strftime(iso8601_datetime)
        return data
