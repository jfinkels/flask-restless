# Flask-Restless #

## Introduction ##

This is Flask-Restless, a [Flask][1] extension which facilitates the creation
of ReSTful JSON APIs. It is compatible with models which have been defined
using either [SQLAlchemy][sa] or [Flask-SQLAlchemy][fsa].

This document contains some brief instructions concerning installation of
requirements, installation of this extension, configuration and usage of this
extension, and building of documentation.

For more information, check the World Wide Web!

  * [Documentation](http://readthedocs.org/docs/flask-restless)
  * [Python Package Index listing](http://pypi.python.org/pypi/Flask-Restless)
  * [Source code repository](http://github.com/jfinkels/flask-restless)

[![Build status](https://secure.travis-ci.org/jfinkels/flask-restless.png)](http://travis-ci.org/jfinkels/flask-restless)

[1]: http://flask.pocoo.org
[sa]: http://sqlalchemy.org
[fsa]: http://packages.python.org/Flask-SQLAlchemy

## Copyright license ##

The code comprising this program is copyright 2011 Lincoln de Sousa and
copyright 2012 Jeffrey Finkelstein, and is dual-licensed under the following
two copyright licenses:

* the GNU Affero General Public License, either version 3 or (at your option)
  any later version
* the 3-clause BSD License

For more information, see the files `LICENSE.AGPL` and `LICENSE.BSD` in this
directory.

## Contents ##

This is a partial listing of the contents of this package.

* `COPYING` - the copyright license under which this program is distributed to
  you (the GNU Affero General Public License version 3)
* `docs/` - the Sphinx documentation for Flask-Restless
* `examples/` - example applications of Flask-Restless
* `flask_restless/` - the Python package containing the extension
* `README.md` - this file
* `setup.py` - Python setuptools configuration file for packaging this
  extension
* `tests/` - unit tests for Flask-Restless

The `flask_restless` directory is a Python package containing the following
files:

* `views.py` - the view class which implements the ReSTful API
* `manager.py` - the main class which end users will utilize to create ReSTful
  APIs for their database models
* `search.py` - functions and classes which facilitate searching the database
  on requests which require a search

## Installing ##

This application requires [Python][4] version 2.5, 2.6, or 2.7.

This application requires the following libraries to be installed:

* [Flask][1] version 0.7 or greater
* [SQLAlchemy][sa]
* [python-dateutil][5] version less than 2.0
* [simplejson][sj] only in Python 2.5
* [Flask-SQLAlchemy][fsa] only if your models are defined using Flask-SQLAlchemy

These requirements are also listed in the `requirements.txt` file. Using `pip`
is probably the easiest way to install these:

    pip install -r requirements.txt

or

    pip install Flask Flask-SQLAlchemy python-dateutil simplejson sqlalchemy

Technical note: simplejson is only required if you are using Python 2.5. The
built-in json module will suffice in later Python versions.

[4]: http://www.python.org/
[5]: http://labix.org/python-dateutil
[sj]: http://pypi.python.org/pypi/simplejson

## Building as a Python egg ##

This package can be built, installed, etc. as a Python egg using the provided
`setup.py` script. For more information, run

    python setup.py --help

## How to use ##

For information on how to use this extension, build the documentation here or
[view it on the Web](http://readthedocs.org/docs/flask-restless).

## Testing ##

Running the unit tests requires the [unittest2][ut2] package, which backports
the functionality of the built-in `unittest` package from Python version 2.7 to
earlier versions. This requirement is also listed in the
`requirements-test.txt` file.

Using `pip` is probably the easiest way to install this:

    pip install -r requirements-test.txt

or

    pip install unittest2

The Python unit tests are contained in the `tests/` directory (which is a
Python package). To run the test suite, run the command

    python setup.py test

You can also run the unit tests in a less verbose way by doing

    ./run-tests.py

This is a Python module which, when executed, simply runs all unit tests.

[ut2]: http://pypi.python.org/pypi/unittest2

### Test coverage ###

You can measure the test coverage by running

    python setup.py coverage

Measuring test coverage requires the [coverage.py][cov] package, which can be
installed like this:

    pip install coverage

[cov]: http://nedbatchelder.com/code/coverage

### Testing validation ###

Validation is not provided directly by Flask-Restless, but it does provide a
way for users to indicate exceptions to catch. If you wish to test validation
of SQLAlchemy models with a real external SQLAlchemy validation library,
install the development version of [SAValidation][sav]:

    pip install -e "hg+http://bitbucket.org/rsyring/sqlalchemy-validation#egg=savlidation-dev"

The test suite will automatically skip these tests if it is not installed.

[sav]: http://pypi.python.org/pypi/SAValidation

## Building documentation ##

Flask-Restless requires the following program and supporting library to build
the documentation:

* [Sphinx][6]
* [sphinxcontrib-httpdomain][7], version 1.1.7 or greater

These requirements are also listed in the `requirements-doc.txt` file. Using
`pip` is probably the easiest way to install these:

    pip install -r requirements-doc.txt

or

    pip install sphinx "sphinxcontrib-httpdomain>=1.1.7"

The documentation is written for Sphinx in [reStructuredText][8] files in the
`docs/` directory. Documentation for each class and function is provided in the
docstring in the code.

The documentation uses the Flask Sphinx theme. It is included as a git
submodule of this project, rooted at `docs/_themes`. To get the themes, do

    git submodule update --init

Now to build the documentation, run the command

    python setup.py build_sphinx

in the top-level directory. The output can be viewed in a web browser by
opening `docs/_build/html/index.html`.

[6]: http://sphinx.pocoo.org/
[7]: http://packages.python.org/sphinxcontrib-httpdomain/
[8]: http://docutils.sourceforge.net/rst.html

## Authors ##

See the `AUTHORS` file for a list of people who have contributed to this code.

## Artwork ##

The `artwork/flask-restless-small.svg` and
`docs/_static/flask-restless-small.png` are licensed under the
[Creative Commons Attribute-ShareAlike 3.0 license][9]. The original image is a
scan of a (now public domain) illustration by Arthur Hopkins in a serial
edition of "The Return of the Native" by Thomas Hardy published in October
1878.

The `artwork/flask-restless.svg` and `docs/_static/flask-restless.png` are
licensed under the [Flask Artwork License][10].

[9]: http://creativecommons.org/licenses/by-sa/3.0
[10]: http://flask.pocoo.org/docs/license/#flask-artwork-license

## Contact ##

Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
