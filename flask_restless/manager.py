# manager.py - class that creates endpoints compliant JSON API
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
"""Provides the main class with which users of Flask-Restless interact.

The :class:`APIManager` class allow users to create ReSTful APIs for
their SQLAlchemy models.

"""
from collections import defaultdict
from collections import namedtuple
from uuid import uuid1
import sys

from sqlalchemy.inspection import inspect
from flask import Blueprint
from flask import url_for as flask_url_for

from .helpers import collection_name
from .helpers import model_for
from .helpers import primary_key_for
from .helpers import serializer_for
from .helpers import url_for
from .serialization import DefaultSerializer
from .serialization import DefaultDeserializer
from .views import API
from .views import FunctionAPI
from .views import RelationshipAPI

#: The names of HTTP methods that allow fetching information.
READONLY_METHODS = frozenset(('GET', ))

#: The names of HTTP methods that allow creating, updating, or deleting
#: information.
WRITEONLY_METHODS = frozenset(('PATCH', 'POST', 'DELETE'))

#: The set of all recognized HTTP methods.
ALL_METHODS = READONLY_METHODS | WRITEONLY_METHODS

#: The default URL prefix for APIs created by instance of :class:`APIManager`.
DEFAULT_URL_PREFIX = '/api'

if sys.version_info < (3, ):
    STRING_TYPES = (str, unicode)
else:
    STRING_TYPES = (str, )

#: A triple that stores the SQLAlchemy session and the universal pre- and post-
#: processors to be applied to any API created for a particular Flask
#: application.
#:
#: These tuples are used by :class:`APIManager` to store information about
#: Flask applications registered using :meth:`APIManager.init_app`.
# RestlessInfo = namedtuple('RestlessInfo', ['session',
#                                            'universal_preprocessors',
#                                            'universal_postprocessors'])

#: A tuple that stores information about a created API.
#:
#: The elements are, in order,
#:
#: - `collection_name`, the name by which a collection of instances of
#:   the model exposed by this API is known,
#: - `blueprint_name`, the name of the blueprint that contains this API,
#: - `serializer`, the subclass of :class:`Serializer` provided for the
#:   model exposed by this API.
#: - `primary_key`, the primary key used by the model
#:
APIInfo = namedtuple('APIInfo', ['collection_name', 'blueprint_name',
                                 'serializer', 'primary_key'])


class IllegalArgumentError(Exception):
    """This exception is raised when a calling function has provided illegal
    arguments to a function or method.

    """
    pass


class APIManager(object):
    """Provides a method for creating a public ReSTful JSON API with respect
    to a given :class:`~flask.Flask` application object.

    The :class:`~flask.Flask` object can either be specified in the
    constructor, or after instantiation time by calling the
    :meth:`init_app` method.

    `app` is the :class:`~flask.Flask` object containing the user's
    Flask application.

    `session` is the :class:`~sqlalchemy.orm.session.Session` object in
    which changes to the database will be made.

    `flask_sqlalchemy_db` is the :class:`~flask.ext.sqlalchemy.SQLAlchemy`
    object with which `app` has been registered and which contains the
    database models for which API endpoints will be created.

    If `flask_sqlalchemy_db` is not ``None``, `session` will be ignored.

    For example, to use this class with models defined in pure SQLAlchemy::

        from flask import Flask
        from flask.ext.restless import APIManager
        from sqlalchemy import create_engine
        from sqlalchemy.orm.session import sessionmaker

        engine = create_engine('sqlite:////tmp/mydb.sqlite')
        Session = sessionmaker(bind=engine)
        mysession = Session()
        app = Flask(__name__)
        apimanager = APIManager(app, session=mysession)

    and with models defined with Flask-SQLAlchemy::

        from flask import Flask
        from flask.ext.restless import APIManager
        from flask.ext.sqlalchemy import SQLAlchemy

        app = Flask(__name__)
        db = SQLALchemy(app)
        apimanager = APIManager(app, flask_sqlalchemy_db=db)

    `url_prefix` is the URL prefix at which each API created by this
    instance will be accessible. For example, if this is set to
    ``'foo'``, then this method creates endpoints of the form
    ``/foo/<collection_name>`` when :meth:`create_api` is called. If the
    `url_prefix` is set in the :meth:`create_api`, the URL prefix set in
    the constructor will be ignored for that endpoint.

    `postprocessors` and `preprocessors` must be dictionaries as
    described in the section :doc:`processors`. These preprocessors and
    postprocessors will be applied to all requests to and responses from
    APIs created using this APIManager object. The preprocessors and
    postprocessors given in these keyword arguments will be prepended to
    the list of processors given for each individual model when using
    the :meth:`create_api_blueprint` method (more specifically, the
    functions listed here will be executed before any functions
    specified in the :meth:`create_api_blueprint` method). For more
    information on using preprocessors and postprocessors, see
    :doc:`processors`.

    """

    #: The format of the name of the API view for a given model.
    #:
    #: This format string expects the name of a model to be provided when
    #: formatting.
    APINAME_FORMAT = '{0}api'

    def __init__(self, app=None, session=None, flask_sqlalchemy_db=None,
                 preprocessors=None, postprocessors=None, url_prefix=None):
        if session is None and flask_sqlalchemy_db is None:
            msg = 'must specify either `flask_sqlalchemy_db` or `session`'
            raise ValueError(msg)

        self.app = app

        # Stash this instance so that it can be examined later by the global
        # `url_for`, `model_for`, and `collection_name` functions.
        #
        # TODO This is a bit of poor code style because it requires the
        # APIManager to know about these global functions that use it.
        url_for.register(self)
        model_for.register(self)
        collection_name.register(self)
        serializer_for.register(self)
        primary_key_for.register(self)

        #: A mapping whose keys are models for which this object has
        #: created an API via the :meth:`create_api_blueprint` method
        #: and whose values are the corresponding collection names for
        #: those models.
        self.created_apis_for = {}

        #: List of blueprints created by :meth:`create_api` to be registered
        #: to the app when calling :meth:`init_app`.
        self.blueprints = []

        # If a Flask-SQLAlchemy object is provided, prefer the session
        # from that object.
        if flask_sqlalchemy_db is not None:
            session = flask_sqlalchemy_db.session

        # pre = preprocessors or {}
        # post = postprocessors or {}
        # self.restless_info = RestlessInfo(session, pre, post)
        self.pre = preprocessors or {}
        self.post = postprocessors or {}
        self.session = session

        #: The default URL prefix for APIs created by this manager.
        #:
        #: This can be overriden by the `url_prefix` keyword argument in the
        #: :meth:`create_api` method.
        self.url_prefix = url_prefix

        # if self.app is not None:
        #     self.init_app(self.app)

    @staticmethod
    def api_name(collection_name):
        """Returns the name of the :class:`API` instance exposing models of the
        specified type of collection.

        `collection_name` must be a string.

        """
        return APIManager.APINAME_FORMAT.format(collection_name)

    def model_for(self, collection_name):
        """Returns the SQLAlchemy model class whose type is given by the
        specified collection name.

        `collection_name` is a string containing the collection name as
        provided to the ``collection_name`` keyword argument to
        :meth:`create_api_blueprint`.

        The collection name should correspond to a model on which
        :meth:`create_api_blueprint` has been invoked previously. If it doesn't
        this method raises :exc:`ValueError`.

        This method is the inverse of :meth:`collection_name`::

            >>> from mymodels import Person
            >>> manager.create_api(Person, collection_name='people')
            >>> manager.collection_name(manager.model_for('people'))
            'people'
            >>> manager.model_for(manager.collection_name(Person))
            <class 'mymodels.Person'>

        """
        # Reverse the dictionary.
        #
        # TODO In Python 3 this should be a dict comprehension.
        models = dict((info.collection_name, model)
                      for model, info in self.created_apis_for.items())
        try:
            return models[collection_name]
        except KeyError:
            raise ValueError('Collection name {0} unknown. Be sure to set the'
                             ' `collection_name` keyword argument when calling'
                             ' `create_api()`.'.format(collection_name))

    def url_for(self, model, **kw):
        """Returns the URL for the specified model, similar to
        :func:`flask.url_for`.

        `model` is a SQLAlchemy model class. This must be a model on
        which :meth:`create_api_blueprint` has been invoked previously,
        otherwise a :exc:`KeyError` is raised.

        This method only returns URLs for endpoints created by this
        :class:`APIManager`.

        The remaining keyword arguments are passed directly on to
        :func:`flask.url_for`.

        .. _Flask request context: http://flask.pocoo.org/docs/0.10/reqcontext/

        """
        collection_name = self.created_apis_for[model].collection_name
        blueprint_name = self.created_apis_for[model].blueprint_name
        api_name = APIManager.api_name(collection_name)
        parts = [blueprint_name, api_name]
        # If we are looking for a relationship URL, the view name ends with
        # '.relationships'.
        if 'relationship' in kw and kw.pop('relationship'):
            parts.append('relationships')
        url = flask_url_for('.'.join(parts), **kw)
        # if _absolute_url:
        #     url = urljoin(request.url_root, url)
        return url

    def collection_name(self, model):
        """Returns the collection name for the specified model, as specified by
        the ``collection_name`` keyword argument to
        :meth:`create_api_blueprint`.

        `model` is a SQLAlchemy model class. This must be a model on
        which :meth:`create_api_blueprint` has been invoked previously,
        otherwise a :exc:`KeyError` is raised.

        This method only returns URLs for endpoints created by this
        :class:`APIManager`.

        """
        return self.created_apis_for[model].collection_name

    def serializer_for(self, model):
        """Returns the serializer for the specified model, as specified
        by the `serializer` keyword argument to
        :meth:`create_api_blueprint`.

        `model` is a SQLAlchemy model class. This must be a model on
        which :meth:`create_api_blueprint` has been invoked previously,
        otherwise a :exc:`KeyError` is raised.

        This method only returns URLs for endpoints created by this
        :class:`APIManager`.

        """
        return self.created_apis_for[model].serializer

    def primary_key_for(self, model):
        """Returns the primary key for the specified model, as specified
        by the `primary_key` keyword argument to
        :meth:`create_api_blueprint`.

        `model` is a SQLAlchemy model class. This must be a model on
        which :meth:`create_api_blueprint` has been invoked previously,
        otherwise a :exc:`KeyError` is raised.

        """
        return self.created_apis_for[model].primary_key

    def init_app(self, app):

        """Registers any created APIs on the given Flask application.

        This function should only be called if no Flask application was
        provided in the `app` keyword argument to the constructor of
        this class.

        When this function is invoked, any blueprint created by a
        previous invocation of :meth:`create_api` will be registered on
        `app` by calling the :meth:`~flask.Flask.register_blueprint`
        method.

        To use this method with pure SQLAlchemy, for example::

            from flask import Flask
            from flask.ext.restless import APIManager
            from sqlalchemy import create_engine
            from sqlalchemy.orm.session import sessionmaker

            engine = create_engine('sqlite:////tmp/mydb.sqlite')
            Session = sessionmaker(bind=engine)
            mysession = Session()

            # Here create model classes, for example User, Comment, etc.
            ...

            # Create the API manager and create the APIs.
            apimanager = APIManager(session=mysession)
            apimanager.create_api(User)
            apimanager.create_api(Comment)

            # Later, call `init_app` to register the blueprints for the
            # APIs created earlier.
            app = Flask(__name__)
            apimanager.init_app(app)

        and with models defined with Flask-SQLAlchemy::

            from flask import Flask
            from flask.ext.restless import APIManager
            from flask.ext.sqlalchemy import SQLAlchemy

            db = SQLALchemy(app)

            # Here create model classes, for example User, Comment, etc.
            ...

            # Create the API manager and create the APIs.
            apimanager = APIManager(flask_sqlalchemy_db=db)
            apimanager.create_api(User)
            apimanager.create_api(Comment)

            # Later, call `init_app` to register the blueprints for the
            # APIs created earlier.
            app = Flask(__name__)
            apimanager.init_app(app)

        """
        # Register any queued blueprints on the given application.
        for blueprint in self.blueprints:
            app.register_blueprint(blueprint)

    def create_api_blueprint(self, name, model, methods=READONLY_METHODS,
                             url_prefix=None, collection_name=None,
                             allow_functions=False, only=None, exclude=None,
                             additional_attributes=None,
                             validation_exceptions=None, page_size=10,
                             max_page_size=100, preprocessors=None,
                             postprocessors=None, primary_key=None,
                             serializer_class=None, deserializer_class=None,
                             includes=None, allow_to_many_replacement=False,
                             allow_delete_from_to_many_relationships=False,
                             allow_client_generated_ids=False):
        """Creates and returns a ReSTful API interface as a blueprint, but does
        not register it on any :class:`flask.Flask` application.

        The endpoints for the API for ``model`` will be available at
        ``<url_prefix>/<collection_name>``. If `collection_name` is
        ``None``, the lowercase name of the provided model class will be
        used instead, as accessed by ``model.__table__.name``. (If any
        black magic was performed on ``model.__table__``, this will be
        reflected in the endpoint URL.) For more information, see
        :ref:`collectionname`.

        This function must be called at most once for each model for which you
        wish to create a ReSTful API. Its behavior (for now) is undefined if
        called more than once.

        This function returns the :class:`flask.Blueprint` object that handles
        the endpoints for the model. The returned :class:`~flask.Blueprint` has
        *not* been registered with the :class:`~flask.Flask` application
        object specified in the constructor of this class, so you will need
        to register it yourself to make it available on the application. If you
        don't need access to the :class:`~flask.Blueprint` object, use
        :meth:`create_api_blueprint` instead, which handles registration
        automatically.

        `name` is the name of the blueprint that will be created.

        `model` is the SQLAlchemy model class for which a ReSTful interface
        will be created.

        `app` is the :class:`Flask` object on which we expect the blueprint
        created in this method to be eventually registered. If not specified,
        the Flask application specified in the constructor of this class is
        used.

        `methods` is a list of strings specifying the HTTP methods that
        will be made available on the ReSTful API for the specified
        model.

        * If ``'GET'`` is in the list, :http:method:`get` requests will
          be allowed at endpoints for collections of resources,
          resources, to-many and to-one relations of resources, and
          particular members of a to-many relation. Furthermore,
          relationship information will be accessible. For more
          information, see :doc:`fetching`.
        * If ``'POST'`` is in the list, :http:method:`post` requests
          will be allowed at endpoints for collections of resources. For
          more information, see :doc:`creating`.
        * If ``'DELETE'`` is in the list, :http:method:`delete` requests
          will be allowed at endpoints for individual resources. For
          more information, see :doc:`deleting`.
        * If ``'PATCH'`` is in the list, :http:method:`patch` requests
          will be allowed at endpoints for individual
          resources. Replacing a to-many relationship when issuing a
          request to update a resource can be enabled by setting
          ``allow_to_many_replacement`` to ``True``.

          Furthermore, to-one relationships can be updated at
          the relationship endpoints under an individual resource via
          :http:method:`patch` requests. This also allows you to add to
          a to-many relationship via the :http:method:`post` method,
          delete from a to-many relationship via the
          :http:method:`delete` method (if
          ``allow_delete_from_to_many_relationships`` is set to
          ``True``), and replace a to-many relationship via the
          :http:method:`patch` method (if ``allow_to_many_replacement``
          is set to ``True``). For more information, see :doc:`updating`
          and :doc:`updatingrelationships`.

        The default set of methods provides a read-only interface (that is,
        only :http:method:`get` requests are allowed).

        `url_prefix` is the URL prefix at which this API will be
        accessible. For example, if this is set to ``'/foo'``, then this
        method creates endpoints of the form
        ``/foo/<collection_name>``. If not set, the default URL prefix
        specified in the constructor of this class will be used. If that
        was not set either, the default ``'/api'`` will be used.

        `collection_name` is the name of the collection specified by the
        given model class to be used in the URL for the ReSTful API
        created. If this is not specified, the lowercase name of the
        model will be used. For example, if this is set to ``'foo'``,
        then this method creates endpoints of the form ``/api/foo``,
        ``/api/foo/<id>``, etc.

        If `allow_functions` is ``True``, then :http:method:`get`
        requests to ``/api/eval/<collection_name>`` will return the
        result of evaluating SQL functions specified in the body of the
        request. For information on the request format, see
        :doc:`functionevaluation`. This is ``False`` by default.

        .. warning::

           If ``allow_functions`` is ``True``, you must not create an
           API for a model whose name is ``'eval'``.

        If `only` is not ``None``, it must be a list of columns and/or
        relationships of the specified `model`, given either as strings or as
        the attributes themselves. If it is a list, only these fields will
        appear in the resource object representation of an instance of `model`.
        In other words, `only` is a whitelist of fields. The ``id`` and
        ``type`` elements of the resource object will always be present
        regardless of the value of this argument. If `only` contains a string
        that does not name a column in `model`, it will be ignored.

        If `additional_attributes` is a list of strings, these
        attributes of the model will appear in the JSON representation
        of an instance of the model. This is useful if your model has an
        attribute that is not a SQLAlchemy column but you want it to be
        exposed. If any of the attributes does not exist on the model, a
        :exc:`AttributeError` is raised.

        If `exclude` is not ``None``, it must be a list of columns and/or
        relationships of the specified `model`, given either as strings or as
        the attributes themselves. If it is a list, all fields **except** these
        will appear in the resource object representation of an instance of
        `model`. In other words, `exclude` is a blacklist of fields. The ``id``
        and ``type`` elements of the resource object will always be present
        regardless of the value of this argument. If `exclude` contains a
        string that does not name a column in `model`, it will be ignored.

        If either `only` or `exclude` is not ``None``, exactly one of them must
        be specified; if both are not ``None``, then this function will raise a
        :exc:`IllegalArgumentError`.

        See :doc:`sparse` for more information on specifying which fields will
        be included in the resource object representation.

        `validation_exceptions` is the tuple of possible exceptions raised by
        validation of your database models. If this is specified, validation
        errors will be captured and forwarded to the client in the format
        described by the JSON API specification. For more information on how to
        use validation, see :ref:`validation`.

        `page_size` must be a positive integer that represents the default page
        size for responses that consist of a collection of resources. Requests
        made by clients may override this default by specifying ``page_size``
        as a query parameter. `max_page_size` must be a positive integer that
        represents the maximum page size that a client can request. Even if a
        client specifies that greater than `max_page_size` should be returned,
        at most `max_page_size` results will be returned. For more information,
        see :doc:`pagination`.

        `serializer_class` and `deserializer_class` are custom
        serializer and deserializer classes. The former must be a
        subclass of :class:`Serializer` and the latter a subclass of
        :class:`Deserializer`. For more information on using these, see
        :doc:`serialization`.

        `preprocessors` is a dictionary mapping strings to lists of
        functions. Each key represents a type of endpoint (for example,
        ``'GET_RESOURCE'`` or ``'GET_COLLECTION'``). Each value is a list of
        functions, each of which will be called before any other code is
        executed when this API receives the corresponding HTTP request. The
        functions will be called in the order given here. The `postprocessors`
        keyword argument is essentially the same, except the given functions
        are called after all other code. For more information on preprocessors
        and postprocessors, see :doc:`processors`.

        `primary_key` is a string specifying the name of the column of `model`
        to use as the primary key for the purposes of creating URLs. If the
        `model` has exactly one primary key, there is no need to provide a
        value for this. If `model` has two or more primary keys, you must
        specify which one to use. For more information, see :ref:`primarykey`.

        `includes` must be a list of strings specifying which related resources
        will be included in a compound document by default when fetching a
        resource object representation of an instance of `model`. Each element
        of `includes` is the name of a field of `model` (that is, either an
        attribute or a relationship). For more information, see
        :doc:`includes`.

        If `allow_to_many_replacement` is ``True`` and this API allows
        :http:method:`patch` requests, the server will allow two types
        of requests.  First, it allows the client to replace the entire
        collection of resources in a to-many relationship when updating
        an individual instance of the model. Second, it allows the
        client to replace the entire to-many relationship when making a
        :http:method:`patch` request to a to-many relationship endpoint.
        This is ``False`` by default. For more information, see
        :doc:`updating` and :doc:`updatingrelationships`.

        If `allow_delete_from_to_many_relationships` is ``True`` and
        this API allows :http:method:`patch` requests, the server will
        allow the client to delete resources from any to-many
        relationship of the model. This is ``False`` by default. For
        more information, see :doc:`updatingrelationships`.

        If `allow_client_generated_ids` is ``True`` and this API allows
        :http:method:`post` requests, the server will allow the client to
        specify the ID for the resource to create. JSON API recommends that
        this be a UUID. This is ``False`` by default. For more information, see
        :doc:`creating`.

        """
        # Perform some sanity checks on the provided keyword arguments.
        if only is not None and exclude is not None:
            msg = 'Cannot simultaneously specify both `only` and `exclude`'
            raise IllegalArgumentError(msg)
        if not hasattr(model, 'id'):
            msg = 'Provided model must have an `id` attribute'
            raise IllegalArgumentError(msg)
        if collection_name == '':
            msg = 'Collection name must be nonempty'
            raise IllegalArgumentError(msg)
        if collection_name is None:
            # If the model is polymorphic in a single table inheritance
            # scenario, this should *not* be the tablename, but perhaps
            # the polymorphic identity?
            mapper = inspect(model)
            if mapper.polymorphic_identity is not None:
                collection_name = mapper.polymorphic_identity
            else:
                collection_name = model.__table__.name

        # convert all method names to upper case
        methods = frozenset((m.upper() for m in methods))
        # the name of the API, for use in creating the view and the blueprint
        apiname = APIManager.api_name(collection_name)
        # Prepend the universal preprocessors and postprocessors specified in
        # the constructor of this class.
        preprocessors_ = defaultdict(list)
        postprocessors_ = defaultdict(list)
        preprocessors_.update(preprocessors or {})
        postprocessors_.update(postprocessors or {})
        for key, value in self.pre.items():
            preprocessors_[key] = value + preprocessors_[key]
        for key, value in self.post.items():
            postprocessors_[key] = value + postprocessors_[key]
        # Validate that all the additional attributes exist on the model.
        if additional_attributes is not None:
            for attr in additional_attributes:
                if isinstance(attr, STRING_TYPES) and not hasattr(model, attr):
                    msg = 'no attribute "{0}" on model {1}'.format(attr, model)
                    raise AttributeError(msg)
        if (additional_attributes is not None and exclude is not None and
                any(attr in exclude for attr in additional_attributes)):
            msg = ('Cannot exclude attributes listed in the'
                   ' `additional_attributes` keyword argument')
            raise IllegalArgumentError(msg)
        # Create a default serializer and deserializer if none have been
        # provided.
        if serializer_class is None:
            serializer_class = DefaultSerializer
        if deserializer_class is None:
            deserializer_class = DefaultDeserializer
        # Instantiate the serializer and deserializer.
        attrs = additional_attributes
        serializer = serializer_class(only=only, exclude=exclude,
                                      additional_attributes=attrs)
        acgi = allow_client_generated_ids
        deserializer = deserializer_class(self.session, model,
                                          allow_client_generated_ids=acgi)
        # Create the view function for the API for this model.
        #
        # Rename some variables with long names for the sake of brevity.
        atmr = allow_to_many_replacement
        api_view = API.as_view(apiname, self.session, model,
                               preprocessors=preprocessors_,
                               postprocessors=postprocessors_,
                               primary_key=primary_key,
                               validation_exceptions=validation_exceptions,
                               allow_to_many_replacement=atmr,
                               page_size=page_size,
                               max_page_size=max_page_size,
                               serializer=serializer,
                               deserializer=deserializer,
                               includes=includes)

        # add the URL rules to the blueprint: the first is for methods on the
        # collection only, the second is for methods which may or may not
        # specify an instance, the third is for methods which must specify an
        # instance
        # TODO what should the second argument here be?
        # TODO should the url_prefix be specified here or in register_blueprint
        if url_prefix is not None:
            prefix = url_prefix
        elif self.url_prefix is not None:
            prefix = self.url_prefix
        else:
            prefix = DEFAULT_URL_PREFIX
        blueprint = Blueprint(name, __name__, url_prefix=prefix)
        add_rule = blueprint.add_url_rule

        # The URLs that will be routed below.
        collection_url = '/{0}'.format(collection_name)
        resource_url = '{0}/<resource_id>'.format(collection_url)
        related_resource_url = '{0}/<relation_name>'.format(resource_url)
        to_many_resource_url = \
            '{0}/<related_resource_id>'.format(related_resource_url)
        relationship_url = \
            '{0}/relationships/<relation_name>'.format(resource_url)

        # Create relationship URL endpoints.
        #
        # Due to a limitation in Flask's routing (which is actually
        # Werkzeug's routing), this needs to be declared *before* the
        # rest of the API views. Otherwise, requests like
        # :http:get:`/api/articles/1/relationships/author` interpret the
        # word `relationships` as the name of a relation of an article
        # object.
        relationship_api_name = '{0}.relationships'.format(apiname)
        rapi_view = RelationshipAPI.as_view
        adftmr = allow_delete_from_to_many_relationships
        relationship_api_view = \
            rapi_view(relationship_api_name, self.session, model,
                      # Keyword arguments for APIBase.__init__()
                      preprocessors=preprocessors_,
                      postprocessors=postprocessors_,
                      primary_key=primary_key,
                      validation_exceptions=validation_exceptions,
                      allow_to_many_replacement=allow_to_many_replacement,
                      # Keyword arguments RelationshipAPI.__init__()
                      allow_delete_from_to_many_relationships=adftmr)
        # When PATCH is allowed, certain non-PATCH requests are allowed
        # on relationship URLs.
        relationship_methods = READONLY_METHODS & methods
        if 'PATCH' in methods:
            relationship_methods |= WRITEONLY_METHODS
        add_rule(relationship_url, methods=relationship_methods,
                 view_func=relationship_api_view)

        # The URL for accessing the entire collection. (POST is special because
        # the :meth:`API.post` method doesn't have any arguments.)
        #
        # For example, /api/people.
        collection_methods = frozenset(('POST', )) & methods
        add_rule(collection_url, view_func=api_view,
                 methods=collection_methods)
        collection_methods = frozenset(('GET', )) & methods
        collection_defaults = dict(resource_id=None, relation_name=None,
                                   related_resource_id=None)
        add_rule(collection_url, view_func=api_view,
                 methods=collection_methods, defaults=collection_defaults)

        # The URL for accessing a single resource. (DELETE and PATCH are
        # special because the :meth:`API.delete` and :meth:`API.patch` methods
        # don't have the `relationname` and `relationinstid` arguments.)
        #
        # For example, /api/people/1.
        resource_methods = frozenset(('DELETE', 'PATCH')) & methods
        add_rule(resource_url, view_func=api_view, methods=resource_methods)
        resource_methods = READONLY_METHODS & methods
        resource_defaults = dict(relation_name=None, related_resource_id=None)
        add_rule(resource_url, view_func=api_view, methods=resource_methods,
                 defaults=resource_defaults)

        # The URL for accessing a related resource, which may be a to-many or a
        # to-one relationship.
        #
        # For example, /api/people/1/articles.
        related_resource_methods = READONLY_METHODS & methods
        related_resource_defaults = dict(related_resource_id=None)
        add_rule(related_resource_url, view_func=api_view,
                 methods=related_resource_methods,
                 defaults=related_resource_defaults)

        # The URL for accessing a to-many related resource.
        #
        # For example, /api/people/1/articles/1.
        to_many_resource_methods = READONLY_METHODS & methods
        add_rule(to_many_resource_url, view_func=api_view,
                 methods=to_many_resource_methods)

        # if function evaluation is allowed, add an endpoint at /api/eval/...
        # which responds only to GET requests and responds with the result of
        # evaluating functions on all instances of the specified model
        if allow_functions:
            eval_api_name = '{0}.eval'.format(apiname)
            eval_api_view = FunctionAPI.as_view(eval_api_name, self.session,
                                                model)
            eval_endpoint = '/eval{0}'.format(collection_url)
            eval_methods = ['GET']
            blueprint.add_url_rule(eval_endpoint, methods=eval_methods,
                                   view_func=eval_api_view)

        # Finally, record that this APIManager instance has created an API for
        # the specified model.
        self.created_apis_for[model] = APIInfo(collection_name, blueprint.name,
                                               serializer, primary_key)
        return blueprint

    def create_api(self, *args, **kw):
        """Creates and possibly registers a ReSTful API blueprint for
        the given SQLAlchemy model.

        If a Flask application was provided in the constructor of this
        class, the created blueprint is immediately registered on that
        application. Otherwise, the blueprint is stored for later
        registration when the :meth:`init_app` method is invoked. In
        that case, the blueprint will be registered each time the
        :meth:`init_app` method is invoked.

        The keyword arguments for this method are exactly the same as
        those for :meth:`create_api_blueprint`, and are passed directly
        to that method. However, unlike that method, this method accepts
        only a single positional argument, `model`, the SQLAlchemy model
        for which to create the API. A UUID will be automatically
        generated for the blueprint name.

        For example, if you only wish to create APIs on a single Flask
        application::

            app = Flask(__name__)
            session = ...  # create the SQLAlchemy session
            manager = APIManager(app=app, session=session)
            manager.create_api(User)

        If you want to create APIs before having access to a Flask
        application, you can call this method before calling
        :meth:`init_app`::

            session = ...  # create the SQLAlchemy session
            manager = APIManager(session=session)
            manager.create_api(User)

            # later...
            app = Flask(__name__)
            manager.init_app(app)

        If you want to create an API and register it on multiple Flask
        applications, you can call this method once and :meth:`init_app`
        multiple times with different `app` arguments::

            session = ...  # create the SQLAlchemy session
            manager = APIManager(session=session)
            manager.create_api(User)

            # later...
            app1 = Flask('application1')
            app2 = Flask('application2')
            manager.init_app(app1)
            manager.init_app(app2)

        """
        blueprint_name = str(uuid1())
        blueprint = self.create_api_blueprint(blueprint_name, *args, **kw)
        # Store the created blueprint
        self.blueprints.append(blueprint)
        # If a Flask application was provided in the constructor of this
        # API manager, then immediately register the blueprint on that
        # application.
        if self.app is not None:
            self.app.register_blueprint(blueprint)
