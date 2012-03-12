# -*- coding: utf-8; Mode: Python -*-
#
# Copyright (C) 2011 Lincoln de Sousa <lincoln@comum.org>
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
"""
Flask-Restless
~~~~~~~~~~~~~~

Flask-Restless is a `Flask <http://flask.pocoo.org>`_ extension which
facilitates the creation of ReSTful JSON APIs. It is compatible with models
which have been described using `Elixir <http://elixir.ematia.de>`_, a layer on
top of `SQLAlchemy <http://sqlalchemy.org>`_.

For more information, check the World Wide Web!

  * `Documentation <http://readthedocs.org/docs/flask-restless>`_
  * `PyPI listing <http://pypi.python.org/pypi/Flask-Restless>`_
  * `Source code repository <http://github.com/jfinkels/flask-restless>`_

"""
from __future__ import with_statement

from setuptools import setup


def from_requirements_file(filename='requirements.txt'):
    """Returns a list of required Python packages from the file whose path is
    given by `filename`.

    By default, `filename` is the conventional :file:`requirements.txt` file.

    """
    with open(filename, 'r') as f:
        requirements = f.read()
    return requirements.split()


setup(
    author='Jeffrey Finkelstein',
    author_email='jeffrey.finkelstein@gmail.com',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Affero General Public License v3',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Database :: Front-Ends',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    description='A Flask extension for easy ReSTful API generation',
    download_url='http://pypi.python.org/pypi/Flask-Restless',
    install_requires=from_requirements_file(),
    include_package_data=True,
    keywords=['ReST', 'API', 'Flask', 'Elixir'],
    license='GNU AGPLv3+',
    long_description=__doc__,
    name='Flask-Restless',
    platforms='any',
    packages=['flask_restless'],
    test_suite='tests.suite',
    tests_require=['unittest2'],
    url='http://github.com/jfinkels/flask-restless',
    version='0.4-dev',
    zip_safe=False
)
