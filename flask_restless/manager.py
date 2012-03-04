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
    flaskext.restless.manager
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    Provides :class:`APIManager`, the class which users of this extension will
    utilize to create ReSTful APIs for their database models.

    :copyright:2011 by Lincoln de Sousa <lincoln@comum.org>
    :copyright:2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3, see COPYING for more details

"""

from flask import Blueprint

from .views import API


# TODO add support for PUT method which just delegates to PATCH?
# TODO use __tablename__ instead of uppercase class name?
class APIManager(object):
    """Provides a method for creating a public ReSTful JSOn API with respect to
    a given :class:`~flask.Flask` application object.

    The :class:`~flask.Flask` object can be specified in the constructor, or
    after instantiation time by calling the :meth:`init_app` method. In any
    case, the application object must be specified before calling the
    :meth:`create_api` method.

    """

    APINAME_FORMAT = '{}api'
    """The format of the name of the API view for a given model.

    This format string expects the name of a model to be provided when
    formatting.

    """

    BLUEPRINTNAME_FORMAT = '{}{}'
    """The format of the name of the blueprint containing the API view for a
    given model.

    This format string expects the following to be provided when formatting:

    1. name of the API view of a specific model
    2. a number representing the number of times a blueprint with that name has
       been registered.

    """

    def __init__(self, app=None):
        """Stores the specified :class:`flask.Flask` application object so that
        this class can register blueprints on it later.

        If `app` is ``None``, the user must call the :meth:`init_app` method
        before calling the :meth:`create_api` method.

        `app` is the :class:`flask.Flask` object containing the user's Flask
        application.

        """
        self.app = app

    def _next_blueprint_name(self, basename):
        """Returns the next name for a blueprint with the specified base name.

        This method returns a string of the form ``'{}{}'.format(basename,
        number)``, where ``number`` is the next non-negative integer not
        already used in the name of an existing blueprint.

        For example, if `basename` is ``'personapi'`` and blueprints already
        exist with names ``'personapi0'``, ``'personapi1'``, and
        ``'personapi2'``, then this function would return ``'personapi3'``. We
        expect that code which calls this function will subsequently register a
        blueprint with that name, but that is not necessary.

        """
        existing_names = filter(lambda s: s.startswith(basename),
                                self.app.blueprints.iterkeys())
        # if this is the first one...
        if not list(existing_names):
            next_number = 0
        else:
            existing_numbers = map(lambda n: int(n.partition(basename)[-1]),
                                   existing_names)
            next_number = max(existing_numbers) + 1
        return APIManager.BLUEPRINTNAME_FORMAT.format(basename, next_number)

    def init_app(self, app):
        """Stores the specified :class:`flask.Flask` application object on
        which API endpoints will be registered.

        This is for use in the situation in which this class must be
        instantiated before the :class:`~flask.Flask` application has been
        created. For example::

            apimanager = APIManager()

            # later...

            app = Flask(__name__)
            apimanager.init_app(app)

        """
        self.app = app

    # alternately: def add_api(modelname, readonly=True):
    def create_api(self, model, methods=['GET'], url_prefix='/api'):
        """Creates a ReSTful API interface as a blueprint and registers it on
        the :class:`flask.Flask` application specified in the constructor to
        this class.

        The endpoints for the API for ``model`` will be available at
        ``<url_prefix>/<modelname>``, where ``<url_prefix>`` is the last
        parameter to this function and ``<modelname>`` is the lowercase string
        representation of the model class, as accessed by
        ``model.__name__``. (If any black magic was performed on
        ``model.__name__``, this will be reflected in the endpoint URL.)

        This function must be called at most once for each model for which you
        wish to create a ReSTful API. Its behavior (for now) is undefined if
        called more than once.

        ``model`` is the :class:`flask.ext.restless.Entity` class for which a
        ReSTful interface will be created. Note this must be a class, not an
        instance of a class.

        ``methods`` specify the HTTP methods which will be made available on
        the ReSTful API for the specified model, subject to the following
        caveats:

        * If :http:method:`get` is in this list, the API will allow getting a
          single instance of the model, getting all instances of the model, and
          searching the model using search parameters.
        * If :http:method:`patch` is in this list, the API will allow updating
          a single instance of the model, updating all instances of the model,
          and updating a subset of all instances of the model specified using
          search parameters.
        * If :http:method:`delete` is in this list, the API will allow deletion
          of a single instance of the model per request.
        * If :http:method:`post` is in this list, the API will allow posting a
          new instance of the model per request.

        The default list of methods provides a read-only interface (that is,
        only :http:method:`get` requests are allowed).

        ``url_prefix`` specifies the URL prefix at which this API will be
        accessible.

        """
        modelname = model.__name__
        methods = frozenset(methods)
        # sets of methods used for different types of endpoints
        no_instance_methods = methods & {'POST'}
        possibly_empty_instance_methods = methods & {'GET', 'PATCH'}
        instance_methods = methods & {'GET', 'PATCH', 'DELETE'}
        # the base URL of the endpoints on which requests will be made
        collection_endpoint = '/{}'.format(modelname)
        instance_endpoint = collection_endpoint + '/<int:instid>'
        # the name of the API, for use in creating the view and the blueprint
        apiname = APIManager.APINAME_FORMAT.format(modelname)
        # the view function for the API for this model
        api_view = API.as_view(apiname, model)
        # suffix an integer to apiname according to already existing blueprints
        blueprintname = self._next_blueprint_name(apiname)
        # add the URL rules to the blueprint: the first is for methods on the
        # collection only, the second is for methods which may or may not
        # specify an instance, the third is for methods which must specify an
        # instance
        # TODO what should the second argument here be?
        # TODO should the url_prefix be specified here or in register_blueprint
        blueprint = Blueprint(blueprintname, __name__, url_prefix=url_prefix)
        blueprint.add_url_rule(collection_endpoint,
                               methods=no_instance_methods, view_func=api_view)
        blueprint.add_url_rule(collection_endpoint, defaults={'instid': None},
                               methods=possibly_empty_instance_methods,
                               view_func=api_view)
        blueprint.add_url_rule(instance_endpoint, methods=instance_methods,
                               view_func=api_view)
        # register the blueprint on the app
        self.app.register_blueprint(blueprint)
