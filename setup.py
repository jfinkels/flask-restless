# setup.py - packaging and distribution configuration for Flask-Restless
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
"""Flask-Restless is a `Flask`_ extension that provides simple
generation of ReSTful APIs that satisfy the `JSON API`_ specification
given database models defined using `SQLAlchemy`_ (or
`Flask-SQLAlchemy`_).

For more information, see the `documentation`_, `pypi`_, or the `source
code`_ repository.

.. _Flask: http://flask.pocoo.org
.. _SQLAlchemy: https://sqlalchemy.org
.. _Flask-SQLAlchemy: https://pypi.python.org/pypi/Flask-SQLAlchemy
.. _JSON API: http://jsonapi.org
.. _documentation: https://flask-restless.readthedocs.org
.. _pypi: https://pypi.python.org/pypi/Flask-Restless
.. _source code: https://github.com/jfinkels/flask-restless

"""
import codecs
import os.path
import re
from setuptools import setup, find_packages

#: A regular expression capturing the version number from Python code.
VERSION_RE = r"^__version__ = ['\"]([^'\"]*)['\"]"

# TODO We require Flask version 1.0 or greater if we want Flask to recognize
# the JSON API mimetype as a form of JSON and therefore automatically be able
# to deserialize JSON to Python via the Request.get_json() method. On the other
# hand, we could keep the 0.10 requirement and simply rely on the ``force``
# keyword argument of that method, which also works around the limitations in
# MSIE8 and MSIE9...

#: The installation requirements for Flask-Restless. Flask-SQLAlchemy is not
#: required, so the user must install it explicitly.
REQUIREMENTS = ['flask>=0.10', 'sqlalchemy>=0.8', 'python-dateutil>2.2']

#: The absolute path to this file.
HERE = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    """Reads the entire contents of the file whose path is given as `parts`."""
    with codecs.open(os.path.join(HERE, *parts), 'r') as f:
        return f.read()


def find_version(*file_path):
    """Returns the version number appearing in the file in the given file
    path.

    Each positional argument indicates a member of the path.

    """
    version_file = read(*file_path)
    version_match = re.search(VERSION_RE, version_file, re.MULTILINE)
    if version_match:
        return version_match.group(1)
    raise RuntimeError('Unable to find version string.')


setup(
    author='Jeffrey Finkelstein',
    author_email='jeffrey.finkelstein@gmail.com',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        ('License :: OSI Approved :: '
         'GNU Affero General Public License v3 or later (AGPLv3+)'),
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Database :: Front-Ends',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    description=('Flask extension for generating a JSON API interface for'
                 ' SQLAlchemy models'),
    download_url='https://pypi.python.org/pypi/Flask-Restless',
    install_requires=REQUIREMENTS,
    include_package_data=True,
    keywords=['ReST', 'API', 'Flask'],
    license='GNU AGPLv3+ or BSD',
    long_description=__doc__,
    name='Flask-Restless',
    platforms='any',
    packages=find_packages(exclude=['tests', 'tests.*']),
    test_suite='tests',
    tests_require=['unittest2'],
    url='https://github.com/jfinkels/flask-restless',
    version=find_version('flask_restless', '__init__.py'),
    zip_safe=False
)
