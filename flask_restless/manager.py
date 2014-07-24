"""
    flask.ext.restless.manager
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    Provides :class:`flask.ext.restless.manager.APIManager`, the class which
    users of Flask-Restless must instantiate to create ReSTful APIs for their
    database models.

    :copyright:2011 by Lincoln de Sousa <lincoln@comum.org>
    :copyright:2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
from collections import defaultdict

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

    def __init__(self, app=None, session=None, flask_sqlalchemy_db=None,
                 preprocessors=None, postprocessors=None):
        self.init_app(app, session, flask_sqlalchemy_db, preprocessors,
                      postprocessors)

    def _next_blueprint_name(self, basename):
        """Returns the next name for a blueprint with the specified base name.

        This method returns a string of the form ``'{0}{1}'.format(basename,
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
        return APIManager.BLUEPRINTNAME_FORMAT.format(basename, next_number)

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
        self.app = app
        self.session = session or getattr(flask_sqlalchemy_db, 'session', None)
        self.universal_preprocessors = preprocessors or {}
        self.universal_postprocessors = postprocessors or {}

    def create_api_blueprint(self, model, methods=READONLY_METHODS,
                             url_prefix='/api', collection_name=None,
                             allow_patch_many=False, allow_functions=False,
                             exclude_columns=None, include_columns=None,
                             include_methods=None, validation_exceptions=None,
                             results_per_page=10, max_results_per_page=100,
                             post_form_preprocessor=None,
                             preprocessors=None, postprocessors=None,
                             primary_key=None):
        """Creates and returns a ReSTful API interface as a blueprint, but does
        not register it on any :class:`flask.Flask` application.

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

        `model` is the SQLAlchemy model class for which a ReSTful interface
        will be created. Note this must be a class, not an instance of a class.

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
        if collection_name is None:
            collection_name = model.__tablename__
        # convert all method names to upper case
        methods = frozenset((m.upper() for m in methods))
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
        collection_endpoint = '/{0}'.format(collection_name)
        # the name of the API, for use in creating the view and the blueprint
        apiname = APIManager.APINAME_FORMAT.format(collection_name)
        # Prepend the universal preprocessors and postprocessors specified in
        # the constructor of this class.
        preprocessors_ = defaultdict(list)
        postprocessors_ = defaultdict(list)
        preprocessors_.update(preprocessors or {})
        postprocessors_.update(postprocessors or {})
        for key, value in self.universal_preprocessors.items():
            preprocessors_[key] = value + preprocessors_[key]
        for key, value in self.universal_postprocessors.items():
            postprocessors_[key] = value + postprocessors_[key]
        # the view function for the API for this model
        api_view = API.as_view(apiname, self.session, model, exclude_columns,
                               include_columns, include_methods,
                               validation_exceptions, results_per_page,
                               max_results_per_page, post_form_preprocessor,
                               preprocessors_, postprocessors_, primary_key)
        # suffix an integer to apiname according to already existing blueprints
        blueprintname = self._next_blueprint_name(apiname)
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
            eval_api_view = FunctionAPI.as_view(eval_api_name, self.session,
                                                model)
            eval_endpoint = '/eval' + collection_endpoint
            blueprint.add_url_rule(eval_endpoint, methods=['GET'],
                                   view_func=eval_api_view)
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
        blueprint = self.create_api_blueprint(*args, **kw)
        self.app.register_blueprint(blueprint)
