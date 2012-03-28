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
    flask.ext.restless.manager
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    Provides :class:`flask.ext.restless.manager.APIManager`, the class which
    users of Flask-Restless must instantiate to create ReSTful APIs for their
    database models.

    :copyright:2011 by Lincoln de Sousa <lincoln@comum.org>
    :copyright:2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3, see COPYING for more details

"""

from flask import Blueprint

from .views import API
from .views import FunctionAPI

#: The set of methods which are allowed by default when creating an API
READONLY_METHODS = frozenset(('GET', ))


class IllegalArgumentError(Exception):
    """This exception is raised when a calling function has provided illegal
    arguments to a function or method.

    """
    pass


# TODO use __tablename__ instead of uppercase class name?
class APIManager(object):
    """Provides a method for creating a public ReSTful JSOn API with respect to
    a given :class:`~flask.Flask` application object.

    The :class:`~flask.Flask` object can be specified in the constructor, or
    after instantiation time by calling the :meth:`init_app` method. In any
    case, the application object must be specified before calling the
    :meth:`create_api` method.

    """

    #: The format of the name of the API view for a given model.
    #:
    #: This format string expects the name of a model to be provided when
    #: formatting.
    APINAME_FORMAT = '%sapi'

    #: The format of the name of the blueprint containing the API view for a
    #: given model.
    #:
    #: This format string expects the following to be provided when formatting:
    #:
    #: 1. name of the API view of a specific model
    #: 2. a number representing the number of times a blueprint with that name
    #:    has been registered.
    BLUEPRINTNAME_FORMAT = '%s%s'

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
        # blueprints is a dict whose keys are the names of the blueprints
        blueprints = self.app.blueprints
        existing = [name for name in blueprints if name.startswith(basename)]
        # if this is the first one...
        if not existing:
            next_number = 0
        else:
            # for brevity
            b = basename
            existing_numbers = [int(n.partition(b)[-1]) for n in existing]
            next_number = max(existing_numbers) + 1
        return APIManager.BLUEPRINTNAME_FORMAT % (basename, next_number)

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

    def create_api(self, model, methods=READONLY_METHODS, url_prefix='/api',
                   collection_name=None, allow_patch_many=False,
                   allow_functions=False, authentication_required_for=None,
                   authentication_function=None):
        """Creates a ReSTful API interface as a blueprint and registers it on
        the :class:`flask.Flask` application specified in the constructor to
        this class.

        The endpoints for the API for ``model`` will be available at
        ``<url_prefix>/<collection_name>``. If `collection_name` is ``None``,
        the lowercase name of the provided model class will be used instead, as
        accessed by ``model.__name__``. (If any black magic was performed on
        ``model.__name__``, this will be reflected in the endpoint URL.)

        This function must be called at most once for each model for which you
        wish to create a ReSTful API. Its behavior (for now) is undefined if
        called more than once.

        This function returns the :class:`flask.Blueprint` object which handles
        the endpoints for the model. The returned :class:`~flask.Blueprint` has
        already been registered with the :class:`~flask.Flask` application
        object specified in the constructor of this class, so you do *not* need
        to register it yourself.

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

        The default set of methods provides a read-only interface (that is,
        only :http:method:`get` requests are allowed).

        `collection_name` is the name of the collection specified by the given
        model class to be used in the URL for the ReSTful API created. If this
        is not specified, the lowercase name of the model will be used.

        ``url_prefix`` specifies the URL prefix at which this API will be
        accessible.

        If `allow_patch_many` is ``True``, then requests to
        :http:patch:`/api/<collection_name>?q=<searchjson>` will attempt to
        patch the attributes on each of the instances of the model which match
        the specified search query. This is ``False`` by default. For
        information on the search query parameter ``q``, see
        :ref:`searchformat`.

        If `allow_functions` is ``True``, then requests to
        :http:get:`/api/eval/<collection_name>` will return the result of
        evaluating SQL functions specified in the body of the request. For
        information on the request format, see :ref:`functionevaluation`. This
        if ``False`` by default. Warning: you must not create an API for a
        model whose name is ``'eval'`` if you set this argument to ``True``.

        `authentication_required_for` is a list of HTTP method names (for
        example, ``['POST', 'PATCH']``) for which authentication must be
        required before clients can successfully make requests. If this keyword
        argument is specified, `authentication_function` must also be
        specified. For more information on requiring authentication, see
        :ref:`authentication`.

        `authentication_function` is a function which accepts no arguments and
        returns ``True`` if and only if a client is authorized to make a
        request on an endpoint.

        .. versionadded:: 0.4
           Added the `authentication_required_for` keyword argument.

        .. versionadded:: 0.4
           Added the `authentication_function` keyword argument.

        .. versionadded:: 0.4
           Added the `allow_functions` keyword argument.

        .. versionchanged:: 0.4
           Force the model name in the URL to lowercase.

        .. versionadded:: 0.4
           Added the `allow_patch_many` keyword argument.

        .. versionadded:: 0.4
           Added the `collection_name` keyword argument.

        """
        if authentication_required_for and not authentication_function:
            msg = ('If authentication_required is specified, so must'
                   ' authentication_function.')
            raise IllegalArgumentError(msg)
        if collection_name is None:
            collection_name = model.__name__.lower()
        methods = frozenset(methods)
        # sets of methods used for different types of endpoints
        no_instance_methods = methods & frozenset(('POST', ))
        if allow_patch_many:
            possibly_empty_instance_methods = \
                methods & frozenset(('GET', 'PATCH', 'PUT'))
        else:
            possibly_empty_instance_methods = methods & frozenset(('GET', ))
        instance_methods = \
            methods & frozenset(('GET', 'PATCH', 'DELETE', 'PUT'))
        # the base URL of the endpoints on which requests will be made
        collection_endpoint = '/%s' % collection_name
        instance_endpoint = collection_endpoint + '/<int:instid>'
        # the name of the API, for use in creating the view and the blueprint
        apiname = APIManager.APINAME_FORMAT % collection_name
        # the view function for the API for this model
        api_view = API.as_view(apiname, model, authentication_required_for,
                               authentication_function)
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
        # if function evaluation is allowed, add an endpoint at /api/eval/...
        # which responds only to GET requests and responds with the result of
        # evaluating functions on all instances of the specified model
        if allow_functions:
            eval_api_name = apiname + 'eval'
            eval_api_view = FunctionAPI.as_view(eval_api_name, model)
            eval_endpoint = '/eval' + collection_endpoint
            blueprint.add_url_rule(eval_endpoint, methods=['GET'],
                                   view_func=eval_api_view)
        # register the blueprint on the app
        self.app.register_blueprint(blueprint)
        return blueprint
