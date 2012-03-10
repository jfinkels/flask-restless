# -*- coding: utf-8; Mode: Python -*-
#
# Copyright (C) 2011 Lincoln de Sousa <lincoln@comum.org>
# Copyright 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
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
    Flask-Restless unit tests
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    Provides unit tests for modules in the :mod:`flask_restless` package.

    This module imports all test classes from the ``test_*`` modules in this
    package, so that the full test suite can be run from the command-line like
    this::

        python -m unittest tests

    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :copyright: 2011 Lincoln de Sousa <lincoln@comum.org>
    :license: GNU AGPLv3, see COPYING for more details
"""

from .test_manager import *
from .test_model import *
from .test_search import *
from .test_views import *
