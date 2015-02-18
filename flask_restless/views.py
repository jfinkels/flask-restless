"""
    flask.ext.restless.views
    ~~~~~~~~~~~~~~~~~~~~~~~~

    Provides the following view classes, subclasses of
    :class:`flask.MethodView` which provide generic endpoints for interacting
    with an entity of the database:

    :class:`flask.ext.restless.views.API`
      Provides the endpoints for each of the basic HTTP methods. This is the
      main class used by the
      :meth:`flask.ext.restless.manager.APIManager.create_api` method to create
      endpoints.

    :class:`flask.ext.restless.views.FunctionAPI`
      Provides a :http:method:`get` endpoint which returns the result of
      evaluating some function on the entire collection of a given model.

    :copyright: 2011 by Lincoln de Sousa <lincoln@comum.org>
    :copyright: 2012, 2013, 2014, 2015 Jeffrey Finkelstein
                <jeffrey.finkelstein@gmail.com> and contributors.
    :license: GNU AGPLv3+ or BSD

"""
from __future__ import division

from collections import defaultdict
from functools import wraps
import math
import warnings

from flask import current_app
from flask import json
from flask import jsonify as _jsonify
from flask import request
from flask.views import MethodView
from mimerender import FlaskMimeRender
from sqlalchemy import Column
from sqlalchemy.exc import DataError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.associationproxy import AssociationProxy
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.orm.exc import MultipleResultsFound
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.query import Query
from werkzeug.exceptions import BadRequest
from werkzeug.exceptions import HTTPException
from werkzeug.urls import url_quote_plus

from .helpers import count
from .helpers import evaluate_functions
from .helpers import get_by
from .helpers import get_columns
from .helpers import get_or_create
from .helpers import get_related_model
from .helpers import get_relations
from .helpers import has_field
from .helpers import is_like_list
from .helpers import partition
from .helpers import primary_key_name
from .helpers import query_by_primary_key
from .helpers import session_query
from .helpers import strings_to_dates
from .helpers import to_dict
from .helpers import upper_keys
from .helpers import get_related_association_proxy_model
from .search import create_query
from .search import search


#: Format string for creating Link headers in paginated responses.
LINKTEMPLATE = '<{0}?page={1}&results_per_page={2}>; rel="{3}"'

#: String used internally as a dictionary key for passing header information
#: from view functions to the :func:`jsonpify` function.
_HEADERS = '__restless_headers'

#: String used internally as a dictionary key for passing status code
#: information from view functions to the :func:`jsonpify` function.
_STATUS = '__restless_status_code'


class ProcessingException(HTTPException):
    """Raised when a preprocessor or postprocessor encounters a problem.

    This exception should be raised by functions supplied in the
    ``preprocessors`` and ``postprocessors`` keyword arguments to
    :class:`APIManager.create_api`. When this exception is raised, all
    preprocessing or postprocessing halts, so any processors appearing later in
    the list will not be invoked.

    `code` is the HTTP status code of the response supplied to the client in
    the case that this exception is raised. `description` is an error message
    describing the cause of this exception. This message will appear in the
    JSON object in the body of the response to the client.

    """
    def __init__(self, description='', code=400, *args, **kwargs):
        super(ProcessingException, self).__init__(*args, **kwargs)
        self.code = code
        self.description = description


class ValidationError(Exception):
    """Raised when there is a problem deserializing a dictionary into an
    instance of a SQLAlchemy model.

    """
    pass


def _is_msie8or9():
    """Returns ``True`` if and only if the user agent of the client making the
    request indicates that it is Microsoft Internet Explorer 8 or 9.

    .. note::

       We have no way of knowing if the user agent is lying, so we just make
       our best guess based on the information provided.

    """
    # request.user_agent.version comes as a string, so we have to parse it
    version = lambda ua: tuple(int(d) for d in ua.version.split('.'))
    return (request.user_agent is not None
            and request.user_agent.version is not None
            and request.user_agent.browser == 'msie'
            and (8, 0) <= version(request.user_agent) < (10, 0))


def create_link_string(page, last_page, per_page):
    """Returns a string representing the value of the ``Link`` header.

    `page` is the number of the current page, `last_page` is the last page in
    the pagination, and `per_page` is the number of results per page.

    """
    linkstring = ''
    if page < last_page:
        next_page = page + 1
        linkstring = LINKTEMPLATE.format(request.base_url, next_page,
                                         per_page, 'next') + ', '
    linkstring += LINKTEMPLATE.format(request.base_url, last_page,
                                      per_page, 'last')
    return linkstring


def catch_processing_exceptions(func):
    """Decorator that catches :exc:`ProcessingException`s and subsequently
    returns a JSON-ified error response.

    """
    @wraps(func)
    def decorator(*args, **kw):
        try:
            return func(*args, **kw)
        except ProcessingException as exception:
            current_app.logger.exception(str(exception))
            status = exception.code
            message = exception.description or str(exception)
            return jsonify(message=message), status
    return decorator


def catch_integrity_errors(session):
    """Returns a decorator that catches database integrity errors.

    `session` is the SQLAlchemy session in which all database transactions will
    be performed.

    View methods can be wrapped like this::

        @catch_integrity_errors(session)
        def get(self, *args, **kw):
            return '...'

    Specifically, functions wrapped with the returned decorator catch
    :exc:`IntegrityError`s, :exc:`DataError`s, and
    :exc:`ProgrammingError`s. After the exceptions are caught, the session is
    rolled back, the exception is logged on the current Flask application, and
    an error response is returned to the client.

    """
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kw):
            try:
                return func(*args, **kw)
            # TODO should `sqlalchemy.exc.InvalidRequestError`s also be caught?
            except (DataError, IntegrityError, ProgrammingError) as exception:
                session.rollback()
                current_app.logger.exception(str(exception))
                return dict(message=type(exception).__name__), 400
        return wrapped
    return decorator


def set_headers(response, headers):
    """Sets the specified headers on the specified response.

    `response` is a Flask response object, and `headers` is a dictionary of
    headers to set on the specified response. Any existing headers that
    conflict with `headers` will be overwritten.

    """
    for key, value in headers.items():
        response.headers[key] = value


def jsonify(*args, **kw):
    """Same as :func:`flask.jsonify`, but sets response headers.

    If ``headers`` is a keyword argument, this function will construct the JSON
    response via :func:`flask.jsonify`, then set the specified ``headers`` on
    the response. ``headers`` must be a dictionary mapping strings to strings.

    """
    response = _jsonify(*args, **kw)
    if 'headers' in kw:
        set_headers(response, kw['headers'])
    return response


# This code is (lightly) adapted from the ``requests`` library, in the
# ``requests.utils`` module. See <http://python-requests.org> for more
# information.
def _link_to_json(value):
    """Returns a list representation of the specified HTTP Link header
    information.

    `value` is a string containing the link header information. If the link
    header information (the part of after ``Link:``) looked like this::

        <url1>; rel="next", <url2>; rel="foo"; bar="baz"

    then this function returns a list that looks like this::

        [{"url": "url1", "rel": "next"},
         {"url": "url2", "rel": "foo", "bar": "baz"}]

    This example is adapted from the documentation of GitHub's API.

    """
    links = []
    replace_chars = " '\""
    for val in value.split(","):
        try:
            url, params = val.split(";", 1)
        except ValueError:
            url, params = val, ''
        link = {}
        link["url"] = url.strip("<> '\"")
        for param in params.split(";"):
            try:
                key, value = param.split("=")
            except ValueError:
                break
            link[key.strip(replace_chars)] = value.strip(replace_chars)
        links.append(link)
    return links


def _headers_to_json(headers):
    """Returns a dictionary representation of the specified dictionary of HTTP
    headers ready for use as a JSON object.

    Pre-condition: headers is not ``None``.

    """
    link = headers.pop('Link', None)
    # Shallow copy is fine here because the `headers` dictionary maps strings
    # to strings to strings.
    result = headers.copy()
    if link:
        result['Link'] = _link_to_json(link)
    return result


def jsonpify(*args, **kw):
    """Passes the specified arguments directly to :func:`jsonify` with a status
    code of 200, then wraps the response with the name of a JSON-P callback
    function specified as a query parameter called ``'callback'`` (or does
    nothing if no such callback function is specified in the request).

    If the keyword arguments include the string specified by :data:`_HEADERS`,
    its value must be a dictionary specifying headers to set before sending the
    JSONified response to the client. Headers on the response will be
    overwritten by headers specified in this dictionary.

    If the keyword arguments include the string specified by :data:`_STATUS`,
    its value must be an integer representing the status code of the response.
    Otherwise, the status code of the response will be :http:status:`200`.

    """
    # HACK In order to make the headers and status code available in the
    # content of the response, we need to send it from the view function to
    # this jsonpify function via its keyword arguments. This is a limitation of
    # the mimerender library: it has no way of making the headers and status
    # code known to the rendering functions.
    headers = kw.pop(_HEADERS, {})
    status_code = kw.pop(_STATUS, 200)
    response = jsonify(*args, **kw)
    callback = request.args.get('callback', False)
    if callback:
        # Reload the data from the constructed JSON string so we can wrap it in
        # a JSONP function.
        data = json.loads(response.data)
        # Force the 'Content-Type' header to be 'application/javascript'.
        #
        # Note that this is different from the mimetype used in Flask for JSON
        # responses; Flask uses 'application/json'. We use
        # 'application/javascript' because a JSONP response is valid
        # Javascript, but not valid JSON.
        headers['Content-Type'] = 'application/javascript'
        # Add the headers and status code as metadata to the JSONP response.
        meta = _headers_to_json(headers) if headers is not None else {}
        meta['status'] = status_code
        inner = json.dumps(dict(meta=meta, data=data))
        content = '{0}({1})'.format(callback, inner)
        # Note that this is different from the mimetype used in Flask for JSON
        # responses; Flask uses 'application/json'. We use
        # 'application/javascript' because a JSONP response is not valid JSON.
        mimetype = 'application/javascript'
        response = current_app.response_class(content, mimetype=mimetype)
    # Set the headers on the HTTP response as well.
    if headers:
        set_headers(response, headers)
    response.status_code = status_code
    return response


def _parse_includes(column_names):
    """Returns a pair, consisting of a list of column names to include on the
    left and a dictionary mapping relation name to a list containing the names
    of fields on the related model which should be included.

    `column_names` must be a list of strings.

    If the name of a relation appears as a key in the dictionary, then it will
    not appear in the list.

    """
    dotted_names, columns = partition(column_names, lambda name: '.' in name)
    # Create a dictionary mapping relation names to fields on the related
    # model.
    relations = defaultdict(list)
    for name in dotted_names:
        relation, field = name.split('.', 1)
        # Only add the relation if it's column has been specified.
        if relation in columns:
            relations[relation].append(field)
    # Included relations need only be in the relations dictionary, not the
    # columns list.
    for relation in relations:
        if relation in columns:
            columns.remove(relation)
    return columns, relations


def _parse_excludes(column_names):
    """Returns a pair, consisting of a list of column names to exclude on the
    left and a dictionary mapping relation name to a list containing the names
    of fields on the related model which should be excluded.

    `column_names` must be a list of strings.

    If the name of a relation appears in the list then it will not appear in
    the dictionary.

    """
    dotted_names, columns = partition(column_names, lambda name: '.' in name)
    # Create a dictionary mapping relation names to fields on the related
    # model.
    relations = defaultdict(list)
    for name in dotted_names:
        relation, field = name.split('.', 1)
        # Only add the relation if it's column has not been specified.
        if relation not in columns:
            relations[relation].append(field)
    # Relations which are to be excluded entirely need only be in the columns
    # list, not the relations dictionary.
    for column in columns:
        if column in relations:
            del relations[column]
    return columns, relations


def extract_error_messages(exception):
    """Tries to extract a dictionary mapping field name to validation error
    messages from `exception`, which is a validation exception as provided in
    the ``validation_exceptions`` keyword argument in the constructor of this
    class.

    Since the type of the exception is provided by the user in the constructor
    of this class, we don't know for sure where the validation error messages
    live inside `exception`. Therefore this method simply attempts to access a
    few likely attributes and returns the first one it finds (or ``None`` if no
    error messages dictionary can be extracted).

    """
    # 'errors' comes from sqlalchemy_elixir_validations
    if hasattr(exception, 'errors'):
        return exception.errors
    # 'message' comes from savalidation
    if hasattr(exception, 'message'):
        # TODO this works only if there is one validation error
        try:
            left, right = str(exception).rsplit(':', 1)
            left_bracket = left.rindex('[')
            right_bracket = right.rindex(']')
        except ValueError as exc:
            current_app.logger.exception(str(exc))
            # could not parse the string; we're not trying too hard here...
            return None
        msg = right[:right_bracket].strip(' "')
        fieldname = left[left_bracket + 1:].strip()
        return {fieldname: msg}
    return None

#: Creates the mimerender object necessary for decorating responses with a
#: function that automatically formats the dictionary in the appropriate format
#: based on the ``Accept`` header.
#:
#: Technical details: the first pair of parantheses instantiates the
#: :class:`mimerender.FlaskMimeRender` class. The second pair of parentheses
#: creates the decorator, so that we can simply use the variable ``mimerender``
#: as a decorator.
# TODO fill in xml renderer
mimerender = FlaskMimeRender()(default='json', json=jsonpify)


class ModelView(MethodView):
    """Base class for :class:`flask.MethodView` classes which represent a view
    of a SQLAlchemy model.

    The model class for this view can be accessed from the :attr:`model`
    attribute, and the session in which all database transactions will be
    performed when dealing with this model can be accessed from the
    :attr:`session` attribute.

    When subclasses wish to make queries to the database model specified in the
    constructor, they should access the ``self.query`` function, which
    delegates to the appropriate SQLAlchemy query object or Flask-SQLAlchemy
    query object, depending on how the model has been defined.

    """

    #: List of decorators applied to every method of this class.
    decorators = [mimerender]

    def __init__(self, session, model, *args, **kw):
        """Calls the constructor of the superclass and specifies the model for
        which this class provides a ReSTful API.

        `session` is the SQLAlchemy session in which all database transactions
        will be performed.

        `model` is the SQLALchemy declarative model class of the database model
        for which this instance of the class is an API.

        """
        super(ModelView, self).__init__(*args, **kw)
        self.session = session
        self.model = model

    def query(self, model=None):
        """Returns either a SQLAlchemy query or Flask-SQLAlchemy query object
        (depending on the type of the model) on the specified `model`, or if
        `model` is ``None``, the model specified in the constructor of this
        class.

        """
        return session_query(self.session, model or self.model)


class FunctionAPI(ModelView):
    """Provides method-based dispatching for :http:method:`get` requests which
    wish to apply SQL functions to all instances of a model.

    .. versionadded:: 0.4

    """

    def get(self):
        """Returns the result of evaluating the SQL functions specified in the
        body of the request.

        For a description of the request and response formats, see
        :ref:`functionevaluation`.

        """
        if 'q' not in request.args or not request.args.get('q'):
            return dict(message='Empty query parameter'), 400
        # if parsing JSON fails, return a 400 error in JSON format
        try:
            data = json.loads(str(request.args.get('q'))) or {}
        except (TypeError, ValueError, OverflowError) as exception:
            current_app.logger.exception(str(exception))
            return dict(message='Unable to decode data'), 400
        try:
            result = evaluate_functions(self.session, self.model,
                                        data.get('functions', []))
            if not result:
                return {}, 204
            return result
        except AttributeError as exception:
            current_app.logger.exception(str(exception))
            message = 'No such field "{0}"'.format(exception.field)
            return dict(message=message), 400
        except OperationalError as exception:
            current_app.logger.exception(str(exception))
            message = 'No such function "{0}"'.format(exception.function)
            return dict(message=message), 400


class API(ModelView):
    """Provides method-based dispatching for :http:method:`get`,
    :http:method:`post`, :http:method:`patch`, :http:method:`put`, and
    :http:method:`delete` requests, for both collections of models and
    individual models.

    """

    #: List of decorators applied to every method of this class.
    decorators = ModelView.decorators + [catch_processing_exceptions]

    def __init__(self, session, model, exclude_columns=None,
                 include_columns=None, include_methods=None,
                 validation_exceptions=None, results_per_page=10,
                 max_results_per_page=100, post_form_preprocessor=None,
                 preprocessors=None, postprocessors=None, primary_key=None,
                 serializer=None, deserializer=None, *args, **kw):
        """Instantiates this view with the specified attributes.

        `session` is the SQLAlchemy session in which all database transactions
        will be performed.

        `model` is the SQLAlchemy model class for which this instance of the
        class is an API. This model should live in `database`.

        `validation_exceptions` is the tuple of exceptions raised by backend
        validation (if any exist). If exceptions are specified here, any
        exceptions which are caught when writing to the database. Will be
        returned to the client as a :http:statuscode:`400` response with a
        message specifying the validation error which occurred. For more
        information, see :ref:`validation`.

        If either `include_columns` or `exclude_columns` is not ``None``,
        exactly one of them must be specified. If both are not ``None``, then
        the behavior of this function is undefined. `exclude_columns` must be
        an iterable of strings specifying the columns of `model` which will
        *not* be present in the JSON representation of the model provided in
        response to :http:method:`get` requests.  Similarly, `include_columns`
        specifies the *only* columns which will be present in the returned
        dictionary. In other words, `exclude_columns` is a blacklist and
        `include_columns` is a whitelist; you can only use one of them per API
        endpoint. If either `include_columns` or `exclude_columns` contains a
        string which does not name a column in `model`, it will be ignored.

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
           Added the `results_per_page` keyword argument.

        .. versionadded:: 0.5
           Added the `include_columns`, and `validation_exceptions` keyword
           arguments.

        .. versionadded:: 0.4
           Added the `authentication_required_for` and
           `authentication_function` keyword arguments.

        """
        super(API, self).__init__(session, model, *args, **kw)
        if exclude_columns is None:
            self.exclude_columns, self.exclude_relations = (None, None)
        else:
            self.exclude_columns, self.exclude_relations = _parse_excludes(
                [self._get_column_name(column) for column in exclude_columns])
        if include_columns is None:
            self.include_columns, self.include_relations = (None, None)
        else:
            self.include_columns, self.include_relations = _parse_includes(
                [self._get_column_name(column) for column in include_columns])
        self.include_methods = include_methods
        self.validation_exceptions = tuple(validation_exceptions or ())
        self.results_per_page = results_per_page
        self.max_results_per_page = max_results_per_page
        self.primary_key = primary_key
        # Use our default serializer and deserializer if none are specified.
        if serializer is None:
            self.serialize = self._inst_to_dict
        else:
            self.serialize = serializer
        if deserializer is None:
            self.deserialize = self._dict_to_inst
            # And check for our own default ValidationErrors here
            self.validation_exceptions = tuple(list(self.validation_exceptions)
                                               + [ValidationError])
        else:
            self.deserialize = deserializer
        self.postprocessors = defaultdict(list)
        self.preprocessors = defaultdict(list)
        self.postprocessors.update(upper_keys(postprocessors or {}))
        self.preprocessors.update(upper_keys(preprocessors or {}))
        # move post_form_preprocessor to preprocessors['POST'] for backward
        # compatibility
        if post_form_preprocessor:
            msg = ('post_form_preprocessor is deprecated and will be removed'
                   ' in version 1.0; use preprocessors instead.')
            warnings.warn(msg, DeprecationWarning)
            self.preprocessors['POST'].append(post_form_preprocessor)
        # postprocessors for PUT are applied to PATCH because PUT is just a
        # redirect to PATCH
        for postprocessor in self.postprocessors['PUT_SINGLE']:
            self.postprocessors['PATCH_SINGLE'].append(postprocessor)
        for preprocessor in self.preprocessors['PUT_SINGLE']:
            self.preprocessors['PATCH_SINGLE'].append(preprocessor)
        for postprocessor in self.postprocessors['PUT_MANY']:
            self.postprocessors['PATCH_MANY'].append(postprocessor)
        for preprocessor in self.preprocessors['PUT_MANY']:
            self.preprocessors['PATCH_MANY'].append(preprocessor)

        # HACK: We would like to use the :attr:`API.decorators` class attribute
        # in order to decorate each view method with a decorator that catches
        # database integrity errors. However, in order to rollback the session,
        # we need to have a session object available to roll back. Therefore we
        # need to manually decorate each of the view functions here.
        decorate = lambda name, f: setattr(self, name, f(getattr(self, name)))
        for method in ['get', 'post', 'patch', 'put', 'delete']:
            decorate(method, catch_integrity_errors(self.session))

    def _get_column_name(self, column):
        """Retrieve a column name from a column attribute of SQLAlchemy
        model class, or a string.

        Raises `TypeError` when argument does not fall into either of those
        options.

        Raises `ValueError` if argument is a column attribute that belongs
        to an incorrect model class.

        """
        if hasattr(column, '__clause_element__'):
            clause_element = column.__clause_element__()
            if not isinstance(clause_element, Column):
                msg = ('Column must be a string or a column attribute'
                       ' of SQLAlchemy ORM class')
                raise TypeError(msg)
            model = column.class_
            if model is not self.model:
                msg = ('Cannot specify column of model {0} while creating API'
                       ' for model {1}').format(model.__name__,
                                                self.model.__name__)
                raise ValueError(msg)
            return clause_element.key

        return column

    def _add_to_relation(self, query, relationname, toadd=None):
        """Adds a new or existing related model to each model specified by
        `query`.

        This function does not commit the changes made to the database. The
        calling function has that responsibility.

        `query` is a SQLAlchemy query instance that evaluates to all instances
        of the model specified in the constructor of this class that should be
        updated.

        `relationname` is the name of a one-to-many relationship which exists
        on each model specified in `query`.

        `toadd` is a list of dictionaries, each representing the attributes of
        an existing or new related model to add. If a dictionary contains the
        key ``'id'``, that instance of the related model will be
        added. Otherwise, the :func:`helpers.get_or_create` class method will
        be used to get or create a model to add.

        """
        submodel = get_related_model(self.model, relationname)
        if isinstance(toadd, dict):
            toadd = [toadd]
        for dictionary in toadd or []:
            subinst = get_or_create(self.session, submodel, dictionary)
            try:
                for instance in query:
                    getattr(instance, relationname).append(subinst)
            except AttributeError as exception:
                current_app.logger.exception(str(exception))
                setattr(instance, relationname, subinst)

    def _remove_from_relation(self, query, relationname, toremove=None):
        """Removes a related model from each model specified by `query`.

        This function does not commit the changes made to the database. The
        calling function has that responsibility.

        `query` is a SQLAlchemy query instance that evaluates to all instances
        of the model specified in the constructor of this class that should be
        updated.

        `relationname` is the name of a one-to-many relationship which exists
        on each model specified in `query`.

        `toremove` is a list of dictionaries, each representing the attributes
        of an existing model to remove. If a dictionary contains the key
        ``'id'``, that instance of the related model will be
        removed. Otherwise, the instance to remove will be retrieved using the
        other attributes specified in the dictionary. If multiple instances
        match the specified attributes, only the first instance will be
        removed.

        If one of the dictionaries contains a mapping from ``'__delete__'`` to
        ``True``, then the removed object will be deleted after being removed
        from each instance of the model in the specified query.

        """
        submodel = get_related_model(self.model, relationname)
        for dictionary in toremove or []:
            remove = dictionary.pop('__delete__', False)
            if 'id' in dictionary:
                subinst = get_by(self.session, submodel, dictionary['id'])
            else:
                subinst = self.query(submodel).filter_by(**dictionary).first()
            for instance in query:
                getattr(instance, relationname).remove(subinst)
            if remove:
                self.session.delete(subinst)

    def _set_on_relation(self, query, relationname, toset=None):
        """Sets the value of the relation specified by `relationname` on each
        instance specified by `query` to have the new or existing related
        models specified by `toset`.

        This function does not commit the changes made to the database. The
        calling function has that responsibility.

        `query` is a SQLAlchemy query instance that evaluates to all instances
        of the model specified in the constructor of this class that should be
        updated.

        `relationname` is the name of a one-to-many relationship which exists
        on each model specified in `query`.

        `toset` is either a dictionary or a list of dictionaries, each
        representing the attributes of an existing or new related model to
        set. If a dictionary contains the key ``'id'``, that instance of the
        related model will be added. Otherwise, the
        :func:`helpers.get_or_create` method will be used to get or create a
        model to set.

        """
        submodel = get_related_model(self.model, relationname)
        if isinstance(toset, list):
            value = [get_or_create(self.session, submodel, d) for d in toset]
        else:
            value = get_or_create(self.session, submodel, toset)
        for instance in query:
            setattr(instance, relationname, value)

    # TODO change this to have more sensible arguments
    def _update_relations(self, query, params):
        """Adds, removes, or sets models which are related to the model
        specified in the constructor of this class.

        This function does not commit the changes made to the database. The
        calling function has that responsibility.

        This method returns a :class:`frozenset` of strings representing the
        names of relations which were modified.

        `query` is a SQLAlchemy query instance that evaluates to all instances
        of the model specified in the constructor of this class that should be
        updated.

        `params` is a dictionary containing a mapping from name of the relation
        to modify (as a string) to either a list or another dictionary. In the
        former case, the relation will be assigned the instances specified by
        the elements of the list, which are dictionaries as described below.
        In the latter case, the inner dictionary contains at most two mappings,
        one with the key ``'add'`` and one with the key ``'remove'``. Each of
        these is a mapping to a list of dictionaries which represent the
        attributes of the object to add to or remove from the relation.

        If one of the dictionaries specified in ``add`` or ``remove`` (or the
        list to be assigned) includes an ``id`` key, the object with that
        ``id`` will be attempt to be added or removed. Otherwise, an existing
        object with the specified attribute values will be attempted to be
        added or removed. If adding, a new object will be created if a matching
        object could not be found in the database.

        If a dictionary in one of the ``'remove'`` lists contains a mapping
        from ``'__delete__'`` to ``True``, then the removed object will be
        deleted after being removed from each instance of the model in the
        specified query.

        """
        relations = get_relations(self.model)
        tochange = frozenset(relations) & frozenset(params)
        for columnname in tochange:
            # Check if 'add' or 'remove' is being used
            if (isinstance(params[columnname], dict)
                and any(k in params[columnname] for k in ['add', 'remove'])):

                toadd = params[columnname].get('add', [])
                toremove = params[columnname].get('remove', [])
                self._add_to_relation(query, columnname, toadd=toadd)
                self._remove_from_relation(query, columnname,
                                           toremove=toremove)
            else:
                toset = params[columnname]
                self._set_on_relation(query, columnname, toset=toset)

        return tochange

    def _handle_validation_exception(self, exception):
        """Rolls back the session, extracts validation error messages, and
        returns a :func:`flask.jsonify` response with :http:statuscode:`400`
        containing the extracted validation error messages.

        Again, *this method calls
        :meth:`sqlalchemy.orm.session.Session.rollback`*.

        """
        self.session.rollback()
        errors = extract_error_messages(exception) or \
            'Could not determine specific validation errors'
        return dict(validation_errors=errors), 400

    def _compute_results_per_page(self):
        """Helper function which returns the number of results per page based
        on the request argument ``results_per_page`` and the server
        configuration parameters :attr:`results_per_page` and
        :attr:`max_results_per_page`.

        """
        try:
            results_per_page = int(request.args.get('results_per_page'))
        except:
            results_per_page = self.results_per_page
        if results_per_page <= 0:
            results_per_page = self.results_per_page
        return min(results_per_page, self.max_results_per_page)

    # TODO it is ugly to have `deep` as an arg here; can we remove it?
    def _paginated(self, instances, deep):
        """Returns a paginated JSONified response from the specified list of
        model instances.

        `instances` is either a Python list of model instances or a
        :class:`~sqlalchemy.orm.Query`.

        `deep` is the dictionary which defines the depth of submodels to output
        in the JSON format of the model instances in `instances`; it is passed
        directly to :func:`helpers.to_dict`.

        The response data is JSON of the form:

        .. sourcecode:: javascript

           {
             "page": 2,
             "total_pages": 3,
             "num_results": 8,
             "objects": [{"id": 1, "name": "Jeffrey", "age": 24}, ...]
           }

        """
        if isinstance(instances, list):
            num_results = len(instances)
        else:
            num_results = count(self.session, instances)
        results_per_page = self._compute_results_per_page()
        if results_per_page > 0:
            # get the page number (first page is page 1)
            page_num = int(request.args.get('page', 1))
            start = (page_num - 1) * results_per_page
            end = min(num_results, start + results_per_page)
            total_pages = int(math.ceil(num_results / results_per_page))
        else:
            page_num = 1
            start = 0
            end = num_results
            total_pages = 1
        objects = [to_dict(x, deep, exclude=self.exclude_columns,
                           exclude_relations=self.exclude_relations,
                           include=self.include_columns,
                           include_relations=self.include_relations,
                           include_methods=self.include_methods)
                   for x in instances[start:end]]
        return dict(page=page_num, objects=objects, total_pages=total_pages,
                    num_results=num_results)

    def _inst_to_dict(self, inst):
        """Returns the dictionary representation of the specified instance.

        This method respects the include and exclude columns specified in the
        constructor of this class.

        """
        # create a placeholder for the relations of the returned models
        relations = frozenset(get_relations(self.model))
        # do not follow relations that will not be included in the response
        if self.include_columns is not None:
            cols = frozenset(self.include_columns)
            rels = frozenset(self.include_relations)
            relations &= (cols | rels)
        elif self.exclude_columns is not None:
            relations -= frozenset(self.exclude_columns)
        deep = dict((r, {}) for r in relations)
        return to_dict(inst, deep, exclude=self.exclude_columns,
                       exclude_relations=self.exclude_relations,
                       include=self.include_columns,
                       include_relations=self.include_relations,
                       include_methods=self.include_methods)

    def _dict_to_inst(self, data):
        """Returns an instance of the model with the specified attributes."""
        # Check for any request parameter naming a column which does not exist
        # on the current model.
        for field in data:
            if not has_field(self.model, field):
                msg = "Model does not have field '{0}'".format(field)
                raise ValidationError(msg)

        # Getting the list of relations that will be added later
        cols = get_columns(self.model)
        relations = get_relations(self.model)

        # Looking for what we're going to set on the model right now
        colkeys = cols.keys()
        paramkeys = data.keys()
        props = set(colkeys).intersection(paramkeys).difference(relations)

        # Special case: if there are any dates, convert the string form of the
        # date into an instance of the Python ``datetime`` object.
        data = strings_to_dates(self.model, data)

        # Instantiate the model with the parameters.
        modelargs = dict([(i, data[i]) for i in props])
        instance = self.model(**modelargs)

        # Handling relations, a single level is allowed
        for col in set(relations).intersection(paramkeys):
            submodel = get_related_model(self.model, col)

            if type(data[col]) == list:
                # model has several related objects
                for subparams in data[col]:
                    subinst = get_or_create(self.session, submodel,
                                            subparams)
                    try:
                        getattr(instance, col).append(subinst)
                    except AttributeError:
                        attribute = getattr(instance, col)
                        attribute[subinst.key] = subinst.value
            else:
                # model has single related object
                subinst = get_or_create(self.session, submodel,
                                        data[col])
                setattr(instance, col, subinst)

        return instance

    def _instid_to_dict(self, instid):
        """Returns the dictionary representation of the instance specified by
        `instid`.

        If no such instance of the model exists, this method aborts with a
        :http:statuscode:`404`.

        """
        inst = get_by(self.session, self.model, instid, self.primary_key)
        if inst is None:
            return {_STATUS: 404}, 404
        return self._inst_to_dict(inst)

    def _search(self):
        """Defines a generic search function for the database model.

        If the query string is empty, or if the specified query is invalid for
        some reason (for example, searching for all person instances with), the
        response will be the JSON string ``{"objects": []}``.

        To search for entities meeting some criteria, the client makes a
        request to :http:get:`/api/<modelname>` with a query string containing
        the parameters of the search. The parameters of the search can involve
        filters. In a filter, the client specifies the name of the field by
        which to filter, the operation to perform on the field, and the value
        which is the argument to that operation. In a function, the client
        specifies the name of a SQL function which is executed on the search
        results; the result of executing the function is returned to the
        client.

        The parameters of the search must be provided in JSON form as the value
        of the ``q`` request query parameter. For example, in a database of
        people, to search for all people with a name containing a "y", the
        client would make a :http:method:`get` request to ``/api/person`` with
        query parameter as follows::

            q={"filters": [{"name": "name", "op": "like", "val": "%y%"}]}

        If multiple objects meet the criteria of the search, the response has
        :http:status:`200` and content of the form::

        .. sourcecode:: javascript

           {"objects": [{"name": "Mary"}, {"name": "Byron"}, ...]}

        If the result of the search is a single instance of the model, the JSON
        representation of that instance would be the top-level object in the
        content of the response::

        .. sourcecode:: javascript

           {"name": "Mary", ...}

        For more information SQLAlchemy operators for use in filters, see the
        `SQLAlchemy SQL expression tutorial
        <http://docs.sqlalchemy.org/en/latest/core/tutorial.html>`_.

        The general structure of request data as a JSON string is as follows::

        .. sourcecode:: javascript

           {
             "single": true,
             "order_by": [{"field": "age", "direction": "asc"}],
             "limit": 2,
             "offset": 1,
             "disjunction": true,
             "filters":
               [
                 {"name": "name", "val": "%y%", "op": "like"},
                 {"name": "age", "val": [18, 19, 20, 21], "op": "in"},
                 {"name": "age", "op": "gt", "field": "height"},
                 ...
               ]
           }

        For a complete description of all possible search parameters and
        responses, see :ref:`searchformat`.

        """
        # try to get search query from the request query parameters
        try:
            search_params = json.loads(request.args.get('q', '{}'))
        except (TypeError, ValueError, OverflowError) as exception:
            current_app.logger.exception(str(exception))
            return dict(message='Unable to decode data'), 400

        for preprocessor in self.preprocessors['GET_MANY']:
            preprocessor(search_params=search_params)

        # resolve date-strings as required by the model
        for param in search_params.get('filters', list()):
            if 'name' in param and 'val' in param:
                query_model = self.model
                query_field = param['name']
                if '__' in param['name']:
                    fieldname, relation = param['name'].split('__')
                    submodel = getattr(self.model, fieldname)
                    if isinstance(submodel, InstrumentedAttribute):
                        query_model = submodel.property.mapper.class_
                        query_field = relation
                    elif isinstance(submodel, AssociationProxy):
                        # For the sake of brevity, rename this function.
                        get_assoc = get_related_association_proxy_model
                        query_model = get_assoc(submodel)
                        query_field = relation
                to_convert = {query_field: param['val']}
                try:
                    result = strings_to_dates(query_model, to_convert)
                except ValueError as exception:
                    current_app.logger.exception(str(exception))
                    return dict(message='Unable to construct query'), 400
                param['val'] = result.get(query_field)

        # perform a filtered search
        try:
            result = search(self.session, self.model, search_params)
        except NoResultFound:
            return dict(message='No result found'), 404
        except MultipleResultsFound:
            return dict(message='Multiple results found'), 400
        except Exception as exception:
            current_app.logger.exception(str(exception))
            return dict(message='Unable to construct query'), 400

        # create a placeholder for the relations of the returned models
        relations = frozenset(get_relations(self.model))
        # do not follow relations that will not be included in the response
        if self.include_columns is not None:
            cols = frozenset(self.include_columns)
            rels = frozenset(self.include_relations)
            relations &= (cols | rels)
        elif self.exclude_columns is not None:
            relations -= frozenset(self.exclude_columns)
        deep = dict((r, {}) for r in relations)

        # for security purposes, don't transmit list as top-level JSON
        if isinstance(result, Query):
            result = self._paginated(result, deep)
            # Create the Link header.
            #
            # TODO We are already calling self._compute_results_per_page() once
            # in _paginated(); don't compute it again here.
            page, last_page = result['page'], result['total_pages']
            linkstring = create_link_string(page, last_page,
                                            self._compute_results_per_page())
            headers = dict(Link=linkstring)
        else:
            primary_key = self.primary_key or primary_key_name(result)
            result = to_dict(result, deep, exclude=self.exclude_columns,
                             exclude_relations=self.exclude_relations,
                             include=self.include_columns,
                             include_relations=self.include_relations,
                             include_methods=self.include_methods)
            # The URL at which a client can access the instance matching this
            # search query.
            url = '{0}/{1}'.format(request.base_url, result[primary_key])
            headers = dict(Location=url)

        for postprocessor in self.postprocessors['GET_MANY']:
            postprocessor(result=result, search_params=search_params)

        # HACK Provide the headers directly in the result dictionary, so that
        # the :func:`jsonpify` function has access to them. See the note there
        # for more information.
        result[_HEADERS] = headers
        return result, 200, headers

    def get(self, instid, relationname, relationinstid):
        """Returns a JSON representation of an instance of model with the
        specified name.

        If ``instid`` is ``None``, this method returns the result of a search
        with parameters specified in the query string of the request. If no
        search parameters are specified, this method returns all instances of
        the specified model.

        If ``instid`` is an integer, this method returns the instance of the
        model with that identifying integer. If no such instance exists, this
        method responds with :http:status:`404`.

        """
        if instid is None:
            return self._search()
        for preprocessor in self.preprocessors['GET_SINGLE']:
            temp_result = preprocessor(instance_id=instid)
            # Let the return value of the preprocessor be the new value of
            # instid, thereby allowing the preprocessor to effectively specify
            # which instance of the model to process on.
            #
            # We assume that if the preprocessor returns None, it really just
            # didn't return anything, which means we shouldn't overwrite the
            # instid.
            if temp_result is not None:
                instid = temp_result
        # get the instance of the "main" model whose ID is instid
        instance = get_by(self.session, self.model, instid, self.primary_key)
        if instance is None:
            return {_STATUS: 404}, 404
        # If no relation is requested, just return the instance. Otherwise,
        # get the value of the relation specified by `relationname`.
        if relationname is None:
            result = self.serialize(instance)
        else:
            related_value = getattr(instance, relationname)
            # create a placeholder for the relations of the returned models
            related_model = get_related_model(self.model, relationname)
            relations = frozenset(get_relations(related_model))
            deep = dict((r, {}) for r in relations)
            if relationinstid is not None:
                related_value_instance = get_by(self.session, related_model,
                                                relationinstid)
                if related_value_instance is None:
                    return {_STATUS: 404}, 404
                result = to_dict(related_value_instance, deep)
            else:
                # for security purposes, don't transmit list as top-level JSON
                if is_like_list(instance, relationname):
                    result = self._paginated(list(related_value), deep)
                else:
                    result = to_dict(related_value, deep)
        if result is None:
            return {_STATUS: 404}, 404
        for postprocessor in self.postprocessors['GET_SINGLE']:
            postprocessor(result=result)
        return result

    def _delete_many(self):
        """Deletes multiple instances of the model.

        If search parameters are provided via the ``q`` query parameter, only
        those instances matching the search parameters will be deleted.

        If no instances were deleted, this returns a
        :http:status:`404`. Otherwise, it returns a :http:status:`200` with the
        number of deleted instances in the body of the response.

        """
        # try to get search query from the request query parameters
        try:
            search_params = json.loads(request.args.get('q', '{}'))
        except (TypeError, ValueError, OverflowError) as exception:
            current_app.logger.exception(str(exception))
            return dict(message='Unable to decode search query'), 400

        for preprocessor in self.preprocessors['DELETE_MANY']:
            preprocessor(search_params=search_params)

        # perform a filtered search
        try:
            # HACK We need to ignore any ``order_by`` request from the client,
            # because for some reason, SQLAlchemy does not allow calling
            # delete() on a query that has an ``order_by()`` on it. If you
            # attempt to call delete(), you get this error:
            #
            #     sqlalchemy.exc.InvalidRequestError: Can't call Query.delete()
            #     when order_by() has been called
            #
            result = search(self.session, self.model, search_params,
                            _ignore_order_by=True)
        except NoResultFound:
            return dict(message='No result found'), 404
        except MultipleResultsFound:
            return dict(message='Multiple results found'), 400
        except Exception as exception:
            current_app.logger.exception(str(exception))
            return dict(message='Unable to construct query'), 400

        # for security purposes, don't transmit list as top-level JSON
        if isinstance(result, Query):
            # Implementation note: `synchronize_session=False`, described in
            # the SQLAlchemy documentation for
            # :meth:`sqlalchemy.orm.query.Query.delete`, states that this is
            # the most efficient option for bulk deletion, and is reliable once
            # the session has expired, which occurs after the session commit
            # below.
            num_deleted = result.delete(synchronize_session=False)
        else:
            self.session.delete(result)
            num_deleted = 1
        self.session.commit()
        result = dict(num_deleted=num_deleted)
        for postprocessor in self.postprocessors['DELETE_MANY']:
            postprocessor(result=result, search_params=search_params)
        return (result, 200) if num_deleted > 0 else 404

    def delete(self, instid, relationname, relationinstid):
        """Removes the specified instance of the model with the specified name
        from the database.

        Although :http:method:`delete` is an idempotent method according to
        :rfc:`2616`, idempotency only means that subsequent identical requests
        cannot have additional side-effects. Since the response code is not a
        side effect, this method responds with :http:status:`204` only if an
        object is deleted, and with :http:status:`404` when nothing is deleted.

        If `relationname

        .. versionadded:: 0.12.0
           Added the `relationinstid` keyword argument.

        .. versionadded:: 0.10.0
           Added the `relationname` keyword argument.

        """
        if instid is None:
            # If no instance ID is provided, this request is an attempt to
            # delete many instances of the model via a search with possible
            # filters.
            return self._delete_many()
        was_deleted = False
        for preprocessor in self.preprocessors['DELETE_SINGLE']:
            temp_result = preprocessor(instance_id=instid,
                                       relation_name=relationname,
                                       relation_instance_id=relationinstid)
            # See the note under the preprocessor in the get() method.
            if temp_result is not None:
                instid = temp_result
        inst = get_by(self.session, self.model, instid, self.primary_key)
        if relationname:
            # If the request is ``DELETE /api/person/1/computers``, error 400.
            if not relationinstid:
                msg = ('Cannot DELETE entire "{0}"'
                       ' relation').format(relationname)
                return dict(message=msg), 400
            # Otherwise, get the related instance to delete.
            relation = getattr(inst, relationname)
            related_model = get_related_model(self.model, relationname)
            relation_instance = get_by(self.session, related_model,
                                       relationinstid)
            # Removes an object from the relation list.
            relation.remove(relation_instance)
            was_deleted = len(self.session.dirty) > 0
        elif inst is not None:
            self.session.delete(inst)
            was_deleted = len(self.session.deleted) > 0
        self.session.commit()
        for postprocessor in self.postprocessors['DELETE_SINGLE']:
            postprocessor(was_deleted=was_deleted)
        return {}, 204 if was_deleted else 404

    def post(self):
        """Creates a new instance of a given model based on request data.

        This function parses the string contained in
        :attr:`flask.request.data`` as a JSON object and then validates it with
        a validator specified in the constructor of this class.

        The :attr:`flask.request.data` attribute will be parsed as a JSON
        object containing the mapping from field name to value to which to
        initialize the created instance of the model.

        After that, it separates all columns that defines relationships with
        other entities, creates a model with the simple columns and then
        creates instances of these submodels and associates them with the
        related fields. This happens only at the first level of nesting.

        Currently, this method can only handle instantiating a model with a
        single level of relationship data.

        """
        content_type = request.headers.get('Content-Type', None)
        content_is_json = content_type.startswith('application/json')
        is_msie = _is_msie8or9()
        # Request must have the Content-Type: application/json header, unless
        # the User-Agent string indicates that the client is Microsoft Internet
        # Explorer 8 or 9 (which has a fixed Content-Type of 'text/html'; see
        # issue #267).
        if not is_msie and not content_is_json:
            msg = 'Request must have "Content-Type: application/json" header'
            return dict(message=msg), 415

        # try to read the parameters for the model from the body of the request
        try:
            # HACK Requests made from Internet Explorer 8 or 9 don't have the
            # correct content type, so request.get_json() doesn't work.
            if is_msie:
                data = json.loads(request.get_data()) or {}
            else:
                data = request.get_json() or {}
        except (BadRequest, TypeError, ValueError, OverflowError) as exception:
            current_app.logger.exception(str(exception))
            return dict(message='Unable to decode data'), 400

        # apply any preprocessors to the POST arguments
        for preprocessor in self.preprocessors['POST']:
            preprocessor(data=data)

        try:
            # Convert the dictionary representation into an instance of the
            # model.
            instance = self.deserialize(data)
            # Add the created model to the session.
            self.session.add(instance)
            self.session.commit()
            # Get the dictionary representation of the new instance as it
            # appears in the database.
            result = self.serialize(instance)
        except self.validation_exceptions as exception:
            return self._handle_validation_exception(exception)
        # Determine the value of the primary key for this instance and
        # encode URL-encode it (in case it is a Unicode string).
        pk_name = self.primary_key or primary_key_name(instance)
        primary_key = result[pk_name]
        try:
            primary_key = str(primary_key)
        except UnicodeEncodeError:
            primary_key = url_quote_plus(primary_key.encode('utf-8'))
        # The URL at which a client can access the newly created instance
        # of the model.
        url = '{0}/{1}'.format(request.base_url, primary_key)
        # Provide that URL in the Location header in the response.
        headers = dict(Location=url)
        for postprocessor in self.postprocessors['POST']:
            postprocessor(result=result)
        return result, 201, headers

    def patch(self, instid, relationname, relationinstid):
        """Updates the instance specified by ``instid`` of the named model, or
        updates multiple instances if ``instid`` is ``None``.

        The :attr:`flask.request.data` attribute will be parsed as a JSON
        object containing the mapping from field name to value to which to
        update the specified instance or instances.

        If ``instid`` is ``None``, the query string will be used to search for
        instances (using the :func:`_search` method), and all matching
        instances will be updated according to the content of the request data.
        See the :func:`_search` documentation on more information about search
        parameters for restricting the set of instances on which updates will
        be made in this case.

        This function ignores the `relationname` and `relationinstid` keyword
        arguments.

        .. versionadded:: 0.12.0
           Added the `relationinstid` keyword argument.

        .. versionadded:: 0.10.0
           Added the `relationname` keyword argument.

        """
        content_type = request.headers.get('Content-Type', None)
        content_is_json = content_type.startswith('application/json')
        is_msie = _is_msie8or9()
        # Request must have the Content-Type: application/json header, unless
        # the User-Agent string indicates that the client is Microsoft Internet
        # Explorer 8 or 9 (which has a fixed Content-Type of 'text/html'; see
        # issue #267).
        if not is_msie and not content_is_json:
            msg = 'Request must have "Content-Type: application/json" header'
            return dict(message=msg), 415

        # try to load the fields/values to update from the body of the request
        try:
            # HACK Requests made from Internet Explorer 8 or 9 don't have the
            # correct content type, so request.get_json() doesn't work.
            if is_msie:
                data = json.loads(request.get_data()) or {}
            else:
                data = request.get_json() or {}
        except (BadRequest, TypeError, ValueError, OverflowError) as exception:
            # this also happens when request.data is empty
            current_app.logger.exception(str(exception))
            return dict(message='Unable to decode data'), 400

        # Check if the request is to patch many instances of the current model.
        patchmany = instid is None
        # Perform any necessary preprocessing.
        if patchmany:
            # Get the search parameters; all other keys in the `data`
            # dictionary indicate a change in the model's field.
            search_params = data.pop('q', {})
            for preprocessor in self.preprocessors['PATCH_MANY']:
                preprocessor(search_params=search_params, data=data)
        else:
            for preprocessor in self.preprocessors['PATCH_SINGLE']:
                temp_result = preprocessor(instance_id=instid, data=data)
                # See the note under the preprocessor in the get() method.
                if temp_result is not None:
                    instid = temp_result

        # Check for any request parameter naming a column which does not exist
        # on the current model.
        for field in data:
            if not has_field(self.model, field):
                msg = "Model does not have field '{0}'".format(field)
                return dict(message=msg), 400

        if patchmany:
            try:
                # create a SQLALchemy Query from the query parameter `q`
                query = create_query(self.session, self.model, search_params)
            except Exception as exception:
                current_app.logger.exception(str(exception))
                return dict(message='Unable to construct query'), 400
        else:
            # create a SQLAlchemy Query which has exactly the specified row
            query = query_by_primary_key(self.session, self.model, instid,
                                         self.primary_key)
            if query.count() == 0:
                return {_STATUS: 404}, 404
            assert query.count() == 1, 'Multiple rows with same ID'

        try:
            relations = self._update_relations(query, data)
        except self.validation_exceptions as exception:
            current_app.logger.exception(str(exception))
            return self._handle_validation_exception(exception)
        field_list = frozenset(data) ^ relations
        data = dict((field, data[field]) for field in field_list)

        # Special case: if there are any dates, convert the string form of the
        # date into an instance of the Python ``datetime`` object.
        data = strings_to_dates(self.model, data)

        try:
            # Let's update all instances present in the query
            num_modified = 0
            if data:
                for item in query.all():
                    for field, value in data.items():
                        setattr(item, field, value)
                    num_modified += 1
            self.session.commit()
        except self.validation_exceptions as exception:
            current_app.logger.exception(str(exception))
            return self._handle_validation_exception(exception)

        # Perform any necessary postprocessing.
        if patchmany:
            result = dict(num_modified=num_modified)
            for postprocessor in self.postprocessors['PATCH_MANY']:
                postprocessor(query=query, result=result,
                              search_params=search_params)
        else:
            result = self._instid_to_dict(instid)
            for postprocessor in self.postprocessors['PATCH_SINGLE']:
                postprocessor(result=result)

        return result

    def put(self, *args, **kw):
        """Alias for :meth:`patch`."""
        return self.patch(*args, **kw)
