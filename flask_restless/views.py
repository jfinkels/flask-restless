"""
    flask.ext.restless.views
    ~~~~~~~~~~~~~~~~~~~~~~~~

    Provides the following view classes, subclasses of
    :class:`flask.MethodView` which provide generic endpoints for fetching,
    creating, updating, and deleting instances of a SQLAlchemy model.

    The implementations here are designed to meet the requirements of the JSON
    API specification.

    :class:`API`

      Provides the endpoints for accessing resources via each of the basic HTTP
      methods. This is the main class used by the :meth:`APIManager.create_api`
      method to create endpoints.

    :class:`RelationshipAPI`

      Provides endpoints for accessing relationship URLs. This allows accessing
      **link objects**, as described in the JSON API specification.

    :class:`FunctionAPI`

      Provides a :http:method:`get` endpoint which returns the result of
      evaluating a given function on the entire collection of a given model.

    :copyright: 2011 by Lincoln de Sousa <lincoln@comum.org>
    :copyright: 2012, 2013, 2014, 2015 Jeffrey Finkelstein
                <jeffrey.finkelstein@gmail.com> and contributors.
    :license: GNU AGPLv3+ or BSD

"""
from __future__ import division

from collections import defaultdict
from functools import wraps
from itertools import chain
import math

from flask import current_app
from flask import json
from flask import jsonify
from flask import request
from flask.views import MethodView
from mimerender import FlaskMimeRender
from mimerender import register_mime
from sqlalchemy.exc import DataError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm.exc import FlushError
from sqlalchemy.orm.exc import MultipleResultsFound
from sqlalchemy.orm.exc import NoResultFound
from werkzeug.exceptions import BadRequest
from werkzeug.exceptions import HTTPException

from .helpers import changes_on_update
from .helpers import collection_name
from .helpers import count
from .helpers import evaluate_functions
from .helpers import get_by
from .helpers import get_model
from .helpers import get_related_model
from .helpers import has_field
from .helpers import is_like_list
from .helpers import primary_key_name
from .helpers import primary_key_value
from .helpers import strings_to_datetimes
from .helpers import upper_keys
from .helpers import url_for
from .search import ComparisonToNull
from .search import search
from .serialization import DefaultSerializer
from .serialization import DefaultDeserializer
from .serialization import DeserializationException
from .serialization import SerializationException

#: Format string for creating the complete URL for a paginated response.
LINKTEMPLATE = '{0}?page[number]={1}&page[size]={2}'

#: String used internally as a dictionary key for passing header information
#: from view functions to the :func:`jsonpify` function.
_HEADERS = '__restless_headers'

#: String used internally as a dictionary key for passing status code
#: information from view functions to the :func:`jsonpify` function.
_STATUS = '__restless_status_code'

#: The Content-Type we expect for most requests to APIs.
#:
#: The JSON API specification requires the content type to be
#: ``application/vnd.api+json``.
CONTENT_TYPE = 'application/vnd.api+json'

#: SQLAlchemy errors that, when caught, trigger a rollback of the session.
ROLLBACK_ERRORS = (DataError, IntegrityError, ProgrammingError, FlushError)

# For the sake of brevity, rename this function.
chain = chain.from_iterable

# Register the JSON API content type so that mimerender knows to look for it.
register_mime('jsonapi', (CONTENT_TYPE, ))


class SortKeyError(KeyError):
    """Raised when attempting to parse the sort query parameter reveals that
    the client did not correctly specify the sort order using ``'+'`` or
    ``'-'``.

    """
    pass


class SingleKeyError(KeyError):
    """Raised when attempting to parse the "single" query parameter reveals
    that the client did not correctly provide a Boolean value.

    """
    pass


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


def catch_processing_exceptions(func):
    """Decorator that catches :exc:`ProcessingException`s and subsequently
    returns a JSON-ified error response.

    """
    @wraps(func)
    def new_func(*args, **kw):
        try:
            return func(*args, **kw)
        except ProcessingException as exception:
            current_app.logger.exception(str(exception))
            detail = exception.description or str(exception)
            return error_response(exception.code, detail=detail)
    return new_func


def requires_json_api_accept(func):
    """Decorator that requires requests have the ``Accept`` header required by
    the JSON API specification.

    If the request does not have the correct ``Accept`` header, a
    :http:status:`406` response is returned.

    View methods can be wrapped like this::

        @requires_json_api_accept
        def get(self, *args, **kw):
            return '...'

    """
    @wraps(func)
    def new_func(*args, **kw):
        if request.headers.get('Accept') != CONTENT_TYPE:
            detail = ('Request must have "Accept: {0}"'
                      ' header'.format(CONTENT_TYPE))
            return error_response(406, detail=detail)
        return func(*args, **kw)
    return new_func


def requires_json_api_mimetype(func):
    """Decorator that requires requests have the ``Content-Type`` header
    required by the JSON API specification.

    If the request does not have the correct ``Content-Type`` header, a
    :http:status:`415` response is returned.

    View methods can be wrapped like this::

        @requires_json_api_mimetype
        def get(self, *args, **kw):
            return '...'

    """
    @wraps(func)
    def new_func(*args, **kw):
        content_type = request.headers.get('Content-Type')
        content_is_json = content_type.startswith(CONTENT_TYPE)
        is_msie = _is_msie8or9()
        # Request must have the Content-Type: application/vnd.api+json header,
        # unless the User-Agent string indicates that the client is Microsoft
        # Internet Explorer 8 or 9 (which has a fixed Content-Type of
        # 'text/html'; for more information, see issue #267).
        if not is_msie and not content_is_json:
            detail = ('Request must have "Content-Type: {0}"'
                      ' header').format(CONTENT_TYPE)
            return error_response(415, detail=detail)
        return func(*args, **kw)
    return new_func


def catch_integrity_errors(session):
    """Returns a decorator that catches database integrity errors.

    `session` is the SQLAlchemy session in which all database transactions will
    be performed.

    View methods can be wrapped like this::

        @catch_integrity_errors(session)
        def get(self, *args, **kw):
            return '...'

    Specifically, functions wrapped with the returned decorator catch the
    exceptions specified in :data:`ROLLBACK_ERRORS`. After the exceptions are
    caught, the session is rolled back, the exception is logged on the current
    Flask application, and an error response is returned to the client.

    """
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kw):
            try:
                return func(*args, **kw)
            # TODO should `sqlalchemy.exc.InvalidRequestError`s also be caught?
            except ROLLBACK_ERRORS as exception:
                session.rollback()
                current_app.logger.exception(str(exception))
                # Special status code for conflicting instances: 409 Conflict
                status = 409 if is_conflict(exception) else 400
                return dict(message=type(exception).__name__), status
        return wrapped
    return decorator


def is_conflict(exception):
    """Returns ``True`` if and only if the specified exception represents a
    conflict in the database.

    """
    string = str(exception)
    return 'conflicts with' in string or 'UNIQUE constraint failed' in string


def jsonpify(*args, **kw):
    """Returns a JSONP response, with the specified arguments passed directly
    to :func:`flask.jsonify`.

    If the request has a query parameter ``calback=foo``, then the body of the
    response will be ``foo(<json>)``, where ``<json>`` is the JSON object that
    would have been returned normally. If no such query parameter exists, this
    simply returns ``<json>`` as normal.

    The positional and keyword arguments are passed directly to
    :func:`flask.jsonify`, with the following exceptions.

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
        document = json.loads(response.data)
        # Force the 'Content-Type' header to be 'application/javascript'.
        #
        # Note that this is different from the mimetype used in Flask for JSON
        # responses; Flask uses 'application/json'. We use
        # 'application/javascript' because a JSONP response is valid
        # Javascript, but not valid JSON (and not a valid JSON API document).
        mimetype = 'application/javascript'
        headers['Content-Type'] = mimetype
        # # Add the headers and status code as metadata to the JSONP response.
        # meta = _headers_to_json(headers) if headers is not None else {}
        meta = {}
        meta['status'] = status_code
        if 'meta' in document:
            document['meta'].update(meta)
        else:
            document['meta'] = meta
        inner = json.dumps(document)
        content = '{0}({1})'.format(callback, inner)
        # Note that this is different from the mimetype used in Flask for JSON
        # responses; Flask uses 'application/json'. We use
        # 'application/javascript' because a JSONP response is not valid JSON.
        response = current_app.response_class(content, mimetype=mimetype)
    if 'Content-Type' not in headers:
        headers['Content-Type'] = CONTENT_TYPE
    # Set the headers on the HTTP response as well.
    if headers:
        for key, value in headers.items():
            response.headers.set(key, value)
    response.status_code = status_code
    return response


def parse_sparse_fields(type_=None):
    """Get the sparse fields as requested by the client.

    Returns a dictionary mapping resource type names to set of fields to
    include for that resource.

    For example, if the client requests::

        GET /articles?fields[articles]=title,body&fields[people]=name

    then::

        >>> parse_sparse_fields()
        {'articles': {'title', 'body'}, 'people': {'name'}}

    If the `type_` argument is given, only the set of fields for that resource
    type will be returned::

        >>> parse_sparse_fields('articles')
        {'title', 'body'}

    """
    # TODO use a regular expression to ensure field parameters are of the
    # correct format? (maybe ``fields\[[^\[\]\.]*\]``)
    fields = {key[7:-1]: set(value.split(','))
              for key, value in request.args.items()
              if key.startswith('fields[') and key.endswith(']')}
    return fields.get(type_) if type_ is not None else fields


# TODO these need to become JSON Pointers
def extract_error_messages(exception):
    """Tries to extract a dictionary mapping field name to validation error
    messages from `exception`, which is a validation exception as provided in
    the ``validation_exceptions`` keyword argument to the constructor of the
    :class:`APIBase` class.

    Since the type of the exception is provided by the user in the constructor
    of that class, we cannot know for sure where the validation error messages
    live inside `exception`. Therefore this method simply attempts to access a
    few likely attributes and returns the first one it finds (or ``None`` if no
    error messages dictionary can be extracted).

    """
    # Check for our own built-in validation error.
    if isinstance(exception, DeserializationException):
        return exception.args[0]
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


def error(id=None, href=None, status=None, code=None, title=None,
          detail=None, links=None, paths=None):
    """Returns a dictionary representation of an error as described in the JSON
    API specification.

    For more information, see the `Errors`_ section of the JSON API
    specification.

    .. Errors_: http://jsonapi.org/format/#errors

    """
    # HACK We use locals() so we don't have to list every keyword argument.
    if all(kwvalue is None for kwvalue in locals().values()):
        raise ValueError('At least one of the arguments must not be None.')
    return dict(id=id, href=href, status=status, code=code, title=title,
                detail=detail, links=links, paths=paths)


def error_response(status, **kw):
    """Returns a correctly formatted error response with the specified
    parameters.

    This is a convenience function for::

        errors_response(status, [error(**kw)])

    For more information, see :func:`errors_response`.

    """
    return errors_response(status, [error(**kw)])


def errors_response(status, errors):
    """Return an error response with multiple errors.

    `status` is an integer representing an HTTP status code corresponding to an
    error response.

    `errors` is a list of error dictionaries, each of which must satisfy the
    requirements of the JSON API specification.

    This function returns a two-tuple whose left element is a dictionary
    containing the errors under the top-level key ``errors`` and whose right
    element is `status`.

    The returned dictionary object also includes a key with a special name,
    stored in the key :data:`_STATUS`, which is used to workaround an
    incompatibility between Flask and mimerender that doesn't allow setting
    headers on a global response object.

    The keys within each error object are described in the `Errors`_ section of
    the JSON API specification.

    .. _Errors: http://jsonapi.org/format/#errors

    """
    return {'errors': errors, _STATUS: status}, status


#: Creates the mimerender object necessary for decorating responses with a
#: function that automatically formats the dictionary in the appropriate format
#: based on the ``Accept`` header.
#:
#: Technical details: the first pair of parentheses instantiates the
#: :class:`mimerender.FlaskMimeRender` class. The second pair of parentheses
#: creates the decorator, so that we can simply use the variable ``mimerender``
#: as a decorator.
# TODO fill in xml renderer
mimerender = FlaskMimeRender()(default='jsonapi', jsonapi=jsonpify)


class ModelView(MethodView):
    """Base class for :class:`flask.MethodView` classes which represent a view
    of a SQLAlchemy model.

    `session` is the SQLAlchemy session in which all database transactions will
    be performed.

    `model` is the SQLALchemy declarative model class of the database model for
    which this instance of the class is an API.

    The model class for this view can be accessed from the :attr:`model`
    attribute, and the session in which all database transactions will be
    performed when dealing with this model can be accessed from the
    :attr:`session` attribute.

    """

    #: List of decorators applied to every method of this class.
    #:
    #: If a subclass must add more decorators, prepend them to this list::
    #:
    #:     class MyView(ModelView):
    #:         decorators = [my_decorator] + ModelView.decorators
    #:
    #: This way, the :data:`mimerender` function appears last. It must appear
    #: last so that it can render the returned dictionary.
    decorators = [requires_json_api_accept, requires_json_api_mimetype,
                  mimerender]

    def __init__(self, session, model, *args, **kw):
        super(ModelView, self).__init__(*args, **kw)
        self.session = session
        self.model = model


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
        if 'functions' not in request.args:
            detail = 'Must provide `functions` query parameter'
            return error_response(400, detail=detail)
        functions = request.args.get('functions')
        try:
            data = json.loads(str(functions)) or []
        except (TypeError, ValueError, OverflowError) as exception:
            current_app.logger.exception(str(exception))
            detail = 'Unable to decode JSON in `functions` query parameter'
            return error_response(400, detail=detail)
        try:
            result = evaluate_functions(self.session, self.model, data)
        except AttributeError as exception:
            current_app.logger.exception(str(exception))
            detail = 'No such field "{0}"'.format(exception.field)
            return error_response(400, detail=detail)
        except KeyError as exception:
            current_app.logger.exception(str(exception))
            return error_response(400, detail=str(exception))
        except OperationalError as exception:
            current_app.logger.exception(str(exception))
            detail = 'No such function "{0}"'.format(exception.function)
            return error_response(400, detail=detail)
        return dict(data=result)


class APIBase(ModelView):
    """Base class for view classes that provide fetch, create, update, and
    delete functionality for resources and relationships on resources.

    `session` and `model` are as described in the constructor of the
    superclass.

    `preprocessors` and `postprocessors` are as described in :ref:`processors`.

    `primary_key` is as described in :ref:`primarykey`.

    `validation_exceptions` are as described in :ref:`validation_exceptions`.

    `allow_to_many_replacement` is as described in :ref:`allowreplacement`.

    """

    #: List of decorators applied to every method of this class.
    decorators = [catch_processing_exceptions] + ModelView.decorators

    def __init__(self, session, model, preprocessors=None, postprocessors=None,
                 primary_key=None, validation_exceptions=None,
                 allow_to_many_replacement=None, *args, **kw):
        super(APIBase, self).__init__(session, model, *args, **kw)

        #: Whether to allow complete replacement of a to-many relationship when
        #: updating a resource.
        self.allow_to_many_replacement = allow_to_many_replacement

        #: The tuple of exceptions that are expected to be raised during
        #: validation when creating or updating a model.
        self.validation_exceptions = tuple(validation_exceptions or ())

        #: The name of the attribute containing the primary key to use as the
        #: ID of the resource.
        self.primary_key = primary_key

        upper = upper_keys

        #: The mapping from method name to a list of functions to apply after
        #: the main functionality of that method has been executed.
        self.postprocessors = defaultdict(list, upper(postprocessors or {}))

        #: The mapping from method name to a list of functions to apply before
        #: the main functionality of that method has been executed.
        self.preprocessors = defaultdict(list, upper(preprocessors or {}))

        # HACK: We would like to use the :attr:`API.decorators` class attribute
        # in order to decorate each view method with a decorator that catches
        # database integrity errors. However, in order to rollback the session,
        # we need to have a session object available to roll back. Therefore we
        # need to manually decorate each of the view functions here.
        decorate = lambda name, f: setattr(self, name, f(getattr(self, name)))
        for method in ['get', 'post', 'patch', 'delete']:
            # Check if the subclass has the method before trying to decorate
            # it.
            if hasattr(self, method):
                decorate(method, catch_integrity_errors(self.session))

    def _handle_validation_exception(self, exception):
        """Rolls back the session, extracts validation error messages, and
        returns an error response with :http:statuscode:`400` containing the
        extracted validation error messages.

        Again, *this method calls
        :meth:`sqlalchemy.orm.session.Session.rollback`*.

        """
        self.session.rollback()
        errors = extract_error_messages(exception)
        if not errors:
            return error_response(400, title='Validation error')
        if isinstance(errors, dict):
            errors = [error(title='Validation error',
                            detail='{0}: {1}'.format(field, detail))
                      for field, detail in errors.items()]
        return errors_response(400, errors)


class API(APIBase):
    """Provides method-based dispatching for :http:method:`get`,
    :http:method:`post`, :http:method:`patch`, and :http:method:`delete`
    requests, for both collections of resources and individual resources.

    `session` and `model` are as described in the constructor of the
    superclass. In addition to those described below, this constructor also
    accepts all the keyword arguments of the constructor of the superclass.

    `page_size` must be a positive integer that represents the default page
    size for responses that consist of a collection of resources. Requests made
    by clients may override this default by specifying ``page_size`` as a query
    parameter. `max_page_size` must be a positive integer that represents the
    maximum page size that a client can request. If a client specifies that
    greater than `max_page_size` should be returned, only `max_page_size`
    results will be returned. For more information, see
    :ref:`serverpagination`.

    `serializer` and `deserializer` are custom serialization functions. The
    former function must take a single argument representing the instance of
    the model to serialize, and must return a dictionary representation of that
    instance. The latter function must take a single argument representing the
    dictionary representation of an instance of the model and must return an
    instance of `model` that has those attributes. For more information, see
    :ref:`serialization`.

    `includes` ...

    `allow_client_generated_ids` ...

    """

    def __init__(self, session, model, page_size=10, max_page_size=100,
                 serializer=None, deserializer=None, includes=None,
                 allow_client_generated_ids=False, *args, **kw):
        super(API, self).__init__(session, model, *args, **kw)

        #: ...
        self.default_includes = includes
        if self.default_includes is not None:
            self.default_includes = frozenset(self.default_includes)

        #: ...
        self.collection_name = collection_name(self.model)

        #: ...
        self.page_size = page_size

        #: ...
        self.max_page_size = max_page_size

        #: ...
        self.allow_client_generated_ids = allow_client_generated_ids

        #: ...
        #:
        #: Use our default serializer if none is specified.
        self.serialize = serializer or DefaultSerializer()

        #: ...
        #:
        #: Use our default deserializer if none is specified.
        self.deserialize = deserializer or DefaultDeserializer()

    def _collection_parameters(self):
        """Gets filtering, sorting, grouping, and other settings from the
        request that affect the collection of resources in a response.

        TODO fill me in

        """
        # Determine filtering options.
        filters = json.loads(request.args.get('filter[objects]', '[]'))
        # # TODO fix this using the below
        # filters = [strings_to_dates(self.model, f) for f in filters]

        # # resolve date-strings as required by the model
        # for param in search_params.get('filters', list()):
        #     if 'name' in param and 'val' in param:
        #         query_model = self.model
        #         query_field = param['name']
        #         if '__' in param['name']:
        #             fieldname, relation = param['name'].split('__')
        #             submodel = getattr(self.model, fieldname)
        #             if isinstance(submodel, InstrumentedAttribute):
        #                 query_model = submodel.property.mapper.class_
        #                 query_field = relation
        #             elif isinstance(submodel, AssociationProxy):
        #                 # For the sake of brevity, rename this function.
        #                 get_assoc = get_related_association_proxy_model
        #                 query_model = get_assoc(submodel)
        #                 query_field = relation
        #         to_convert = {query_field: param['val']}
        #         try:
        #             result = strings_to_dates(query_model, to_convert)
        #         except ValueError as exception:
        #             current_app.logger.exception(str(exception))
        #             return dict(message='Unable to construct query'), 400
        #         param['val'] = result.get(query_field)

        # Determine sorting options.
        sort = request.args.get('sort')
        if sort:
            sort = [(value[0], value[1:]) for value in sort.split(',')]
        else:
            sort = []
        if any(order not in ('+', '-') for order, field in sort):
            raise SortKeyError('sort parameter must begin with "+" or "-"')

        # Determine grouping options.
        group_by = request.args.get('group')
        if group_by:
            group_by = group_by.split(',')
        else:
            group_by = []

        # Determine whether the client expects a single resource response.
        try:
            single = bool(int(request.args.get('filter[single]', 0)))
        except ValueError:
            raise SingleKeyError('failed to extract Boolean from parameter')

        return filters, sort, group_by, single

    def _get_related_resource(self, resource_id, relation_name,
                              related_resource_id):
        """Returns a response containing a resource related to a given
        resource.

        For example, a request like this::

            GET /people/1/articles/2

        will fetch the article with ID 2 that is related to the person with ID
        1 via the ``articles`` relationship. In general, this method is called
        on requests of the form::

            GET /<collection_name>/<resource_id>/<relation_name>/<related_resource_id>

        """
        for preprocessor in self.preprocessors['GET_RESOURCE']:
            temp_result = preprocessor(resource_id=resource_id,
                                       relation_name=relation_name,
                                       related_resource_id=related_resource_id)
            # Let the return value of the preprocessor be the new value of
            # instid, thereby allowing the preprocessor to effectively specify
            # which instance of the model to process on.
            #
            # We assume that if the preprocessor returns None, it really just
            # didn't return anything, which means we shouldn't overwrite the
            # instid.
            if temp_result is not None and isinstance(temp_result, tuple):
                if len(temp_result) == 1:
                    resource_id = temp_result
                elif len(temp_result) == 2:
                    resource_id, relation_name = temp_result
                else:
                    resource_id, relation_name, related_resource_id = \
                        temp_result
        # Get the resource with the specified ID.
        resource = get_by(self.session, self.model, resource_id,
                          self.primary_key)
        # Return an error if there is no resource with the specified ID.
        if resource is None:
            detail = 'No instance with ID {0}'.format(resource_id)
            return error_response(404, detail=detail)
        # Return an error if the relation is a to-one relation.
        if not is_like_list(resource, relation_name):
            detail = ('Cannot access a related resource by ID from a to-one'
                      ' relation')
            return error_response(404, detail=detail)
        # Get the model of the specified relation.
        related_model = get_related_model(self.model, relation_name)
        # Return an error if no such relation exists.
        if related_model is None:
            detail = 'No such relation: {0}'.format(related_model)
            return error_response(404, detail=detail)
        # Get the related resources.
        resources = getattr(resource, relation_name)
        # Check if one of the related resources has the specified ID. (JSON API
        # expects all IDs to be strings.)
        primary_keys = (primary_key_value(i) for i in resources)
        if not any(str(k) == related_resource_id for k in primary_keys):
            detail = 'No related resource with ID {0}'
            detail = detail.format(related_resource_id)
            return error_response(404, detail=detail)
        # Get the related resource by its ID.
        resource = get_by(self.session, related_model, related_resource_id)
        # Determine the fields to include for each type of resource.
        fields = parse_sparse_fields()
        type_ = collection_name(related_model)
        fields_for_primary = fields.get(type_)
        # Serialize the related resource.
        try:
            result = self.serialize(resource, only=fields_for_primary)
        except SerializationException as exception:
            # TODO refactor code for serialization error as its own function.
            current_app.logger.exception(str(exception))
            detail = 'Failed to serialize object of type {0}'.format(type_)
            return error_response(400, detail=detail)
        # Wrap the related resource in the `data` key.
        result = dict(data=result)
        # Determine the resources to include (in a compound document).
        to_include = self.resources_to_include(resource)
        # Include any requested resources in a compound document.
        included = []
        for included_resource in to_include:
            type_ = collection_name(get_model(included_resource))
            fields_for_this = fields.get(type_)
            try:
                serialized = self.serialize(included_resource,
                                            only=fields_for_this)
            except SerializationException as exception:
                current_app.logger.exception(str(exception))
                detail = 'Failed to serialize object of type {0}'.format(type_)
                return error_response(400, detail=detail)
            included.append(serialized)
        if included:
            result['included'] = included
        for postprocessor in self.postprocessors['GET_RESOURCE']:
            postprocessor(result=result)
        return result, 200

    # TODO need to apply filtering, sorting, etc. to fetching a to-many
    # relation...
    def _get_relation(self, resource_id, relation_name):
        """Returns a response containing a resource or a collection of
        resources related to a given resource.

        For example, a request for a to-many relationship like this::

            GET /people/1/articles

        will fetch the articles related to the person with ID 1 via the
        ``articles`` relationship. On a request to a to-one relationship::

            GET /articles/2/author

        a single resource will be returned.

        In general, this method is called on requests of the form::

            GET /<collection_name>/<resource_id>/<relation_name>

        """
        for preprocessor in self.preprocessors['GET_RESOURCE']:
            temp_result = preprocessor(resource_id=resource_id,
                                       relation_name=relation_name)
            # Let the return value of the preprocessor be the new value of
            # instid, thereby allowing the preprocessor to effectively specify
            # which instance of the model to process on.
            #
            # We assume that if the preprocessor returns None, it really just
            # didn't return anything, which means we shouldn't overwrite the
            # instid.
            if temp_result is not None and isinstance(temp_result, tuple):
                if len(temp_result) == 1:
                    resource_id = temp_result
                else:
                    resource_id, relation_name = temp_result
        # Get the resource with the specified ID.
        resource = get_by(self.session, self.model, resource_id,
                          self.primary_key)
        if resource is None:
            detail = 'No resource with ID {0}'.format(resource_id)
            return error_response(404, detail=detail)
        # Get the model of the specified relation.
        related_model = get_related_model(self.model, relation_name)
        if related_model is None:
            detail = 'No such relation: {0}'.format(related_model)
            return error_response(404, detail=detail)
        # Determine if this is a to-one or a to-many relation.
        is_to_many = is_like_list(resource, relation_name)
        # Get the resource or resources of the relation.
        if is_to_many:
            resources = getattr(resource, relation_name)
        else:
            resource = getattr(resource, relation_name)
        # Get the fields to include for each type of object.
        fields = parse_sparse_fields()
        type_ = collection_name(related_model)
        fields_for_related = fields.get(type_)
        # Serialize the related resource or collection of resources.
        try:
            if is_to_many:
                result = [self.serialize(inst, only=fields_for_related)
                          for inst in resources]
            else:
                result = self.serialize(resource, only=fields_for_related)
        except SerializationException as exception:
            current_app.logger.exception(str(exception))
            detail = 'Failed to serialize resource of type {0}'.format(type_)
            return error_response(400, detail=detail)
        # Wrap the related resource or collection of resources in the `data`
        # key.
        result = dict(data=result)
        # Determine the resources to include (in a compound document).
        if is_to_many:
            to_include = set(chain(self.resources_to_include(resource)
                                   for resource in resources))
        else:
            to_include = self.resources_to_include(resource)
        # Include any requested resources in a compound document.
        included = []
        for included_resource in to_include:
            type_ = collection_name(get_model(included_resource))
            fields_for_this = fields.get(type_)
            try:
                serialized = self.serialize(included_resource,
                                            only=fields_for_this)
            except SerializationException as exception:
                current_app.logger.exception(str(exception))
                detail = 'Failed to serialize resource of type {0}'
                detail = detail.format(type_)
                return error_response(400, detail=detail)
            included.append(serialized)
        if included:
            result['included'] = included
        for postprocessor in self.postprocessors['GET_RESOURCE']:
            postprocessor(result=result)
        return result, 200

    def _get_resource(self, resource_id):
        """Returns a response containing a single resource with the specified
        ID.

        For example, a request like::

            GET /people/1

        will fetch the person resource with ID 1.

        In general, this method is called on requests of the form::

            GET /<collection_name>/<resource_id>

        """
        for preprocessor in self.preprocessors['GET_RESOURCE']:
            temp_result = preprocessor(resource_id=resource_id)
            # Let the return value of the preprocessor be the new value of
            # instid, thereby allowing the preprocessor to effectively specify
            # which instance of the model to process on.
            #
            # We assume that if the preprocessor returns None, it really just
            # didn't return anything, which means we shouldn't overwrite the
            # instid.
            if temp_result is not None:
                resource_id = temp_result
        # Get the resource with the specified ID.
        resource = get_by(self.session, self.model, resource_id,
                          self.primary_key)
        if resource is None:
            detail = 'No resource with ID {0}'.format(resource_id)
            return error_response(404, detail=detail)
        # Determine the fields to include for each type of object.
        fields = parse_sparse_fields()
        type_ = self.collection_name
        fields_for_resource = fields.get(type_)
        # Serialize the resource.
        try:
            result = self.serialize(resource, only=fields_for_resource)
        except SerializationException as exception:
            current_app.logger.exception(str(exception))
            detail = 'Failed to serialize resource of type {0}'.format(type_)
            return error_response(400, detail=detail)
        # Wrap the resource in the `data` key.
        result = dict(data=result)
        # Determine resources to include.
        to_include = self.resources_to_include(resource)
        # Include any requested resources in a compound document.
        included = []
        for included_resource in to_include:
            type_ = collection_name(get_model(included_resource))
            fields_for_this = fields.get(type_)
            try:
                serialized = self.serialize(included_resource,
                                            only=fields_for_this)
            except SerializationException as exception:
                current_app.logger.exception(str(exception))
                detail = 'Failed to serialize resource of type {0}'
                detail = detail.format(type_)
                return error_response(400, detail=detail)
            included.append(serialized)
        if included:
            result['included'] = included
        for postprocessor in self.postprocessors['GET_RESOURCE']:
            postprocessor(result=result)
        return result, 200

    def _get_collection(self):
        """Returns a response containing a collection of resources of the type
        specified by the ``model`` argument to the constructor of this class.

        For example, a request like::

            GET /people

        will fetch a collection of people resources.

        In general, this method is called on requests of the form::

            GET /<collection_name>

        Filtering, sorting, grouping, and pagination are applied to the
        response in this method.

        """
        try:
            filters, sort, group_by, single = self._collection_parameters()
        except (TypeError, ValueError, OverflowError) as exception:
            current_app.logger.exception(str(exception))
            detail = 'Unable to decode filter objects as JSON list'
            return error_response(400, detail=detail)
        except SortKeyError as exception:
            current_app.logger.exception(str(exception))
            detail = 'Each sort parameter must begin with "+" or "-"'
            return error_response(400, detail=detail)
        except SingleKeyError as exception:
            current_app.logger.exception(str(exception))
            detail = 'Invalid format for filter[single] query parameter'
            return error_response(400, detail=detail)

        for preprocessor in self.preprocessors['GET_COLLECTION']:
            preprocessor(filters=filters, sort=sort, group_by=group_by,
                         single=single)

        # Compute the result of the search on the model.
        try:
            result = search(self.session, self.model, filters=filters,
                            sort=sort, group_by=group_by)
        except ComparisonToNull as exception:
            return error_response(400, detail=str(exception))
        except Exception as exception:
            current_app.logger.exception(str(exception))
            return error_response(400, detail='Unable to construct query')

        # Determine the client's request for which fields to include for this
        # type of object.
        fields = parse_sparse_fields(self.collection_name)

        # If the result of the search is a SQLAlchemy query object, we need to
        # return a collection.
        pagination_links = dict()
        if not single:
            # Determine the client's pagination request: page size and number.
            page_size = int(request.args.get('page[size]', self.page_size))
            if page_size < 0:
                detail = 'Page size must be a positive integer'
                return error_response(400, detail=detail)
            if page_size > self.max_page_size:
                detail = "Page size must not exceed the server's maximum: {0}"
                detail = detail.format(self.max_page_size)
                return error_response(400, detail=detail)
            # If the page size is 0, just return everything.
            if page_size == 0:
                num_results = count(self.session, result)
                headers = dict()
                result = [self.serialize(instance, only=fields)
                          for instance in result]
            # Otherwise, the page size is greater than zero, so paginate the
            # response.
            else:
                page_number = int(request.args.get('page[number]', 1))
                if page_number < 0:
                    detail = 'Page number must be a positive integer'
                    return error_response(400, detail=detail)
                # If the query is really a Flask-SQLAlchemy query, we can use
                # its built-in pagination.
                if hasattr(result, 'paginate'):
                    pagination = result.paginate(page_number, page_size,
                                                 error_out=False)
                    num_results = pagination.total
                    first = 1
                    last = pagination.pages
                    prev = pagination.prev_num
                    next_ = pagination.next_num
                    result = [self.serialize(instance, only=fields)
                              for instance in pagination.items]
                else:
                    num_results = count(self.session, result)
                    first = 1
                    # There will be no division-by-zero error here because we
                    # have already checked that page size is not equal to zero
                    # above.
                    last = int(math.ceil(num_results / page_size))
                    prev = page_number - 1 if page_number > 1 else None
                    next_ = page_number + 1 if page_number < last else None
                    offset = (page_number - 1) * page_size
                    result = result.limit(page_size).offset(offset)
                    result = [self.serialize(instance, only=fields)
                              for instance in result]
                # Create the pagination link URLs
                #
                # TODO pagination needs to respect sorting, fields, etc., so
                # these link template strings are not quite right.
                base_url = request.base_url
                link_urls = (LINKTEMPLATE.format(base_url, num, page_size)
                             if num is not None else None
                             for rel, num in (('first', first), ('last', last),
                                              ('prev', prev), ('next', next_)))
                first_url, last_url, prev_url, next_url = link_urls
                # Make them available for the result dictionary later.
                pagination_links = dict(first=first_url, last=last_url,
                                        prev=prev_url, next=next_url)
                link_strings = ('<{0}>; rel="{1}"'.format(url, rel)
                                if url is not None else None
                                for rel, url in (('first', first_url),
                                                 ('last', last_url),
                                                 ('prev', prev_url),
                                                 ('next', next_url)))
                # TODO Should this be multiple header fields, like this::
                #
                #     headers = [('Link', link) for link in link_strings
                #                if link is not None]
                #
                headers = dict(Link=','.join(link for link in link_strings
                                             if link is not None))
        # Otherwise, the result of the search should be a single resource.
        else:
            try:
                result = result.one()
            except NoResultFound:
                return error_response(404, detail='No result found')
            except MultipleResultsFound:
                return error_response(404, detail='Multiple results found')
            # (This is not a pretty solution.) Set number of results to
            # ``None`` to indicate that the returned JSON metadata should not
            # include a ``total`` key.
            num_results = None
            primary_key = self.primary_key or primary_key_name(result)
            result = self.serialize(result, only=fields)
            # The URL at which a client can access the instance matching this
            # search query.
            url = '{0}/{1}'.format(request.base_url, result[primary_key])
            headers = dict(Location=url)

        # Wrap the resulting object or list of objects under a `data` key.
        result = dict(data=result)

        # Provide top-level links.
        #
        # TODO use a defaultdict for result, then cast it to a dict at the end.
        if 'links' not in result:
            result['links'] = dict()
        result['links']['self'] = url_for(self.model)
        result['links'].update(pagination_links)

        for postprocessor in self.postprocessors['GET_COLLECTION']:
            postprocessor(result=result, filters=filters, sort=sort,
                          single=single)

        # HACK Provide the headers directly in the result dictionary, so that
        # the :func:`jsonpify` function has access to them. See the note there
        # for more information.
        result['meta'] = {_HEADERS: headers}
        result['meta']['total'] = 1 if num_results is None else num_results
        return result, 200, headers

    def resources_to_include(self, instance):
        """Returns a set of resources to include in a compound document
        response based on the ``include`` query parameter and the default
        includes specified in the constructor of this class.

        The ``include`` query parameter is as described in the `Inclusion of
        Related Resources`_ section of the JSON API specification. It specifies
        which resources, other than the primary resource or resources, will be
        included in a compound document response.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        # Add any links requested to be included by URL parameters.
        #
        # We expect `toinclude` to be a comma-separated list of relationship
        # paths.
        toinclude = request.args.get('include')
        if toinclude is None and self.default_includes is None:
            return {}
        elif toinclude is None and self.default_includes is not None:
            toinclude = self.default_includes
        else:
            toinclude = set(toinclude.split(','))

        # TODO create a resources_to_include_from_path() function, then
        # implement this as
        #
        #     return set(chain(resources_to_include_from_path(link)
        #                for link in toinclude))
        #
        result = set()
        for link in toinclude:
            if '.' in link:
                path = link.split('.')
            else:
                path = [link]
            instances = {instance}
            for relation in path:
                if is_like_list(instance, relation):
                    instances = set(chain(getattr(instance, relation)
                                          for instance in instances))
                else:
                    instances = set(getattr(instance, relation)
                                    for instance in instances)
            result |= set(instances)
        return result

    def get(self, resource_id, relation_name, related_resource_id):
        """Returns the JSON document representing a resource or a collection of
        resources.

        If ``resource_id`` is ``None`` (that is, if the request is of the form
        :http:get:`/people/`), this method returns a collection of resources.

        Otherwise, if ``relation_name`` is ``None`` (that is, if the request is
        of the form :http:get:`/people/1`), this method returns a resource with
        the specified ID.

        Otherwise, if ``related_resource_id`` is ``None`` (that is, if the
        request is of the form :http:get:`/people/1/articles` or
        :http:get:`/articles/1/author`), this method returns either a resource
        in the case of a to-one relationship or a collection of resources in
        the case of a to-many relationship.

        Otherwise, if none of the arguments are ``None`` (that is, if the
        request is of the form :http:get:`/people/1/articles/2`), this method
        returns the particular resource in the to-many relationship with the
        specified ID.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        if resource_id is None:
            return self._get_collection()
        if relation_name is None:
            return self._get_resource(resource_id)
        if related_resource_id is None:
            return self._get_relation(resource_id, relation_name)
        return self._get_related_resource(resource_id, relation_name,
                                          related_resource_id)

    def delete(self, resource_id):
        """Deletes the resource with the specified ID.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        for preprocessor in self.preprocessors['DELETE_RESOURCE']:
            temp_result = preprocessor(instance_id=resource_id)
            # See the note under the preprocessor in the get() method.
            if temp_result is not None:
                resource_id = temp_result
        was_deleted = False
        instance = get_by(self.session, self.model, resource_id, self.primary_key)
        if instance is None:
            detail = 'No resource found with ID {0}'.format(resource_id)
            return error_response(404, detail=detail)
        self.session.delete(instance)
        was_deleted = len(self.session.deleted) > 0
        self.session.commit()
        for postprocessor in self.postprocessors['DELETE_RESOURCE']:
            postprocessor(was_deleted=was_deleted)
        if not was_deleted:
            detail = 'There was no instance to delete.'
            return error_response(404, detail=detail)
        return {}, 204

    def post(self):
        """Creates a new resource based on request data.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        # try to read the parameters for the model from the body of the request
        try:
            data = json.loads(request.get_data()) or {}
        except (BadRequest, TypeError, ValueError, OverflowError) as exception:
            current_app.logger.exception(str(exception))
            return error_response(400, detail='Unable to decode data')
        # apply any preprocessors to the POST arguments
        for preprocessor in self.preprocessors['POST']:
            preprocessor(data=data)
        if 'data' not in data:
            detail = 'Resource must have a "data" key'
            return error_response(400, detail=detail)
        data = data['data']
        # Convert the dictionary representation into an instance of the
        # model.
        if 'type' not in data:
            detail = 'Must specify correct data type'
            return error_response(400, detail=detail)
        if 'id' in data and not self.allow_client_generated_ids:
            detail = 'Server does not allow client-generated IDS'
            return error_response(403, detail=detail)
        type_ = data.pop('type')
        if type_ != self.collection_name:
            message = ('Type must be {0}, not'
                       ' {1}').format(self.collection_name, type_)
            return error_response(409, detail=message)
        try:
            instance = self.deserialize(data)
            self.session.add(instance)
            self.session.commit()
        except DeserializationException as exception:
            current_app.logger.exception(str(exception))
            detail = 'Failed to deserialize object'
            return error_response(400, detail=detail)
        except self.validation_exceptions as exception:
            return self._handle_validation_exception(exception)
        # Get the dictionary representation of the new instance as it
        # appears in the database.
        try:
            result = self.serialize(instance)
        except SerializationException as exception:
            current_app.logger.exception(str(exception))
            detail = 'Failed to serialize object'
            return error_response(400, detail=detail)
        # Determine the value of the primary key for this instance and
        # encode URL-encode it (in case it is a Unicode string).
        primary_key = primary_key_value(instance, as_string=True)
        # The URL at which a client can access the newly created instance
        # of the model.
        url = '{0}/{1}'.format(request.base_url, primary_key)
        # Provide that URL in the Location header in the response.
        #
        # TODO should the many Location header fields be combined into a
        # single comma-separated header field::
        #
        #     headers = dict(Location=', '.join(urls))
        #
        headers = dict(Location=url)
        # Wrap the resulting object or list of objects under a 'data' key.
        result = dict(data=result)
        status = 201
        for postprocessor in self.postprocessors['POST']:
            postprocessor(result=result)
        return result, status, headers

    def _update_instance(self, instance, data):
        """Updates the attributes and relationships of the specified instance
        according to the elements in the `data` dictionary.

        `instance` must be an instance of the SQLAlchemy model class specified
        in the constructor of this class.

        `data` must be a dictionary representation of a resource object as
        described in the `Updating Resources`_ section of the JSON API
        specification.

        .. _Updating Resources: http://jsonapi.org/format/#crud-updating

        """
        # Update any relationships.
        links = data.pop('links', {})
        for linkname, link in links.items():
            # TODO: The client is obligated by JSON API to provide linkage if
            # the `links` attribute exists, but we should probably error out
            # in a more constructive way if it's missing.
            linkage = link['linkage']
            related_model = get_related_model(self.model, linkname)
            # If the client provided "null" for this relation, remove it by
            # setting the attribute to ``None``.
            if linkage is None:
                setattr(instance, linkname, None)
                continue
            # If this is a to-many relationship, get all the related
            # resources.
            if isinstance(linkage, list):
                # Replacement of a to-many relationship may have been disabled
                # by the user.
                if not self.allow_to_many_replacement:
                    message = 'Not allowed to replace a to-many relationship'
                    return error_response(403, detail=message)
                # If this is left empty, the relationship will be zeroed.
                newvalue = []
                not_found = []
                for rel in linkage:
                    expected_type = collection_name(related_model)
                    type_ = rel['type']
                    if type_ != expected_type:
                        detail = 'Type must be {0}, not {1}'
                        detail = detail.format(expected_type, type_)
                        return error_response(409, detail=detail)
                    id_ = rel['id']
                    inst = get_by(self.session, related_model, id_)
                    if inst is None:
                        not_found.append((id_, type_))
                    else:
                        newvalue.append(inst)
                # If any of the requested to-many linkage objects do not exist,
                # return an error response.
                if not_found:
                    detail = 'No object of type {0} found with ID {1}'
                    errors = [error(detail=detail.format(t, i))
                              for t, i in not_found]
                    return errors_response(404, errors)
            # Otherwise, it is a to-one relationship, so just get the single
            # related resource.
            else:
                expected_type = collection_name(related_model)
                type_ = linkage['type']
                if type_ != expected_type:
                    detail = 'Type must be {0}, not {1}'
                    detail = detail.format(expected_type, type_)
                    return error_response(409, detail=detail)
                id_ = linkage['id']
                inst = get_by(self.session, related_model, id_)
                # If the to-one relationship resource does not exist, return an
                # error response.
                if inst is None:
                    detail = 'No object of type {0} found with ID {1}'
                    detail = detail.format(type_, id_)
                    return error_response(404, detail=detail)
                newvalue = inst
            # Set the new value of the relationship.
            try:
                # TODO Here if there are any extra attributes in
                # newvalue[inst], (1) get the secondary association object for
                # that relation, then (2) set the extra attributes on that
                # object.
                setattr(instance, linkname, newvalue)
            except self.validation_exceptions as exception:
                current_app.logger.exception(str(exception))
                return self._handle_validation_exception(exception)

        # Check for any request parameter naming a column which does not exist
        # on the current model.
        for field in data:
            if not has_field(self.model, field):
                detail = "Model does not have field '{0}'".format(field)
                return error_response(400, detail=detail)
        # Special case: if there are any dates, convert the string form of the
        # date into an instance of the Python ``datetime`` object.
        data = strings_to_datetimes(self.model, data)
        # Try to update all instances present in the query.
        num_modified = 0
        try:
            if data:
                for field, value in data.items():
                    setattr(instance, field, value)
                num_modified += 1
            self.session.commit()
        except self.validation_exceptions as exception:
            current_app.logger.exception(str(exception))
            return self._handle_validation_exception(exception)

    def patch(self, resource_id):
        """Updates the resource with the specified ID according to the request
        data.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        # try to load the fields/values to update from the body of the request
        try:
            data = json.loads(request.get_data()) or {}
        except (BadRequest, TypeError, ValueError, OverflowError) as exception:
            # this also happens when request.data is empty
            current_app.logger.exception(str(exception))
            return error_response(400, detail='Unable to decode data')
        for preprocessor in self.preprocessors['PATCH_RESOURCE']:
            temp_result = preprocessor(instance_id=resource_id, data=data)
            # See the note under the preprocessor in the get() method.
            if temp_result is not None:
                resource_id = temp_result
        # Get the instance on which to set the new attributes.
        instance = get_by(self.session, self.model, resource_id, self.primary_key)
        # If no instance of the model exists with the specified instance ID,
        # return a 404 response.
        if instance is None:
            detail = 'No instance with ID {0} in model {1}'.format(resource_id,
                                                                   self.model)
            return error_response(404, detail=detail)
        # Unwrap the data from the collection name key.
        data = data.pop('data', {})
        if 'type' not in data:
            message = 'Must specify correct data type'
            return error_response(400, detail=message)
        if 'id' not in data:
            message = 'Must specify resource ID'
            return error_response(400, detail=message)
        type_ = data.pop('type')
        id_ = data.pop('id')
        if type_ != self.collection_name:
            message = ('Type must be {0}, not'
                       ' {1}').format(self.collection_name, type_)
            return error_response(409, detail=message)
        if id_ != resource_id:
            message = 'ID must be {0}, not {1}'.format(resource_id, id_)
            return error_response(409, detail=message)
        result = self._update_instance(instance, data)
        # If result is not None, that means there was an error updating the
        # resource.
        if result is not None:
            return result
        # If we believe that the resource changes in ways other than the
        # updates specified by the request, we must return 200 OK and a
        # representation of the modified resource.
        #
        # TODO This should be checked just once, at instantiation time.
        if changes_on_update(self.model):
            result = dict(data=self.serialize(instance))
            status = 200
        else:
            result = dict()
            status = 204
        # Perform any necessary postprocessing.
        for postprocessor in self.postprocessors['PATCH_RESOURCE']:
            postprocessor(result=result)
        return result, status


class RelationshipAPI(APIBase):
    """Provides fetching, updating, and deleting from relationship URLs.

    The endpoints provided by this class are of the form
    ``/people/1/links/articles``, and the requests and responses include **link
    objects**, as opposed to **resource objects**.

    `session` and `model` are as described in the constructor of the
    superclass. In addition to those described below, this constructor also
    accepts all the keyword arguments of the constructor of the superclass.

    `allow_delete_from_to_many_relationships` ...

    """

    def __init__(self, session, model,
                 allow_delete_from_to_many_relationships=False, *args, **kw):
        super(RelationshipAPI, self).__init__(session, model, *args, **kw)
        self.allow_delete_from_to_many_relationships = \
            allow_delete_from_to_many_relationships

    def get(self, resource_id, relation_name):
        """Fetches a to-one or to-many relationship from a resource.

        If the specified relationship is a to-one relationship, this method
        returns a link object. If it is a to-many relationship, it returns a
        collection of link objects.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        for preprocessor in self.preprocessors['GET_RELATIONSHIP']:
            temp_result = preprocessor(instance_id=resource_id,
                                       relationship=relation_name)
            # Let the return value of the preprocessor be the new value of
            # instid, thereby allowing the preprocessor to effectively specify
            # which instance of the model to process on.
            #
            # We assume that if the preprocessor returns None, it really just
            # didn't return anything, which means we shouldn't overwrite the
            # instid.
            if temp_result is not None:
                resource_id = temp_result
        # get the instance of the "main" model whose ID is instid
        instance = get_by(self.session, self.model, resource_id, self.primary_key)
        if instance is None:
            detail = 'No instance with ID {0}'.format(resource_id)
            return error_response(404, detail=detail)
        related_value = getattr(instance, relation_name)
        related_model = get_related_model(self.model, relation_name)
        related_type = collection_name(related_model)
        # For the sake of brevity, rename this function.
        pk = primary_key_value
        # If this is a to-many relationship...
        if is_like_list(instance, relation_name):
            # Convert IDs to strings, as required by JSON API.
            #
            # TODO This could be paginated.
            result = [dict(id=str(pk(inst)), type=related_type)
                      for inst in related_value]
        # If this is a to-one relationship...
        else:
            if related_value is None:
                result = None
            else:
                # Convert ID to string, as required by JSON API.
                result = dict(id=str(pk(related_value)), type=related_type)
        # Wrap the result
        result = dict(data=result)
        for postprocessor in self.postprocessors['GET_RELATIONSHIP']:
            postprocessor(result=result)
        return result, 200

    def post(self, resource_id, relation_name):
        """Adds resources to a to-many relationship.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        # try to load the fields/values to update from the body of the request
        try:
            data = json.loads(request.get_data()) or {}
        except (BadRequest, TypeError, ValueError, OverflowError) as exception:
            # this also happens when request.data is empty
            current_app.logger.exception(str(exception))
            return error_response(400, detail='Unable to decode data')
        for preprocessor in self.preprocessors['POST_RELATIONSHIP']:
            temp_result = preprocessor(instance_id=resource_id,
                                       relation_name=relation_name, data=data)
            # See the note under the preprocessor in the get() method.
            if temp_result is not None:
                resource_id, relation_name = temp_result
        instance = get_by(self.session, self.model, resource_id, self.primary_key)
        # If no instance of the model exists with the specified instance ID,
        # return a 404 response.
        if instance is None:
            detail = 'No instance with ID {0} in model {1}'.format(resource_id,
                                                                   self.model)
            return error_response(404, detail=detail)
        # If no such relation exists, return a 404.
        if not hasattr(instance, relation_name):
            detail = 'Model {0} has no relation named {1}'.format(self.model,
                                                                  relation_name)
            return error_response(404, detail=detail)
        related_model = get_related_model(self.model, relation_name)
        related_value = getattr(instance, relation_name)
        # Unwrap the data from the request.
        data = data.pop('data', {})
        for rel in data:
            if 'type' not in rel:
                detail = 'Must specify correct data type'
                return error_response(400, detail=detail)
            if 'id' not in rel:
                detail = 'Must specify resource ID'
                return error_response(400, detail=detail)
            type_ = rel['type']
            # The type name must match the collection name of model of the
            # relation.
            if type_ != collection_name(related_model):
                detail = ('Type must be {0}, not'
                          ' {1}').format(collection_name(related_model), type_)
                return error_response(409, detail=detail)
            # Get the new objects to add to the relation.
            new_value = get_by(self.session, related_model, rel['id'])
            if new_value is None:
                detail = ('No object of type {0} found with ID'
                          ' {1}').format(type_, rel['id'])
                return error_response(404, detail=detail)
            # Don't append a new value if it already exists in the to-many
            # relationship.
            if new_value not in related_value:
                try:
                    related_value.append(new_value)
                except self.validation_exceptions as exception:
                    current_app.logger.exception(str(exception))
                    return self._handle_validation_exception(exception)
        # TODO do we need to commit the session here?
        #
        #     self.session.commit()
        #
        # Perform any necessary postprocessing.
        for postprocessor in self.postprocessors['POST_RELATIONSHIP']:
            postprocessor()
        return {}, 204

    def patch(self, resource_id, relation_name):
        """Updates to a to-one or to-many relationship.

        If the relationship is a to-many relationship and this class was
        instantiated with the ``allow_to_many_replacement`` keyword argument
        set to ``False``, then this method returns a :http:status:`403`
        response.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        # try to load the fields/values to update from the body of the request
        try:
            data = json.loads(request.get_data()) or {}
        except (BadRequest, TypeError, ValueError, OverflowError) as exception:
            # this also happens when request.data is empty
            current_app.logger.exception(str(exception))
            return error_response(400, detail='Unable to decode data')
        for preprocessor in self.preprocessors['PATCH_RELATIONSHIP']:
            temp_result = preprocessor(instance_id=resource_id,
                                       relation_name=relation_name, data=data)
            # See the note under the preprocessor in the get() method.
            if temp_result is not None:
                resource_id, relation_name = temp_result
        instance = get_by(self.session, self.model, resource_id, self.primary_key)
        # If no instance of the model exists with the specified instance ID,
        # return a 404 response.
        if instance is None:
            detail = 'No instance with ID {0} in model {1}'.format(resource_id,
                                                                   self.model)
            return error_response(404, detail=detail)
        # If no such relation exists, return a 404.
        if not hasattr(instance, relation_name):
            detail = 'Model {0} has no relation named {1}'.format(self.model,
                                                                  relation_name)
            return error_response(404, detail=detail)
        related_model = get_related_model(self.model, relation_name)
        # related_value = getattr(instance, relation_name)

        # Unwrap the data from the request.
        data = data.pop('data', {})
        # If the client sent a null value, we assume it wants to remove a
        # to-one relationship.
        if data is None:
            # TODO check that the relationship is a to-one relationship.
            setattr(instance, relation_name, None)
        else:
            # If this is a list, we assume the client is trying to set a
            # to-many relationship.
            if isinstance(data, list):
                # Replacement of a to-many relationship may have been disabled
                # on the server-side by the user.
                if not self.allow_to_many_replacement:
                    detail = 'Not allowed to replace a to-many relationship'
                    return error_response(403, detail=detail)
                replacement = []
                for rel in data:
                    if 'type' not in rel:
                        detail = 'Must specify correct data type'
                        return error_response(400, detail=detail)
                    if 'id' not in rel:
                        detail = 'Must specify resource ID or IDs'
                        return error_response(400, detail=detail)
                    type_ = rel['type']
                    # The type name must match the collection name of model of
                    # the relation.
                    if type_ != collection_name(related_model):
                        detail = 'Type must be {0}, not {1}'
                        detail = detail.format(collection_name(related_model),
                                               type_)
                        return error_response(409, detail=detail)
                    id_ = rel['id']
                    obj = get_by(self.session, related_model, id_)
                    replacement.append(obj)
            # Otherwise, we assume the client is trying to set a to-one
            # relationship.
            else:
                if 'type' not in data:
                    detail = 'Must specify correct data type'
                    return error_response(400, detail=detail)
                if 'id' not in data:
                    detail = 'Must specify resource ID or IDs'
                    return error_response(400, detail=detail)
                type_ = data['type']
                # The type name must match the collection name of model of the
                # relation.
                if type_ != collection_name(related_model):
                    detail = ('Type must be {0}, not'
                              ' {1}').format(collection_name(related_model),
                                             type_)
                    return error_response(409, detail=detail)
                id_ = data['id']
                replacement = get_by(self.session, related_model, id_)
            # If the to-one relationship resource or any of the to-many
            # relationship resources do not exist, return an error response.
            if replacement is None:
                detail = ('No object of type {0} found'
                          ' with ID {1}').format(type_, id_)
                return error_response(404, detail=detail)
            if (isinstance(replacement, list)
                and any(value is None for value in replacement)):
                not_found = (rel for rel, value in zip(data, replacement)
                             if value is None)
                detail = 'No object of type {0} found with ID {1}'
                errors = [error(detail=detail.format(rel['type'], rel['id']))
                          for rel in not_found]
                return errors_response(404, errors)
            # Finally, set the relationship to have the new value.
            try:
                setattr(instance, relation_name, replacement)
            except self.validation_exceptions as exception:
                current_app.logger.exception(str(exception))
                return self._handle_validation_exception(exception)
        # TODO do we need to commit the session here?
        #
        #     self.session.commit()
        #
        # Perform any necessary postprocessing.
        for postprocessor in self.postprocessors['PATCH_RELATIONSHIP']:
            postprocessor()
        return {}, 204

    def delete(self, resource_id, relation_name):
        """Deletes resources from a to-many relationship.

        If this class was instantiated with the
        ``allow_delete_from_to_many_relationships`` keyword argument set to
        ``False``, then this method returns a :http:status:`403` response.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        if not self.allow_delete_from_to_many_relationships:
            detail = 'Not allowed to delete from a to-many relationship'
            return error_response(403, detail=detail)
        # try to load the fields/values to update from the body of the request
        try:
            data = json.loads(request.get_data()) or {}
        except (BadRequest, TypeError, ValueError, OverflowError) as exception:
            # this also happens when request.data is empty
            current_app.logger.exception(str(exception))
            return error_response(400, detail='Unable to decode data')
        was_deleted = False
        for preprocessor in self.preprocessors['DELETE_RELATIONSHIP']:
            temp_result = preprocessor(instance_id=resource_id,
                                       relation_name=relation_name)
            # See the note under the preprocessor in the get() method.
            if temp_result is not None:
                resource_id = temp_result
        instance = get_by(self.session, self.model, resource_id, self.primary_key)
        # If no such relation exists, return an error to the client.
        if not hasattr(instance, relation_name):
            detail = 'No such link: {0}'.format(relation_name)
            return error_response(404, detail=detail)
        # We assume that the relation is a to-many relation.
        related_model = get_related_model(self.model, relation_name)
        related_type = collection_name(related_model)
        relation = getattr(instance, relation_name)
        data = data.pop('data')
        not_found = []
        to_remove = []
        for rel in data:
            if 'type' not in rel:
                detail = 'Must specify correct data type'
                return error_response(400, detail=detail)
            if 'id' not in rel:
                detail = 'Must specify resource ID'
                return error_response(400, detail=detail)
            type_ = rel['type']
            id_ = rel['id']
            if type_ != related_type:
                detail = ('Conflicting type: expected {0} but got type {1} for'
                          ' linkage object with ID {2}')
                detail = detail.format(related_type, type_, id_)
                return error_response(409, detail=detail)
            resource = get_by(self.session, related_model, id_)
            if resource is None:
                not_found.append((type_, id_))
            else:
                to_remove.append(resource)
        if not_found:
            detail = 'No resource of type {0} and ID {1} found'
            errors = [error(detail=detail.format(t, i)) for t, i in not_found]
            return errors_response(404, errors)
        # Remove each of the resources from the relation (if they are not
        # already absent).
        for resource in to_remove:
            try:
                relation.remove(resource)
            except ValueError:
                # The JSON API specification requires that we silently
                # ignore requests to delete resources that are already
                # missing from a to-many relation.
                pass
        was_deleted = len(self.session.dirty) > 0
        self.session.commit()
        for postprocessor in self.postprocessors['DELETE_RELATIONSHIP']:
            postprocessor(was_deleted=was_deleted)
        if not was_deleted:
            detail = 'There was no instance to delete'
            return error_response(404, detail=detail)
        return {}, 204
