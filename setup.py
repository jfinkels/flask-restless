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
# Flask-Restless #

Flask-Restless is a [Flask][1] extension which facilitates the creation of
ReSTful APIs. It is compatible with models which have been described using
[Elixir][2], a layer on top of [SQLAlchemy][3].

For more information, check the World Wide Web!

  * [Homepage and documentation](http://packages.python.org/Flask-Restless)
  * [Python Package Index listing](http://pypi.python.org/pypi/Flask-Restless)
  * [Source code repository](http://github.com/jfinkels/flask-restless)

[1]: http://flask.pocoo.org
[2]: http://elixir.ematia.de
[3]: http://sqlalchemy.org

"""
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
    keywords=['ReST', 'API', 'Flask', 'Elixir'],
    license='GNU AGPLv3+',
    long_description=__doc__,
    name='Flask-Restless',
    url='http://github.com/jfinkels/flask-restless',
    packages=['flaskext.restless'],
    test_suite='tests',
    version='0.3-dev'
)
