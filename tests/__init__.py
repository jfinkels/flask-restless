# -*- coding: utf-8; Mode: Python -*-
#
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

    The :func:`suite` function returns a test suite containing all tests in
    this package.

    If you have Python 2.7, run the full test suite from the command-line like
    this::

        python -m tests

    If you have Python 2.6 or earlier, run the full test suite from the
    command-line like this::

        python -m tests.__main__

    Otherwise, you can just use the :file:`setup.py` script::

        python setup.py test

    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3, see COPYING for more details

"""
import unittest

from . import test_manager
from . import test_model
from . import test_search
from . import test_views

def suite():
    """Returns the test suite for this module."""
    suite = unittest.TestSuite()
    loader = unittest.defaultTestLoader
    suite.addTest(loader.loadTestsFromModule(test_manager))
    suite.addTest(loader.loadTestsFromModule(test_model))
    suite.addTest(loader.loadTestsFromModule(test_search))
    suite.addTest(loader.loadTestsFromModule(test_views))
    return suite
