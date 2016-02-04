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
"""Unit tests for Flask-Restless.

The :mod:`test_jsonapi` package contains explicit tests for nearly all
of the requirements of the JSON API specification. The modules
:mod:`test_bulk` and :mod:`test_jsonpatch` test the default JSON API
extensions. Other modules such as :mod:`test_fetching` and
:mod:`test_updating` test features specific to the JSON API
implementation provided by Flask-Restless, as well as additional
features not discussed in the specification.

Run the full test suite from the command-line using ``nosetests`` (or
``python setup.py test``).

"""
