"""
    flask.ext.restless
    ~~~~~~~~~~~~~~~~~~

    Flask-Restless is a `Flask`_ extension that creates endpoints that satisfy
    the requirements of the `JSON API`_ specification. It is compatible with
    models that have been defined using `SQLAlchemy`_ or `Flask-SQLAlchemy`_.

    .. _Flask: http://flask.pocoo.org
    .. _JSON API: http://jsonapi.org
    .. _SQLAlchemy: http://sqlalchemy.org
    .. _Flask-SQLAlchemy: https://pythonhosted.org/Flask-SQLAlchemy

    :copyright:2011 by Lincoln de Sousa <lincoln@comum.org>
    :copyright: 2012, 2013, 2014, 2015 Jeffrey Finkelstein
                <jeffrey.finkelstein@gmail.com> and contributors.
    :license: GNU AGPLv3+ or BSD

"""

#: The current version of this extension.
#:
#: This should be the same as the version specified in the :file:`setup.py`
#: file.
__version__ = '0.17.1-dev'

# The following names are available as part of the public API for
# Flask-Restless. End users of this package can import these names by doing
# ``from flask.ext.restless import APIManager``, for example.
from .helpers import collection_name
from .helpers import model_for
from .helpers import url_for
from .manager import APIManager
from .manager import IllegalArgumentError
from .serialization import SerializationException
from .serialization import simple_serialize
from .serialization import DeserializationException
from .views import CONTENT_TYPE
from .views import ProcessingException
