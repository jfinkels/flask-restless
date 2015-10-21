"""
    Flask-Restless unit tests
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    Provides unit tests for modules in the :mod:`flask_restless`
    package.

    The :mod:`test_jsonapi` module contains explicit tests for nearly
    all of the requirements of the JSON API specification. The modules
    :mod:`test_bulk` and :mod:`test_jsonpatch` test the default JSON API
    extensions. Other modules such as :mod:`test_fetching` and
    :mod:`test_updating` test features specific to the JSON API
    implementation provided by Flask-Restless, as well as additional
    features not discussed in the specification.

    Run the full test suite from the command-line like this::

        python setup.py test

    Or by running::

        nosetests

    :copyright: 2012, 2013, 2014, 2015 Jeffrey Finkelstein
                <jeffrey.finkelstein@gmail.com> and contributors.
    :license: GNU AGPLv3+ or BSD

"""
