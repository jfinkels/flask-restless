"""
    flask.ext.restless.manager
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    Provides :class:`flask.ext.restless.manager.APIManager`, the class which
    users of Flask-Restless must instantiate to create ReSTful APIs for their
    database models.

    :copyright:2011 by Lincoln de Sousa <lincoln@comum.org>
    :copyright: 2012, 2013, 2014, 2015 Jeffrey Finkelstein
                <jeffrey.finkelstein@gmail.com> and contributors.
    :license: GNU AGPLv3+ or BSD

"""
from collections import defaultdict
from collections import namedtuple

import flask
from flask import Blueprint

from .helpers import primary_key_name
from .helpers import url_for
from .views import API
from .views import FunctionAPI

#: The set of methods which are allowed by default when creating an API
READONLY_METHODS = frozenset(('GET', ))


#: A triple that stores the SQLAlchemy session and the universal pre- and post-
#: processors to be applied to any API created for a particular Flask
#: application.
#:
#: These tuples are used by :class:`APIManager` to store information about
#: Flask applications registered using :meth:`APIManager.init_app`.
RestlessInfo = namedtuple('RestlessInfo', ['session',
                                           'universal_preprocessors',
                                           'universal_postprocessors'])

#: A global list of created :class:`APIManager` objects.
created_managers = []

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

        # Stash this instance so that it can be examined later by other
        # functions in this module.
        url_for.created_managers.append(self)

        self.flask_sqlalchemy_db = kw.pop('flask_sqlalchemy_db', None)
        self.session = kw.pop('session', None)
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

    def collection_name(self, model):
        """Returns the name by which the user told us to call collections of
        instances of this model.

        `model` is a SQLAlchemy model class. This must be a model on which
        :meth:`create_api_blueprint` has been invoked previously.

        """
        return self.created_apis_for[model].collection_name

    def blueprint_name(self, model):
        """Returns the name of the blueprint in which an API was created for
        the specified model.

        `model` is a SQLAlchemy model class. This must be a model on which
        :meth:`create_api_blueprint` has been invoked previously.

        """
        return self.created_apis_for[model].blueprint_name

    def url_for(self, model, **kw):
        """Returns the URL for the specified model, similar to
        :func:`flask.url_for`.

        `model` is a SQLAlchemy model class. This must be a model on which
        :meth:`create_api_blueprint` has been invoked previously.

        This method only returns URLs for endpoints created by this
        :class:`APIManager`.

        The remaining keyword arguments are passed directly on to
        :func:`flask.url_for`.

        """
        collection_name = self.collection_name(model)
        api_name = APIManager.api_name(collection_name)
        blueprint_name = self.blueprint_name(model)
        joined = '.'.join([blueprint_name, api_name])
        return flask.url_for(joined, **kw)

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

        .. versionadded:: 0.13.0
           Added the `preprocessors` and `postprocessors` keyword arguments.

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
                             allow_patch_many=False, allow_delete_many=False,
                             allow_functions=False, exclude_columns=None,
                             include_columns=None, include_methods=None,
                             validation_exceptions=None, results_per_page=10,
                             max_results_per_page=100,
                             post_form_preprocessor=None, preprocessors=None,
                             postprocessors=None, primary_key=None,
                             serializer=None, deserializer=None):
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

        This function returns the :class:`flask.Blueprint` object which handles
        the endpoints for the model. The returned :class:`~flask.Blueprint` has
        already been registered with the :class:`~flask.Flask` application
        object specified in the constructor of this class, so you do *not* need
        to register it yourself.

        `model` is the SQLAlchemy model class for which a ReSTful interface
        will be created. Note this must be a class, not an instance of a class.

        `app` is the :class:`Flask` object on which we expect the blueprint
        created in this method to be eventually registered. If not specified,
        the Flask application specified in the constructor of this class is
        used.

        `methods` specify the HTTP methods which will be made available on the
        ReSTful API for the specified model, subject to the following caveats:

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

        `url_prefix` the URL prefix at which this API will be accessible.

        If `allow_patch_many` is ``True``, then requests to
        :http:patch:`/api/<collection_name>?q=<searchjson>` will attempt to
        patch the attributes on each of the instances of the model which match
        the specified search query. This is ``False`` by default. For
        information on the search query parameter ``q``, see
        :ref:`searchformat`.

        If `allow_delete_many` is ``True``, then requests to
        :http:delete:`/api/<collection_name>?q=<searchjson>` will attempt to
        delete each instance of the model that matches the specified search
        query. This is ``False`` by default. For information on the search
        query parameter ``q``, see :ref:`searchformat`.

        `validation_exceptions` is the tuple of possible exceptions raised by
        validation of your database models. If this is specified, validation
        errors will be captured and forwarded to the client in JSON format. For
        more information on how to use validation, see :ref:`validation`.

        If `allow_functions` is ``True``, then requests to
        :http:get:`/api/eval/<collection_name>` will return the result of
        evaluating SQL functions specified in the body of the request. For
        information on the request format, see :ref:`functionevaluation`. This
        if ``False`` by default. Warning: you must not create an API for a
        model whose name is ``'eval'`` if you set this argument to ``True``.

        If either `include_columns` or `exclude_columns` is not ``None``,
        exactly one of them must be specified. If both are not ``None``, then
        this function will raise a :exc:`IllegalArgumentError`.
        `exclude_columns` must be an iterable of strings specifying the columns
        of `model` which will *not* be present in the JSON representation of
        the model provided in response to :http:method:`get` requests.
        Similarly, `include_columns` specifies the *only* columns which will be
        present in the returned dictionary. In other words, `exclude_columns`
        is a blacklist and `include_columns` is a whitelist; you can only use
        one of them per API endpoint. If either `include_columns` or
        `exclude_columns` contains a string which does not name a column in
        `model`, it will be ignored.

        If you attempt to either exclude a primary key field or not include a
        primary key field for :http:method:`post` requests, this method will
        raise an :exc:`IllegalArgumentError`.

        If `include_columns` is an iterable of length zero (like the empty
        tuple or the empty list), then the returned dictionary will be
        empty. If `include_columns` is ``None``, then the returned dictionary
        will include all columns not excluded by `exclude_columns`.

        If `include_methods` is an iterable of strings, the methods with names
        corresponding to those in this list will be called and their output
        included in the response.

        See :ref:`includes` for information on specifying included or excluded
        columns on fields of related models.

        `results_per_page` is a positive integer which represents the default
        number of results which are returned per page. Requests made by clients
        may override this default by specifying ``results_per_page`` as a query
        argument. `max_results_per_page` is a positive integer which represents
        the maximum number of results which are returned per page. This is a
        "hard" upper bound in the sense that even if a client specifies that
        greater than `max_results_per_page` should be returned, only
        `max_results_per_page` results will be returned. For more information,
        see :ref:`serverpagination`.

        .. deprecated:: 0.9.2
           The `post_form_preprocessor` keyword argument is deprecated in
           version 0.9.2. It will be removed in version 1.0. Replace code that
           looks like this::

               manager.create_api(Person, post_form_preprocessor=foo)

           with code that looks like this::

               manager.create_api(Person, preprocessors=dict(POST=[foo]))

           See :ref:`processors` for more information and examples.

        `post_form_preprocessor` is a callback function which takes
        POST input parameters loaded from JSON and enhances them with other
        key/value pairs. The example use of this is when your ``model``
        requires to store user identity and for security reasons the identity
        is not read from the post parameters (where malicious user can tamper
        with them) but from the session.

        `preprocessors` is a dictionary mapping strings to lists of
        functions. Each key is the name of an HTTP method (for example,
        ``'GET'`` or ``'POST'``). Each value is a list of functions, each of
        which will be called before any other code is executed when this API
        receives the corresponding HTTP request. The functions will be called
        in the order given here. The `postprocessors` keyword argument is
        essentially the same, except the given functions are called after all
        other code. For more information on preprocessors and postprocessors,
        see :ref:`processors`.

        `primary_key` is a string specifying the name of the column of `model`
        to use as the primary key for the purposes of creating URLs. If the
        `model` has exactly one primary key, there is no need to provide a
        value for this. If `model` has two or more primary keys, you must
        specify which one to use.

        `serializer` and `deserializer` are custom serialization functions. The
        former function must take a single argument representing the instance
        of the model to serialize, and must return a dictionary representation
        of that instance. The latter function must take a single argument
        representing the dictionary representation of an instance of the model
        and must return an instance of `model` that has those attributes. For
        more information, see :ref:`serialization`.

        .. versionadded:: 0.17.0
           Added the `serializer` and `deserializer` keyword arguments.

        .. versionadded:: 0.16.0
           Added the `app` and `allow_delete_many` keyword arguments.

        .. versionadded:: 0.13.0
           Added the `primary_key` keyword argument.

        .. versionadded:: 0.10.2
           Added the `include_methods` keyword argument.

        .. versionchanged:: 0.10.0
           Removed `authentication_required_for` and `authentication_function`
           keyword arguments.

           Use the `preprocesors` and `postprocessors` keyword arguments
           instead. For more information, see :ref:`authentication`.

        .. versionadded:: 0.9.2
           Added the `preprocessors` and `postprocessors` keyword arguments.

        .. versionadded:: 0.9.0
           Added the `max_results_per_page` keyword argument.

        .. versionadded:: 0.7
           Added the `exclude_columns` keyword argument.

        .. versionadded:: 0.6
           This functionality was formerly in :meth:`create_api`, but the
           blueprint creation and registration have now been separated.

        .. versionadded:: 0.6
           Added the `results_per_page` keyword argument.

        .. versionadded:: 0.5
           Added the `include_columns` and `validation_exceptions` keyword
           argument.

        .. versionadded:: 0.4
           Added the `allow_functions`, `allow_patch_many`,
           `authentication_required_for`, `authentication_function`, and
           `collection_name` keyword arguments.

        .. versionadded:: 0.4
           Force the model name in the URL to lowercase.

        """
        if exclude_columns is not None and include_columns is not None:
            msg = ('Cannot simultaneously specify both include columns and'
                   ' exclude columns.')
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
        # sets of methods used for different types of endpoints
        no_instance_methods = methods & frozenset(('POST', ))
        instance_methods = \
            methods & frozenset(('GET', 'PATCH', 'DELETE', 'PUT'))
        possibly_empty_instance_methods = methods & frozenset(('GET', ))
        if allow_patch_many and ('PATCH' in methods or 'PUT' in methods):
            possibly_empty_instance_methods |= frozenset(('PATCH', 'PUT'))
        if allow_delete_many and 'DELETE' in methods:
            possibly_empty_instance_methods |= frozenset(('DELETE', ))

        # Check that primary_key is included for no_instance_methods
        if no_instance_methods:
            pk_name = primary_key or primary_key_name(model)
            if (include_columns and pk_name not in include_columns or
                exclude_columns and pk_name in exclude_columns):
                msg = ('The primary key must be included for APIs with POST.')
                raise IllegalArgumentError(msg)

        # the base URL of the endpoints on which requests will be made
        collection_endpoint = '/{0}'.format(collection_name)
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
        # the view function for the API for this model
        api_view = API.as_view(apiname, restlessinfo.session, model,
                               exclude_columns, include_columns,
                               include_methods, validation_exceptions,
                               results_per_page, max_results_per_page,
                               post_form_preprocessor, preprocessors_,
                               postprocessors_, primary_key, serializer,
                               deserializer)
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
        # For example, /api/person.
        blueprint.add_url_rule(collection_endpoint,
                               methods=no_instance_methods, view_func=api_view)
        # For example, /api/person/1.
        blueprint.add_url_rule(collection_endpoint,
                               defaults={'instid': None, 'relationname': None,
                                         'relationinstid': None},
                               methods=possibly_empty_instance_methods,
                               view_func=api_view)
        # the per-instance endpoints will allow both integer and string primary
        # key accesses
        instance_endpoint = '{0}/<instid>'.format(collection_endpoint)
        # For example, /api/person/1.
        blueprint.add_url_rule(instance_endpoint, methods=instance_methods,
                               defaults={'relationname': None,
                                         'relationinstid': None},
                               view_func=api_view)
        # add endpoints which expose related models
        relation_endpoint = '{0}/<relationname>'.format(instance_endpoint)
        relation_instance_endpoint = \
            '{0}/<relationinstid>'.format(relation_endpoint)
        # For example, /api/person/1/computers.
        blueprint.add_url_rule(relation_endpoint,
                               methods=possibly_empty_instance_methods,
                               defaults={'relationinstid': None},
                               view_func=api_view)
        # For example, /api/person/1/computers/2.
        blueprint.add_url_rule(relation_instance_endpoint,
                               methods=instance_methods,
                               view_func=api_view)
        # if function evaluation is allowed, add an endpoint at /api/eval/...
        # which responds only to GET requests and responds with the result of
        # evaluating functions on all instances of the specified model
        if allow_functions:
            eval_api_name = apiname + 'eval'
            eval_api_view = FunctionAPI.as_view(eval_api_name,
                                                restlessinfo.session, model)
            eval_endpoint = '/eval' + collection_endpoint
            blueprint.add_url_rule(eval_endpoint, methods=['GET'],
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

        This is a convenience method for the following code::

            blueprint = apimanager.create_api_blueprint(*args, **kw)
            app.register_blueprint(blueprint)

        .. versionchanged:: 0.6
           The blueprint creation has been moved to
           :meth:`create_api_blueprint`; the registration remains here.

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
