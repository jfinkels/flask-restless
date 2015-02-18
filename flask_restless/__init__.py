"""
    flask.ext.restless
    ~~~~~~~~~~~~~~~~~~

    Flask-Restless is a `Flask <http://flask.pocoo.org>`_ extension which
    facilitates the creation of ReSTful JSON APIs. It is compatible with models
    which have been described using `SQLAlchemy <http://sqlalchemy.org>`_.

    :copyright:2011 by Lincoln de Sousa <lincoln@comum.org>
    :copyright: 2012, 2013, 2014, 2015 Jeffrey Finkelstein
                <jeffrey.finkelstein@gmail.com> and contributors.
    :license: GNU AGPLv3+ or BSD

"""

#: The current version of this extension.
#:
#: This should be the same as the version specified in the :file:`setup.py`
#: file.
__version__ = '0.17.0'

# make the following names available as part of the public API
from .helpers import url_for
from .manager import APIManager
from .manager import IllegalArgumentError
from .views import ProcessingException
