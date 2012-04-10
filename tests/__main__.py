"""
    Flask-Restless unit test runner
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Runs all unit tests in this package.

    If you have Python 2.7, run this from the command-line like this::

        python -m tests

    If you have Python 2.6 or earlier, run this from the command-line like
    this::

        python -m tests.__main__


    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
import unittest2

from . import suite

unittest2.main(defaultTest='suite')
