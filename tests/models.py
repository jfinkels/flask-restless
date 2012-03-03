# -*- coding: utf-8; Mode: Python -*-
#
# Copyright (C) 2011 Lincoln de Sousa <lincoln@comum.org>
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
"""Provides database models for use in testing."""
from elixir import Date
from elixir import DateTime
from elixir import Field
from elixir import Float
from elixir import ManyToOne
from elixir import metadata
from elixir import OneToMany
from elixir import setup_all
from elixir import Unicode

from flask.ext.restless import Entity


class Computer(Entity):
    name = Field(Unicode, unique=True)
    vendor = Field(Unicode)
    owner = ManyToOne('Person')
    buy_date = Field(DateTime)


class Person(Entity):
    name = Field(Unicode, unique=True)
    age = Field(Float)
    other = Field(Float)
    computers = OneToMany('Computer')
    birth_date = Field(Date)

def setup(uri):
    metadata.bind = uri
    metadata.bind.echo = False
    setup_all()
