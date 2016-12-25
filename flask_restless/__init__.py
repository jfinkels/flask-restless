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
"""Provides classes for creating endpoints for interacting with
SQLAlchemy models via the JSON API protocol.

"""
# The following names are available as part of the public API for
# Flask-Restless. End users of this package can import these names by doing
# ``from flask_restless import APIManager``, for example.
from .helpers import collection_name
from .helpers import model_for
from .helpers import serializer_for
from .helpers import url_for
from .helpers import primary_key_for
from .manager import APIManager
from .manager import IllegalArgumentError
from .serialization import DefaultDeserializer
from .serialization import DefaultSerializer
from .serialization import DeserializationException
from .serialization import MultipleExceptions
from .serialization import SerializationException
from .serialization import simple_serialize
from .serialization import simple_serialize_many
from .search import register_operator
from .views import JSONAPI_MIMETYPE
from .views import ProcessingException

#: The current version of this extension.
#:
#: This should be the same as the version specified in the :file:`setup.py`
#: file.
__version__ = '1.0.0b2-dev'

__all__ = [
    'APIManager',
    'collection_name',
    'DefaultDeserializer',
    'DefaultSerializer',
    'DeserializationException',
    'IllegalArgumentError',
    'JSONAPI_MIMETYPE',
    'model_for',
    'MultipleExceptions',
    'primary_key_for',
    'ProcessingException',
    'register_operator',
    'SerializationException',
    'serializer_for',
    'simple_serialize',
    'simple_serialize_many',
    'url_for',
]
