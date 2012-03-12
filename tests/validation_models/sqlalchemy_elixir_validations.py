# -*- coding: utf-8; Mode: Python -*-
#
# Copyright 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
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
"""Models for use in testing validation using the
``sqlalchemy_elixir_validations`` package. If that package is not installed,
this importing this module will raise a :class:`ImportError`.

"""
import re

from elixir import Field
from elixir import Integer
from elixir import Unicode

# for the sqlalchemy_elixir_validations package on pypi.python.org
from elixir_validations import validates_format_of
from elixir_validations import validates_numericality_of
from elixir_validations import validates_presence_of
from elixir_validations import validates_range_of
from elixir_validations import validates_uniqueness_of

from flask.ext.restless import Entity

#: A regular expression for email addresses.
EMAIL_REGEX = re.compile("[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^"
                         "_`{|}~-]+)*@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a"
                         "-z0-9](?:[a-z0-9-]*[a-z0-9])")


# create the validated class
# NOTE: don't name this `Person`, as in models.Person
class Test(Entity):
    name = Field(Unicode(30), nullable=False, index=True)
    email = Field(Unicode, nullable=False)
    age = Field(Integer, nullable=False)

    validates_uniqueness_of('name')
    validates_presence_of('name', 'email')
    validates_format_of('email', EMAIL_REGEX)
    validates_numericality_of('age', integer_only=True)
    validates_range_of('age', 0, 150)
