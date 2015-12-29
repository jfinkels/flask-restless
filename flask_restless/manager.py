# manager.py - class that creates endpoints compliant JSON API
#
# Copyright 2011 Lincoln de Sousa <lincoln@comum.org>.
# Copyright 2012, 2013, 2014, 2015 Jeffrey Finkelstein
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
try:
    from urllib.parse import urljoin
except ImportError:
    from urlparse import urljoin

import flask
from flask import request
from flask import Blueprint

from .helpers import collection_name
from .helpers import model_for
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

#: A triple that stores the SQLAlchemy session and the universal pre- and post-
#: processors to be applied to any API created for a particular Flask
#: application.
#:
#: These tuples are used by :class:`APIManager` to store information about
#: Flask applications registered using :meth:`APIManager.init_app`.
RestlessInfo = namedtuple('RestlessInfo', ['session',
                                           'universal_preprocessors',
                                           'universal_postprocessors'])

#: A tuple that stores information about a created API.
#:
#: The first element, `collection_name`, is the name by which a collection of
#: instances of the model which this API exposes is known. The second element,
#: `blueprint_name`, is the name of the blueprint that contains this API.
APIInfo = namedtuple('APIInfo', 'collection_name blueprint_name')


class IllegalArgumentError(Exception):
    """This exception is raised when a calling function has provided illegal
    arguments to a function or method.

    """
    pass


class APIManager(object):
    """Provides a method for creating a public ReSTful JSON API with respect to
    a given :class:`~flask.Flask` application object.

    The :class:`~flask.Flask` object can be specified in the constructor, or
    after instantiation time by calling the :meth:`init_app` method. In any
    case, the application object must be specified before calling the
    :meth:`create_api` method.

    `app` is the :class:`flask.Flask` object containing the user's Flask
    application.

    `session` is the :class:`sqlalchemy.orm.session.Session` object in which
    changes to the database will be made.

    `flask_sqlalchemy_db` is the :class:`flask.ext.sqlalchemy.SQLAlchemy`
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

    """

    #: The format of the name of the API view for a given model.
    #:
    #: This format string expects the name of a model to be provided when
    #: formatting.
    APINAME_FORMAT = '{0}api'

    #: The format of the name of the blueprint containing the API view for a
    #: given model.
    #:
    #: This format string expects the following to be provided when formatting:
    #:
    #: 1. name of the API view of a specific model
    #: 2. a number representing the number of times a blueprint with that name
    #:    has been registered.
    BLUEPRINTNAME_FORMAT = '{0}{1}'

    def __init__(self, app=None, **kw):
        self.app = app

        #: Dictionary mapping Flask application objects to a list of (args, kw)
        #: pairs for which API creation has been delayed, as when calling
        #: :meth:`create_api` before calling :meth:`init_app`.
        self.apis_to_create = defaultdict(list)

        #: A mapping whose keys are models for which this object has created an
        #: API via the :meth:`create_api_blueprint` method and whose values are
        #: the corresponding collection names for those models.
        self.created_apis_for = {}

        #: The Flask-SQLAlchemy database object.
        self.flask_sqlalchemy_db = kw.pop('flask_sqlalchemy_db', None)

        #: The SQLAlchemy session object on which changes to the model will be
        #: made.
        self.session = kw.pop('session', None)

        # Stash this instance so that it can be examined later by the global
        # `url_for`, `model_for`, and `collection_name` functions.
        #
        # TODO This is a bit of poor code style because it requires the
        # APIManager to know about these global functions that use it.
        url_for.register(self)
        model_for.register(self)
        collection_name.register(self)

        if self.app is not None:
            self.init_app(self.app, **kw)

    @staticmethod
    def _next_blueprint_name(blueprints, basename):
        """Returns the next name for a blueprint with the specified base name.

        This method returns a string of the form ``'{0}{1}'.format(basename,
        number)``, where ``number`` is the next non-negative integer not
        already used in the name of an existing blueprint.

        For example, if `basename` is ``'personapi'`` and blueprints already
        exist with names ``'personapi0'``, ``'personapi1'``, and
        ``'personapi2'``, then this function would return ``'personapi3'``. We
        expect that code which calls this function will subsequently register a
        blueprint with that name, but that is not necessary.

        `blueprints` is the list of blueprint names that already exist, as read
        from :attr:`Flask.blueprints` (that attribute is really a dictionary,
        but we simply iterate over the keys, which are names of the
        blueprints).

        """
        # blueprints is a dict whose keys are the names of the blueprints
        existing = [name for name in blueprints if name.startswith(basename)]
        # if this is the first one...
        if not existing:
            next_number = 0
        else:
            # for brevity
            b = basename
            existing_numbers = [int(n.partition(b)[-1]) for n in existing]
            next_number = max(existing_numbers) + 1
        return APIManager.BLUEPRINTNAME_FORMAT.format(basename, next_number)

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
        # In Python 3 this should be:
        #
        #     models = {info.collection_name: model
        #               for model, info in self.created_apis_for.items()}
        #
        models = dict((info.collection_name, model)
                      for model, info in self.created_apis_for.items())
        try:
            return models[collection_name]
        except KeyError:
            raise ValueError('Collection name {0} unknown. Be sure to set the'
                             ' `collection_name` keyword argument when calling'
                             ' `create_api()`.'.format(collection_name))

    def url_for(self, model, _absolute_url=True, **kw):
        """Returns the URL for the specified model, similar to
        :func:`flask.url_for`.

        `model` is a SQLAlchemy model class. This must be a model on
        which :meth:`create_api_blueprint` has been invoked previously,
        otherwise a :exc:`KeyError` is raised.

        If `_absolute_url` is ``False``, this function will return just the URL
        path without the ``scheme`` and ``netloc`` part of the URL. If it is
        ``True``, this function joins the relative URL to the url root for the
        current request. This means `_absolute_url` can only be set to ``True``
        if this function is called from within a `Flask request context`_. For
        example::

            >>> from mymodels import Person
            >>> manager.create_api(Person)
            >>> manager.url_for(Person, instid=3)
            'http://example.com/api/people/3'
            >>> manager.url_for(Person, instid=3, _absolute_url=False)
            '/api/people/3'

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
        url = flask.url_for('.'.join(parts), **kw)
        if _absolute_url:
            url = urljoin(request.url_root, url)
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

    def init_app(self, app, session=None, flask_sqlalchemy_db=None,
                 preprocessors=None, postprocessors=None):
        """Stores the specified :class:`flask.Flask` application object on
        which API endpoints will be registered and the
        :class:`sqlalchemy.orm.session.Session` object in which all database
        changes will be made.

        `session` is the :class:`sqlalchemy.orm.session.Session` object in
        which changes to the database will be made.

        `flask_sqlalchemy_db` is the :class:`flask.ext.sqlalchemy.SQLAlchemy`
        object with which `app` has been registered and which contains the
        database models for which API endpoints will be created.

        If `flask_sqlalchemy_db` is not ``None``, `session` will be ignored.

        This is for use in the situation in which this class must be
        instantiated before the :class:`~flask.Flask` application has been
        created.

        To use this method with pure SQLAlchemy, for example::

            from flask import Flask
            from flask.ext.restless import APIManager
            from sqlalchemy import create_engine
            from sqlalchemy.orm.session import sessionmaker

            apimanager = APIManager()

            # later...

            engine = create_engine('sqlite:////tmp/mydb.sqlite')
            Session = sessionmaker(bind=engine)
            mysession = Session()
            app = Flask(__name__)
            apimanager.init_app(app, session=mysession)

        and with models defined with Flask-SQLAlchemy::

            from flask import Flask
            from flask.ext.restless import APIManager
            from flask.ext.sqlalchemy import SQLAlchemy

            apimanager = APIManager()

            # later...

            app = Flask(__name__)
            db = SQLALchemy(app)
            apimanager.init_app(app, flask_sqlalchemy_db=db)

        `postprocessors` and `preprocessors` must be dictionaries as described
        in the section :ref:`processors`. These preprocessors and
        postprocessors will be applied to all requests to and responses from
        APIs created using this APIManager object. The preprocessors and
        postprocessors given in these keyword arguments will be prepended to
        the list of processors given for each individual model when using the
        :meth:`create_api_blueprint` method (more specifically, the functions
        listed here will be executed before any functions specified in the
        :meth:`create_api_blueprint` method). For more information on using
        preprocessors and postprocessors, see :ref:`processors`.

        """
        # If the SQLAlchemy database was provided in the constructor, use that.
        if flask_sqlalchemy_db is None:
            flask_sqlalchemy_db = self.flask_sqlalchemy_db
        # If the session was provided in the constructor, use that.
        if session is None:
            session = self.session
        session = session or getattr(flask_sqlalchemy_db, 'session', None)
        # Use the `extensions` dictionary on the provided Flask object to store
        # extension-specific information.
        if not hasattr(app, 'extensions'):
            app.extensions = {}
        if 'restless' in app.extensions:
            raise ValueError('Flask-Restless has already been initialized on'
                             ' this application: {0}'.format(app))
        app.extensions['restless'] = RestlessInfo(session,
                                                  preprocessors or {},
                                                  postprocessors or {})
        # Now that this application has been initialized, create blueprints for
        # which API creation was deferred in :meth:`create_api`. This includes
        # all (args, kw) pairs for the key in :attr:`apis_to_create`
        # corresponding to ``app``, as well as any (args, kw) pairs
        # corresponding to the ``None`` key, which represents a call to
        # :meth:`create_api` that is just waiting for any Flask application to
        # be initialized.
        #
        # Rename apis_to_create for the sake of brevity
        apis = self.apis_to_create
        to_create = apis.pop(app, []) + apis.pop(None, [])
        for args, kw in to_create:
            blueprint = self.create_api_blueprint(app=app, *args, **kw)
            app.register_blueprint(blueprint)

    def create_api_blueprint(self, model, app=None, methods=READONLY_METHODS,
                             url_prefix='/api', collection_name=None,
                             allow_functions=False, only=None, exclude=None,
                             additional_attributes=None,
                             validation_exceptions=None, page_size=10,
                             max_page_size=100, preprocessors=None,
                             postprocessors=None, primary_key=None,
                             serializer=None, deserializer=None,
                             includes=None, allow_to_many_replacement=False,
                             allow_delete_from_to_many_relationships=False,
                             allow_client_generated_ids=False):
        """Creates and returns a ReSTful API interface as a blueprint, but does
        not register it on any :class:`flask.Flask` application.

        The endpoints for the API for ``model`` will be available at
        ``<url_prefix>/<collection_name>``. If `collection_name` is ``None``,
        the lowercase name of the provided model class will be used instead, as
        accessed by ``model.__tablename__``. (If any black magic was performed
        on ``model.__tablename__``, this will be reflected in the endpoint
        URL.) For more information, see :ref:`collectionname`.

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
          information, see :ref:`fetching`.
        * If ``'POST'`` is in the list, :http:method:`post` requests
          will be allowed at endpoints for collections of resources. For
          more information, see :ref:`creating`.
        * If ``'DELETE'`` is in the list, :http:method:`delete` requests
          will be allowed at endpoints for individual resources. For
          more information, see :ref:`deleting`.
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
          is set to ``True``). For more information, see :ref:`updating`
          and :ref:`updatingrelationships`.

        The default set of methods provides a read-only interface (that is,
        only :http:method:`get` requests are allowed).

        `url_prefix` is the URL prefix at which this API will be
        accessible. For example, if this is set to ``'foo'``, then this
        method creates endpoints of the form ``/foo/<collection_name>``.

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
        :ref:`functionevaluation`. This is ``False`` by default.

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
        exposed.

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

        See :ref:`sparse` for more information on specifying which fields will
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
        see :ref:`pagination`.

        `serializer` and `deserializer` are custom serialization
        functions. The former function must take a single positional
        argument representing the instance of the model to serialize and
        an additional keyword argument ``only`` representing the fields
        to include in the serialized representation of the instance, and
        must return a dictionary representation of that instance. The
        latter function must take a single argument representing the
        dictionary representation of an instance of the model and must
        return an instance of `model` that has those attributes. For
        more information, see :ref:`serialization`.

        `preprocessors` is a dictionary mapping strings to lists of
        functions. Each key represents a type of endpoint (for example,
        ``'GET_RESOURCE'`` or ``'GET_COLLECTION'``). Each value is a list of
        functions, each of which will be called before any other code is
        executed when this API receives the corresponding HTTP request. The
        functions will be called in the order given here. The `postprocessors`
        keyword argument is essentially the same, except the given functions
        are called after all other code. For more information on preprocessors
        and postprocessors, see :ref:`processors`.

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
        :ref:`includes`.

        If `allow_to_many_replacement` is ``True`` and this API allows
        :http:method:`patch` requests, the server will allow two types
        of requests.  First, it allows the client to replace the entire
        collection of resources in a to-many relationship when updating
        an individual instance of the model. Second, it allows the
        client to replace the entire to-many relationship when making a
        :http:method:`patch` request to a to-many relationship endpoint.
        This is ``False`` by default. For more information, see
        :ref:`updating` and :ref:`updatingrelationships`.

        If `allow_delete_from_to_many_relationships` is ``True`` and
        this API allows :http:method:`patch` requests, the server will
        allow the client to delete resources from any to-many
        relationship of the model. This is ``False`` by default. For
        more information, see :ref:`updatingrelationships`.

        If `allow_client_generated_ids` is ``True`` and this API allows
        :http:method:`post` requests, the server will allow the client to
        specify the ID for the resource to create. JSON API recommends that
        this be a UUID. This is ``False`` by default. For more information, see
        :ref:`creating`.

        """
        # Perform some sanity checks on the provided keyword arguments.
        if only is not None and exclude is not None:
            msg = ('Cannot simultaneously specify both include columns and'
                   ' exclude columns.')
            raise IllegalArgumentError(msg)
        if not hasattr(model, 'id'):
            msg = 'Provided model must have an `id` attribute'
            raise IllegalArgumentError(msg)
        if collection_name == '':
            msg = 'Collection name must be nonempty'
            raise IllegalArgumentError(msg)
        # If no Flask application is specified, use the one (we assume) was
        # specified in the constructor.
        if app is None:
            app = self.app
        restlessinfo = app.extensions['restless']
        if collection_name is None:
            collection_name = model.__tablename__
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
        for key, value in restlessinfo.universal_preprocessors.items():
            preprocessors_[key] = value + preprocessors_[key]
        for key, value in restlessinfo.universal_postprocessors.items():
            postprocessors_[key] = value + postprocessors_[key]
        # Create a default serializer and deserializer if none have been
        # provided.
        if serializer is None:
            serializer = DefaultSerializer(only, exclude,
                                           additional_attributes)
            # if validation_exceptions is None:
            #     validation_exceptions = [DeserializationException]
            # else:
            #     validation_exceptions.append(DeserializationException)
        if deserializer is None:
            deserializer = DefaultDeserializer(restlessinfo.session, model)
        # Create the view function for the API for this model.
        #
        # Rename some variables with long names for the sake of brevity.
        atmr = allow_to_many_replacement
        acgi = allow_client_generated_ids
        api_view = API.as_view(apiname, restlessinfo.session, model,
                               # Keyword arguments for APIBase.__init__()
                               preprocessors=preprocessors_,
                               postprocessors=postprocessors_,
                               primary_key=primary_key,
                               validation_exceptions=validation_exceptions,
                               allow_to_many_replacement=atmr,
                               # Keyword arguments for API.__init__()
                               page_size=page_size,
                               max_page_size=max_page_size,
                               serializer=serializer,
                               deserializer=deserializer,
                               includes=includes,
                               allow_client_generated_ids=acgi)
        # suffix an integer to apiname according to already existing blueprints
        blueprintname = APIManager._next_blueprint_name(app.blueprints,
                                                        apiname)
        # add the URL rules to the blueprint: the first is for methods on the
        # collection only, the second is for methods which may or may not
        # specify an instance, the third is for methods which must specify an
        # instance
        # TODO what should the second argument here be?
        # TODO should the url_prefix be specified here or in register_blueprint
        blueprint = Blueprint(blueprintname, __name__, url_prefix=url_prefix)
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
            rapi_view(relationship_api_name, restlessinfo.session, model,
                      # Keyword arguments for APIBase.__init__()
                      preprocessors=preprocessors_,
                      postprocessors=postprocessors_,
                      primary_key=primary_key,
                      validation_exceptions=validation_exceptions,
                      allow_to_many_replacement=allow_to_many_replacement,
                      # Keyword arguments RelationshipAPI.__init__()
                      allow_delete_from_to_many_relationships=adftmr)
        # TODO Document this rather mysterious behavior, that these non-PATCH
        # methods are allowed on relationship URLs.
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
            eval_api_view = FunctionAPI.as_view(eval_api_name,
                                                restlessinfo.session, model)
            eval_endpoint = '/eval{0}'.format(collection_url)
            eval_methods = ['GET']
            blueprint.add_url_rule(eval_endpoint, methods=eval_methods,
                                   view_func=eval_api_view)

        # Finally, record that this APIManager instance has created an API for
        # the specified model.
        self.created_apis_for[model] = APIInfo(collection_name, blueprint.name)
        return blueprint

    def create_api(self, *args, **kw):
        """Creates and registers a ReSTful API blueprint on the
        :class:`flask.Flask` application specified in the constructor of this
        class.

        The positional and keyword arguments are passed directly to the
        :meth:`create_api_blueprint` method, so see the documentation there.

        This is essentially a convenience method for the following code::

            blueprint = apimanager.create_api_blueprint(*args, **kw)
            app.register_blueprint(blueprint)

        """
        # Check if the user is providing a specific Flask application with
        # which the model's API will be associated.
        if 'app' in kw:
            # If an application object was already provided in the constructor,
            # raise an error indicating that the user is being confusing.
            if self.app is not None:
                msg = ('Cannot provide a Flask application in the APIManager'
                       ' constructor and in create_api(); must choose exactly'
                       ' one')
                raise IllegalArgumentError(msg)
            app = kw.pop('app')
            # If the Flask application has already been initialized, then
            # immediately create the API blueprint.
            #
            # TODO This is something of a fragile check for whether or not
            # init_app() has been called on kw['app'], since some other
            # (malicious) code could simply add the key 'restless' to the
            # extensions dictionary.
            if 'restless' in app.extensions:
                blueprint = self.create_api_blueprint(app=app, *args, **kw)
                app.register_blueprint(blueprint)
            # If the Flask application has not yet been initialized, then stash
            # the positional and keyword arguments for later initialization.
            else:
                self.apis_to_create[app].append((args, kw))
        # The user did not provide a Flask application here.
        else:
            # If a Flask application object was already provided in the
            # constructor, immediately create the API blueprint.
            if self.app is not None:
                app = self.app
                blueprint = self.create_api_blueprint(app=app, *args, **kw)
                app.register_blueprint(blueprint)
            # If no Flask application was provided in the constructor either,
            # then stash the positional and keyword arguments for later
            # initalization.
            else:
                self.apis_to_create[None].append((args, kw))
