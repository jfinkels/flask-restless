# base.py - base classes for views of SQLAlchemy objects
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
"""Base classes for fetching, creating, updating, and deleting
SQLAlchemy resources and relationships.

The main class in this module, :class:`APIBase`, is a
:class:`~flask.MethodView` subclass that is also an abstract base class
for JSON API requests on a SQLAlchemy backend.

"""
from __future__ import division

from collections import defaultdict
from functools import partial
from functools import wraps
from itertools import chain
import math
import re
# In Python 3...
try:
    from urllib.parse import urlparse
    from urllib.parse import urlunparse
# In Python 2...
except ImportError:
    from urlparse import urlparse
    from urlparse import urlunparse

from flask import current_app
from flask import json
from flask import jsonify
from flask import request
from flask.views import MethodView
from mimerender import FlaskMimeRender
from mimerender import register_mime
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import MultipleResultsFound
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.query import Query
from werkzeug import parse_options_header
from werkzeug.exceptions import HTTPException

from ..helpers import collection_name
from ..helpers import get_model
from ..helpers import get_related_model
from ..helpers import is_like_list
from ..helpers import is_relationship
from ..helpers import primary_key_for
from ..helpers import primary_key_value
from ..helpers import serializer_for
from ..helpers import url_for
from ..search import FilterCreationError
from ..search import FilterParsingError
from ..search import search
from ..search import search_relationship
from ..serialization import DeserializationException
from ..serialization import JsonApiDocument
from ..serialization import MultipleExceptions
from ..serialization import simple_serialize_many
from ..serialization import simple_relationship_serialize
from ..serialization import simple_relationship_serialize_many
from ..serialization import SerializationException
from .helpers import count
from .helpers import upper_keys as upper

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

#: The highest version of the JSON API specification supported by
#: Flask-Restless.
JSONAPI_VERSION = '1.0'

#: Strings that indicate a database conflict when appearing in an error
#: message of an exception raised by SQLAlchemy.
#:
#: The particular error message depends on the particular environment
#: containing the SQLite backend, it seems.
CONFLICT_INDICATORS = ('conflicts with', 'UNIQUE constraint failed',
                       'is not unique')

#: The names of pagination links that appear in both ``Link`` headers
#: and JSON API links.
LINK_NAMES = ('first', 'last', 'prev', 'next')

#: The query parameter key that identifies filter objects in a
#: :http:method:`get` request.
FILTER_PARAM = 'filter[objects]'

#: The query parameter key that indicates whether to expect a single
#: resource in the response.
SINGLE_PARAM = 'filter[single]'

#: The query parameter key that identifies sort fields in a :http:method:`get`
#: request.
SORT_PARAM = 'sort'

#: The query parameter key that identifies grouping fields in a
#: :http:method:`get` request.
GROUP_PARAM = 'group'

#: The query parameter key that identifies the page number in a
#: :http:method:`get` request.
PAGE_NUMBER_PARAM = 'page[number]'

#: The query parameter key that identifies the page size in a
#: :http:method:`get` request.
PAGE_SIZE_PARAM = 'page[size]'

#: A regular expression for Accept headers.
#:
#: For an explanation of "media-range", etc., see Sections 5.3.{1,2} of
#: RFC 7231.
ACCEPT_RE = re.compile(
    r'''(                       # media-range capturing-parenthesis
          [^\s;,]+              # type/subtype
          (?:[ \t]*;[ \t]*      # ";"
            (?:                 # parameter non-capturing-parenthesis
              [^\s;,q][^\s;,]*  # token that doesn't start with "q"
            |                   # or
              q[^\s;,=][^\s;,]* # token that is more than just "q"
            )
          )*                    # zero or more parameters
        )                       # end of media-range
        (?:[ \t]*;[ \t]*q=      # weight is a "q" parameter
          (\d*(?:\.\d+)?)       # qvalue capturing-parentheses
          [^,]*                 # "extension" accept params: who cares?
        )?                      # accept params are optional
    ''', re.VERBOSE)

#: Keys in a JSON API error object.
ERROR_FIELDS = ('id_', 'links', 'status', 'code_', 'title', 'detail', 'source',
                'meta')

# For the sake of brevity, rename this function.
chain = chain.from_iterable

# Register the JSON API content type so that mimerender knows to look for it.
register_mime('jsonapi', (CONTENT_TYPE, ))


class SingleKeyError(KeyError):
    """Raised when attempting to parse the "single" query parameter reveals
    that the client did not correctly provide a Boolean value.

    """
    pass


class PaginationError(Exception):
    """Raised when pagination fails, due to, for example, a bad
    pagination parameter supplied by the client.

    """
    pass


class ProcessingException(HTTPException):
    """Raised when a preprocessor or postprocessor encounters a problem.

    This exception should be raised by functions supplied in the
    ``preprocessors`` and ``postprocessors`` keyword arguments to
    :class:`APIManager.create_api`. When this exception is raised, all
    preprocessing or postprocessing halts, so any processors appearing
    later in the list will not be invoked.

    The keyword arguments ``id_``, ``href`` ``status``, ``code``,
    ``title``, ``detail``, ``links``, ``paths`` correspond to the
    elements of the JSON API error object; the values of these keyword
    arguments will appear in the error object returned to the client.

    Any additional positional or keyword arguments are supplied directly
    to the superclass, :exc:`werkzeug.exceptions.HTTPException`.

    """

    def __init__(self, id_=None, links=None, status=400, code=None, title=None,
                 detail=None, source=None, meta=None, *args, **kw):
        super(ProcessingException, self).__init__(*args, **kw)
        self.id_ = id_
        self.links = links
        self.status = status
        # This attribute would otherwise override the class-level
        # attribute `code` in the superclass, HTTPException.
        self.code_ = code
        self.code = status
        self.title = title
        self.detail = detail
        self.source = source
        self.meta = meta


def _is_msie8or9():
    """Returns ``True`` if and only if the user agent of the client making the
    request indicates that it is Microsoft Internet Explorer 8 or 9.

    .. note::

       We have no way of knowing if the user agent is lying, so we just make
       our best guess based on the information provided.

    """
    # request.user_agent.version comes as a string, so we have to parse it
    version = lambda ua: tuple(int(d) for d in ua.version.split('.'))
    return (request.user_agent is not None and
            request.user_agent.version is not None and
            request.user_agent.browser == 'msie' and
            (8, 0) <= version(request.user_agent) < (10, 0))


def un_camel_case(s):
    """Inserts spaces before the capital letters in a camel case string.

    """
    # This regular expression appears on StackOverflow
    # <http://stackoverflow.com/a/199120/108197>, and is distributed
    # under the Creative Commons Attribution-ShareAlike 3.0 Unported
    # license.
    return re.sub(r'(?<=\w)([A-Z])', r' \1', s)


def catch_processing_exceptions(func):
    """Decorator that catches :exc:`ProcessingException`s and subsequently
    returns a JSON-ified error response.

    """
    @wraps(func)
    def new_func(*args, **kw):
        """Executes ``func(*args, **kw)`` but catches
        :exc:`ProcessingException`s.

        """
        try:
            return func(*args, **kw)
        except ProcessingException as exception:
            # TODO In Python 2.7 and later, this should be a dict comprehension
            kw = dict((key, getattr(exception, key)) for key in ERROR_FIELDS)
            # Need to change the name of the `code` key as a workaround
            # for name collisions with Werkzeug exception classes.
            kw['code'] = kw.pop('code_')
            return error_response(cause=exception, **kw)
    return new_func


# This code is (lightly) adapted from the ``werkzeug`` library, in the
# ``werkzeug.http`` module. See <http://werkzeug.pocoo.org> for more
# information.
def parse_accept_header(value):
    """Parses an HTTP Accept-* header.

    This does not implement a complete valid algorithm but one that
    supports at least value and quality extraction.

    `value` is the :http:header:`Accept` header string (everything after
    the ``Accept:``) to be parsed.

    Returns an iterator over ``(value, extra)`` tuples. If there were no
    media type parameters, then ``extra`` is simply ``None``.

    """
    def match_to_pair(match):
        """Returns the pair ``(name, quality)`` from the given match
        object for the Accept header regular expression.

        ``name`` is the name of the content type that is accepted, and
        ``quality`` is the integer given by the header's media type
        parameter, or ``None`` if it has no such media type paramer.

        """
        name = match.group(1)
        extra = match.group(2)
        # This is the main difference between our implementation and
        # Werkzeug's implementation: all we want to know is whether
        # there is any media type parameters or not, so we mark the
        # quality is ``None`` instead of ``1`` here.
        quality = max(min(float(extra), 1), 0) if extra else None
        return name, quality
    return map(match_to_pair, ACCEPT_RE.finditer(value))


def requires_json_api_accept(func):
    """Decorator that requires :http:header:`Accept` headers with the
    JSON API media type to have no media type parameters.

    This does *not* require that all requests have an
    :http:header:`Accept` header, just that those requests with an
    :http:header:`Accept` header for the JSON API media type have no
    media type parameters. However, if there are only
    :http:header:`Accept` headers that specify non-JSON API media types,
    this will cause a :http:status`406` response.

    If a request does not have the correct ``Accept`` header, a
    :http:status:`406` response is returned. An incorrect header is
    described in the `Server Responsibilities`_ section of the JSON API
    specification:

        Servers MUST respond with a 406 Not Acceptable status code if a
        request's Accept header contains the JSON API media type and all
        instances of that media type are modified with media type
        parameters.

    View methods can be wrapped like this::

        @requires_json_api_accept
        def get(self, *args, **kw):
            return '...'

    .. _Server Responsibilities: http://jsonapi.org/format/#content-negotiation-servers

    """
    @wraps(func)
    def new_func(*args, **kw):
        """Executes ``func(*args, **kw)`` only after checking for the
        correct JSON API :http:header:`Accept` header.

        """
        header = request.headers.get('Accept')
        # If there is no Accept header, we don't need to do anything.
        if header is None:
            return func(*args, **kw)
        header_pairs = list(parse_accept_header(header))
        # If the Accept header is empty, then do nothing.
        #
        # An empty Accept header is technically allowed by RFC 2616,
        # Section 14.1 (for more information, see
        # http://stackoverflow.com/a/12131993/108197). Since an empty
        # Accept header doesn't violate JSON APIs rule against having
        # only JSON API mimetypes with media type parameters, we simply
        # proceed as normal with the request.
        if len(header_pairs) == 0:
            return func(*args, **kw)
        jsonapi_pairs = [(name, extra) for name, extra in header_pairs
                         if name.startswith(CONTENT_TYPE)]
        # If there are Accept headers but none of them specifies the
        # JSON API media type, respond with `406 Not Acceptable`.
        if len(jsonapi_pairs) == 0:
            detail = ('Accept header, if specified, must be the JSON API media'
                      ' type: application/vnd.api+json')
            return error_response(406, detail=detail)
        # If there are JSON API Accept headers, but they all have media
        # type parameters, respond with `406 Not Acceptable`.
        if all(extra is not None for name, extra in jsonapi_pairs):
            detail = ('Accept header contained JSON API content type, but each'
                      ' instance occurred with media type parameters; at least'
                      ' one instance must appear without parameters (the part'
                      ' after the semicolon)')
            return error_response(406, detail=detail)
        # At this point, everything is fine, so just execute the method as-is.
        return func(*args, **kw)
    return new_func


def requires_json_api_mimetype(func):
    """Decorator that requires requests *that include data* have the
    :http:header:`Content-Type` header required by the JSON API
    specification.

    If the request does not have the correct :http:header:`Content-Type`
    header, a :http:status:`415` response is returned.

    View methods can be wrapped like this::

        @requires_json_api_mimetype
        def get(self, *args, **kw):
            return '...'

    """
    @wraps(func)
    def new_func(*args, **kw):
        """Executes ``func(*args, **kw)`` only after checking for the
        correct JSON API :http:header:`Content-Type` header.

        """
        # GET and DELETE requests don't have request data in JSON API,
        # so we can ignore those and only continue if this is a PATCH or
        # POST request.
        #
        # Ideally we would be able to decorate each individual request
        # methods directly, but it is not possible with the current
        # design of Flask's method-based views.
        if request.method not in ('PATCH', 'POST'):
            return func(*args, **kw)
        header = request.headers.get('Content-Type')
        content_type, extra = parse_options_header(header)
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
        # JSON API requires that the content type header does not have
        # any media type parameters.
        if extra:
            detail = ('Content-Type header must not have any media type'
                      ' parameters but found {0}'.format(extra))
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
    def decorated(func):
        """Returns a decorated version of ``func``, as described in the
        wrapper defined within.

        """
        @wraps(func)
        def wrapped(*args, **kw):
            """Executes ``func(*args, **kw)`` but catches any exception
            that warrants a database rollback.

            """
            try:
                return func(*args, **kw)
            # This should include: DataError, IntegrityError,
            # ProgrammingError, FlushError, OperationalError,
            # InalidRequestError, and any other SQLAlchemyError
            # subclass.
            except SQLAlchemyError as exception:
                session.rollback()
                # Special status code for conflicting instances: 409 Conflict
                status = 409 if is_conflict(exception) else 400
                detail = str(exception)
                title = un_camel_case(exception.__class__.__name__)
                return error_response(status, cause=exception, detail=detail,
                                      title=title)
        return wrapped
    return decorated


def is_conflict(exception):
    """Returns ``True`` if and only if the specified exception represents a
    conflict in the database.

    """
    exception_string = str(exception)
    return any(s in exception_string for s in CONFLICT_INDICATORS)


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
    headers = kw['meta'].pop(_HEADERS, {}) if 'meta' in kw else {}
    status_code = kw['meta'].pop(_STATUS, 200) if 'meta' in kw else 200
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
    # TODO In Python 2.7 and later, this should be a dictionary comprehension.
    fields = dict((key[7:-1], set(value.split(',')))
                  for key, value in request.args.items()
                  if key.startswith('fields[') and key.endswith(']'))
    return fields.get(type_) if type_ is not None else fields


def resources_from_path(instance, path):
    """Returns an iterable of all resources along the given relationship
    path for the specified instance of the model.

    For example, if our model includes three classes, ``Article``,
    ``Person``, and ``Comment``::

        >>> article = Article(id=1)
        >>> comment1 = Comment(id=1)
        >>> comment2 = Comment(id=2)
        >>> person1 = Person(id=1)
        >>> person2 = Person(id=2)
        >>> article.comments = [comment1, comment2]
        >>> comment1.author = person1
        >>> comment2.author = person2
        >>> instances = [article, comment1, comment2, person1, person2]
        >>> session.add_all(instances)
        >>>
        >>> l = list(api.resources_from_path(article, 'comments.author'))
        >>> len(l)
        4
        >>> [r.id for r in l if isinstance(r, Person)]
        [1, 2]
        >>> [r.id for r in l if isinstance(r, Comment)]
        [1, 2]

    """
    # First, split the path to determine the sequence of relationships
    # to follow.
    if '.' in path:
        path = path.split('.')
    else:
        path = [path]
    # Next, do a breadth-first traversal of the resources related to
    # `instance` via the given path.
    seen = set()
    # TODO In Pyhon 2.7 and later, this should be a set literal.
    nextlevel = set([instance])
    first_time = True
    while nextlevel:
        thislevel = nextlevel
        nextlevel = set()
        # Follow the relation given in the path to get the "neighbor"
        # resources of any resource in the curret level of the
        # breadth-first traversal.
        if path:
            relation = path.pop(0)
        else:
            relation = None
        for resource in thislevel:
            if resource in seen:
                continue
            # Since this method is going to be used to populate the
            # `included` section of a compound document, we don't want
            # to yield the instance from which related resources are
            # being included.
            if first_time:
                first_time = False
            else:
                yield resource
            seen.add(resource)
            # If there are still parts of the relationship path to
            # traverse, queue up the related resources at the next
            # level.
            if relation is not None:
                if is_like_list(resource, relation):
                    update = nextlevel.update
                else:
                    update = nextlevel.add
                update(getattr(resource, relation))


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


def error(id_=None, links=None, status=None, code=None, title=None,
          detail=None, source=None, meta=None):
    """Returns a dictionary representation of an error as described in the
    JSON API specification.

    Note: the ``id_`` keyword argument corresponds to the ``id`` element
    of the JSON API error object.

    For more information, see the `Errors`_ section of the JSON API
    specification.

    .. Errors_: http://jsonapi.org/format/#errors

    """
    # HACK We use locals() so we don't have to list every keyword argument.
    if all(kwvalue is None for kwvalue in locals().values()):
        raise ValueError('At least one of the arguments must not be None.')
    return {'id': id_, 'links': links, 'status': status, 'code': code,
            'title': title, 'detail': detail, 'source': source, 'meta': meta}


def error_response(status=400, cause=None, **kw):
    """Returns a correctly formatted error response with the specified
    parameters.

    This is a convenience function for::

        errors_response(status, [error(**kw)])

    For more information, see :func:`errors_response`.

    """
    if cause is not None:
        current_app.logger.exception(str(cause))
    kw['status'] = status
    return errors_response(status, [error(**kw)])


def errors_response(status, errors):
    """Return an error response with multiple errors.

    `status` is an integer representing an HTTP status code corresponding to an
    error response.

    `errors` is a list of error dictionaries, each of which must satisfy the
    requirements of the JSON API specification.

    This function returns a two-tuple whose left element is a dictionary
    representing a JSON API response document and whose right element is
    simply `status`.

    In addition to a list of the error objects under the ``'errors'``
    key, a jsonapi object, the returned dictionary object also includes
    under the ``'meta'`` element a key with a special name, stored in
    the key :data:`_STATUS`, which is used to workaround an
    incompatibility between Flask and mimerender that doesn't allow
    setting headers on a global response object.

    The keys within each error object are described in the `Errors`_
    section of the JSON API specification.

    .. _Errors: http://jsonapi.org/format/#errors

    """
    # TODO Use an error serializer.
    document = {'errors': errors, 'jsonapi': {'version': JSONAPI_VERSION},
                'meta': {_STATUS: status}}
    return document, status


def error_from_serialization_exception(exception, included=False):
    """Returns an error dictionary, as returned by :func:`error`,
    representing the given instance of :exc:`SerializationException`.

    The ``detail`` element in the returned dictionary will be more
    detailed if :attr:`SerializationException.instance` is not ``None``.

    If `included` is ``True``, this indicates that the exceptions were
    raised by attempts to serialize resources included in a compound
    document; this modifies the error message for the exceptions a bit
    to indicate that the resources were included resource, not primary
    data. If :attr:`~SerializationException.instance` is not ``None``,
    however, that message is preferred and `included` has no effect.

    """
    # As long as `exception` is a `SerializationException` that has been
    # initialized with an actual instance of a SQLAlchemy model, these
    # helper function calls should not cause a problem.
    type_ = collection_name(get_model(exception.instance))
    id_ = primary_key_value(exception.instance)
    if exception.message is not None:
        detail = exception.message
    else:
        resource = 'included resource' if included else 'resource'
        detail = 'Failed to serialize {0} of type {1} and ID {2}'
        detail = detail.format(resource, type_, id_)
    return error(status=500, detail=detail)


def errors_from_serialization_exceptions(exceptions, included=False):
    """Returns an errors response object, as returned by
    :func:`errors_response`, representing the given list of
    :exc:`SerializationException` objects.

    If `included` is ``True``, this indicates that the exceptions were
    raised by attempts to serialize resources included in a compound
    document; this modifies the error message for the exceptions a bit.

    """
    _to_error = partial(error_from_serialization_exception, included=included)
    errors = list(map(_to_error, exceptions))
    return errors_response(500, errors)


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


# TODO Subclasses for different kinds of linkers (relationship, resource
# object, to-one relations, related resource, etc.).
class Linker(object):

    def __init__(self, model):
        self.model = model

    def _related_resource_links(self, resource, primary_resource,
                                relation_name):
        resource_id = primary_key_value(primary_resource)
        related_resource_id = primary_key_value(resource)
        self_link = url_for(self.model, resource_id, relation_name,
                            related_resource_id)
        links = {'self': self_link}
        return links

    def _relationship_links(self, resource_id, relation_name):
        self_link = url_for(self.model, resource_id, relation_name,
                            relationship=True)
        related_link = url_for(self.model, resource_id, relation_name)
        links = {'self': self_link, 'related': related_link}
        return links

    def _to_one_relation_links(self, resource_id, relation_name):
        self_link = url_for(self.model, resource_id, relation_name)
        links = {'self': self_link}
        return links

    def _primary_resource_links(self, resource_id):
        self_link = url_for(self.model, resource_id=resource_id)
        links = {'self': self_link}
        return links

    def _collection_links(self):
        self_link = url_for(self.model)
        links = {'self': self_link}
        return links

    def generate_links(self, resource, primary_resource, relation_name,
                       is_related_resource, is_relationship):
        if primary_resource is not None:
            if is_related_resource:
                return self._related_resource_links(resource, primary_resource,
                                                    relation_name)
            else:
                resource_id = primary_key_value(primary_resource)
                if is_relationship:
                    return self._relationship_links(resource_id, relation_name)
                else:
                    return self._to_one_relation_links(resource_id,
                                                       relation_name)
        else:
            if resource is not None:
                resource_id = primary_key_value(resource)
                return self._primary_resource_links(resource_id)
            else:
                return self._collection_links()


class PaginationLinker(object):

    def __init__(self, pagination):
        self.pagination = pagination

    def generate_links(self):
        return self.pagination.pagination_links

    def generate_header_links(self):
        return self.pagination.header_links


class Paginated(object):
    """Represents a paginated list of resources.

    This class is intended to be instantiated *after* the correct page
    of a collection has been computed. It is mainly used to handle link
    URLs for JSON API documents and HTTP headers.

    `items` is a list of dictionaries, each of which is a JSON API
    resource, either a resource object or a link object.

    `page_size` and `page_number` are the size and number of the current
    page (that is, the page containing `items`). If `page_size` is zero,
    then `items` must be *all* the items in the collection requested by
    the client. In this particular case, this object does not really
    represent a paginated response. Thus, there will be no pagination or
    header links; see :attr:`header_links` and
    :attr:`pagination_links`. Otherwise, `page_size` must be at least as
    large as the length of `items`.

    `num_results` is the total number of resources or link objects on
    all pages, not just the page represented by `items`.

    `first`, `last`, `prev`, and `next_` are integers representing the
    number of the first, last, previous, and next pages,
    respectively. These can also be ``None``, in the case that there is
    no such page.

    `filters`, `sort`, and `group_by` are the filtering, sorting, and
    grouping query parameters from the request that yielded the given
    items.

    After instantiating this object, one can access a list of link
    header strings and a dictionary of pagination link strings as
    suggested by the JSON API specification, as well as the number of
    results and the items provided in the constructor. For example::

        >>> people = ['person1', 'person2', 'person3']
        >>> paginated = Paginated(people, num_results=10, page_number=2,
        ...                       page_size=3, first=1, last=4, prev=1, next=3)
        >>> paginated.items
        ['person1', 'person2', 'person3']
        >>> paginated.num_results
        10
        >>> for rel, url in paginated.pagination_links.items():
        ...     print(rel, url)
        ...
        first http://example.com/api/person?page[size]=3&page[number]=1
        last http://example.com/api/person?page[size]=3&page[number]=4
        prev http://example.com/api/person?page[size]=3&page[number]=1
        next http://example.com/api/person?page[size]=3&page[number]=3
        >>> for link in paginated.header_links:
        ...     print(link)
        ...
        <http://example.com/api/person?page[size]=3&page[number]=1>; rel="first"
        <http://example.com/api/person?page[size]=3&page[number]=4>; rel="last"
        <http://example.com/api/person?page[size]=3&page[number]=1>; rel="prev"
        <http://example.com/api/person?page[size]=3&page[number]=3>; rel="next"

    """

    @staticmethod
    def _filters_to_string(filters):
        """Returns a string representation of the specified dictionary
        of filter objects.

        This is essentially the inverse operation of the parsing that is
        done when reading the filter objects from the query parameters
        of the request string in a :http:method:`get` request.

        """
        return json.dumps(filters)

    @staticmethod
    def _sort_to_string(sort):
        """Returns a string representation of the specified sort fields.

        This is essentially the inverse operation of the parsing that is
        done when reading the sort fields from the query parameters of
        the request string in a :http:method:`get` request.

        """
        return ','.join(''.join((dir_, field)) for dir_, field in sort)

    @staticmethod
    def _group_to_string(group_by):
        """Returns a string representation of the specified grouping
        fields.

        This is essentially the inverse operation of the parsing that is
        done when reading the grouping fields from the query parameters
        of the request string in a :http:method:`get` request.

        """
        return ','.join(group_by)

    @staticmethod
    def _url_without_pagination_params():
        """Returns the request URL including all query parameters except
        the page size and page number query parameters.

        The URL is returned as a string.

        """
        # Parse pieces of the URL requested by the client.
        base_url = request.base_url
        query_params = request.args
        # Set the new query_parameters to be everything except the
        # pagination query parameters.
        #
        # TODO In Python 3, this should be a dict comprehension.
        new_query = dict((k, v) for k, v in query_params.items()
                         if k not in (PAGE_NUMBER_PARAM, PAGE_SIZE_PARAM))
        new_query_string = '&'.join(map('='.join, new_query.items()))
        # Join the base URL with the query parameter string.
        return '{0}?{1}'.format(base_url, new_query_string)

    @staticmethod
    def _to_url(base_url, query_params):
        """Returns the specified base URL augmented with the given query
        parameters.

        `base_url` is a string representing a URL.

        `query_params` is a dictionary whose keys and values are strings,
        representing the query parameters to append to the given URL.

        If the base URL already has query parameters, the ones given in
        `query_params` are appended.

        """
        query_string = '&'.join(map('='.join, query_params.items()))
        scheme, netloc, path, params, query, fragment = urlparse(base_url)
        if query:
            query_string = '&'.join((query, query_string))
        parsed = (scheme, netloc, path, params, query_string, fragment)
        return urlunparse(parsed)

    def __init__(self, items, first=None, last=None, prev=None, next_=None,
                 page_size=None, num_results=None, filters=None, sort=None,
                 group_by=None):
        self._items = items
        self._num_results = num_results
        # Pagination links and the link header are computed by the code below.
        self._pagination_links = {}
        self._header_links = []
        # If page size is zero, there is really no pagination, so we
        # don't need to compute pagination links or header links.
        if page_size == 0:
            return
        # Create the pagination link URLs.
        #
        # Need to account for filters, sort, and group_by, in addition
        # to pagination links, so we collect those query parameters
        # here, if they exist.
        query_params = {}
        if filters:
            query_params[FILTER_PARAM] = Paginated._filters_to_string(filters)
        if sort:
            query_params[SORT_PARAM] = Paginated._sort_to_string(sort)
        if group_by:
            query_params[GROUP_PARAM] = Paginated._group_to_string(group_by)
        # The page size is independent of the link type (first, last,
        # next, or prev).
        query_params[PAGE_SIZE_PARAM] = str(page_size)
        # Maintain a list of URLs that should appear in a Link
        # header. If a link does not exist (for example, if there is no
        # previous page), then that link URL will not appear in this
        # list.
        link_numbers = [first, last, prev, next_]
        # Determine the URL as it would appear without the
        # client-requested pagination query parameters.
        #
        # (`base_url` is not a great name here, since
        # `flask.Request.base_url` is the URL *without* the query
        # parameters.)
        base_url = Paginated._url_without_pagination_params()
        for rel, num in zip(LINK_NAMES, link_numbers):
            # If the link doesn't exist (for example, if there is no
            # previous page), then add ``None`` to the pagination links
            # but don't add a link URL to the headers.
            if num is None:
                self._pagination_links[rel] = None
            else:
                # Each time through this `for` loop we update the page
                # number in the `query_param` dictionary, so the the
                # `_to_url` method will give us the correct URL for that
                # page.
                query_params[PAGE_NUMBER_PARAM] = str(num)
                url = Paginated._to_url(base_url, query_params)
                link_string = '<{0}>; rel="{1}"'.format(url, rel)
                self._header_links.append(link_string)
                self._pagination_links[rel] = url
        # TODO Here we should really make the attributes immutable:
        #
        #     self._header_links = ImmutableList(self._header_links)
        #     ...
        #

    @property
    def header_links(self):
        """List of link header strings for the paginated response.

        The headers can be provided to the HTTP response by using a
        dictionary like this::

            >>> paginated = Paginated(...)
            >>> headers = {'Link': ','.join(paginated.header_links)}

        There may be a way of creating multiple link headers like
        this, in certain situations::

            >>> headers = [('Link', link) for link in header_links]

        """
        return self._header_links

    @property
    def pagination_links(self):
        """Dictionary of pagination links for JSON API documents.

        This dictionary has the relationship of the page to this page as
        the key (``'first'``, ``'last'``, ``'prev'``, and ``'next'``)
        and the URL as the value.

        """
        return self._pagination_links

    @property
    def items(self):
        """The items in the current page that this object represents."""
        return self._items

    @property
    def num_results(self):
        """The total number of elements in the search result, one page
        of which this object represents.

        """
        return self._num_results


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

    def collection_parameters(self, resource_id=None, relation_name=None):
        """Gets filtering, sorting, grouping, and other settings from
        the request that affect the collection of resources in a
        response.

        Returns a four-tuple of the form ``(filters, sort, group_by,
        single)``. These can be provided to the
        :func:`~flask_restless.search.search` function; for more
        information, see the documentation for that function.

        This function can only be invoked in a request context.

        """
        # Determine filtering options.
        #
        # `filters` stores the filter objects, which are retrieved from the
        # query parameter at :data:`FILTER_PARAM`. We also support simple
        # filtering, but we need to search the entire list of query
        # parameters for everything of the form 'filter[...]' and convert
        # each value found into a filter object.
        filters = json.loads(request.args.get(FILTER_PARAM, '[]'))
        for key, value in request.args.items():
            # Skip keys that are not filters and are not filter[objects]
            # and filter[single] request parameters.
            #
            # TODO Document that field names cannot be 'objects' or 'single'.
            if not key.startswith('filter'):
                continue
            if key in (FILTER_PARAM, SINGLE_PARAM):
                continue
            # Get the field on which to filter and the values to match.
            field = key[7:-1]
            values = value.split(',')
            # Determine whether this is a request of the form `GET
            # /comments` or `GET /article/1/comments`.
            if resource_id is not None and relation_name is not None:
                primary_model = get_related_model(self.model, relation_name)
            else:
                primary_model = self.model
            # If the field is a relationship, use the `has` operator
            # with the `in` operator to select only those instances of
            # the primary model that have related instances matching the
            # given foreign keys. Otherwise, the field is an attribute,
            # so we use the `in` operator directly.
            if is_relationship(primary_model, field):
                related_model = get_related_model(primary_model, field)
                field_name = primary_key_for(related_model)
                new_filter = {
                    'name': field,
                    'op': 'has',
                    'val': {
                        'name': field_name,
                        'op': 'in',
                        'val': values
                    }
                }
            else:
                new_filter = {
                    'name': field,
                    'op': 'in',
                    'val': values
                }
            # TODO This creates a problem where the computed link URLs
            # have the additional filter object as a `filter[objects]`
            # param.
            filters.append(new_filter)
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
        sort = request.args.get(SORT_PARAM)
        if sort:
            sort = [('-', value[1:]) if value.startswith('-') else ('+', value)
                    for value in sort.split(',')]
        else:
            sort = []

        # Determine grouping options.
        group_by = request.args.get(GROUP_PARAM)
        if group_by:
            group_by = group_by.split(',')
        else:
            group_by = []

        # Determine whether the client expects a single resource response.
        try:
            single = bool(int(request.args.get(SINGLE_PARAM, 0)))
        except ValueError:
            raise SingleKeyError('failed to extract Boolean from parameter')

        return filters, sort, group_by, single


class APIBase(ModelView):
    """Base class for view classes that provide fetch, create, update, and
    delete functionality for resources and relationships on resources.

    `session` and `model` are as described in the constructor of the
    superclass.

    `preprocessors` and `postprocessors` are as described in :ref:`processors`.

    `primary_key` is as described in :ref:`primarykey`.

    `serializer` and `deserializer` are as described in
    :ref:`serialization`.

    `validation_exceptions` are as described in :ref:`validation`.

    `includes` are as described in :ref:`includes`.

    `page_size` and `max_page_size` are as described in
    :ref:`pagination`.

    `allow_to_many_replacement` is as described in
    :ref:`allowreplacement`.

    """

    #: List of decorators applied to every method of this class.
    decorators = [catch_processing_exceptions] + ModelView.decorators

    def __init__(self, session, model, preprocessors=None, postprocessors=None,
                 primary_key=None, serializer=None, deserializer=None,
                 validation_exceptions=None, includes=None, page_size=10,
                 max_page_size=100, allow_to_many_replacement=False, *args,
                 **kw):
        super(APIBase, self).__init__(session, model, *args, **kw)

        #: The name of the collection specified by the given model class
        #: to be used in the URL for the ReSTful API created.
        self.collection_name = collection_name(self.model)

        #: The default set of related resources to include in compound
        #: documents, given as a set of relationship paths.
        self.default_includes = includes
        if self.default_includes is not None:
            self.default_includes = frozenset(self.default_includes)

        #: Whether to allow complete replacement of a to-many relationship when
        #: updating a resource.
        self.allow_to_many_replacement = allow_to_many_replacement

        #: The default page size for responses that consist of a
        #: collection of resources.
        #:
        #: Requests made by clients may override this default by
        #: specifying ``page_size`` as a query parameter.
        self.page_size = page_size

        #: The maximum page size that a client can request.
        #:
        #: Even if a client specifies that greater than `max_page_size`
        #: should be returned, at most `max_page_size` results will be
        #: returned.
        self.max_page_size = max_page_size

        #: A custom serialization function for primary resources; see
        #: :ref:`serialization` for more information.
        #:
        #: This should not be ``None``, unless a subclass is not going to use
        #: serialization.
        self.serializer = serializer

        #: A custom serialization function for linkage objects.
        #self.serialize_relationship = simple_relationship_serialize

        #: A custom deserialization function for primary resources; see
        #: :ref:`serialization` for more information.
        #:
        #: This should not be ``None``, unless a subclass is not going to use
        #: deserialization.
        self.deserializer = deserializer

        #: The tuple of exceptions that are expected to be raised during
        #: validation when creating or updating a model.
        self.validation_exceptions = tuple(validation_exceptions or ())

        #: The name of the attribute containing the primary key to use as the
        #: ID of the resource.
        self.primary_key = primary_key

        #: The mapping from method name to a list of functions to apply after
        #: the main functionality of that method has been executed.
        self.postprocessors = defaultdict(list, upper(postprocessors or {}))

        #: The mapping from method name to a list of functions to apply before
        #: the main functionality of that method has been executed.
        self.preprocessors = defaultdict(list, upper(preprocessors or {}))

        #: The mapping from resource type name to requested sparse
        #: fields for resources of that type.
        self.sparse_fields = parse_sparse_fields()

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

    def collection_processor_type(self, *args, **kw):
        """The suffix for the pre- and postprocessor identifiers for
        requests on collections of resources.

        This is an abstract method; subclasses must override this
        method.

        """
        raise NotImplementedError

    def resource_processor_type(self, *args, **kw):
        """The suffix for the pre- and postprocessor identifiers for
        requests on resource objects.

        This is an abstract method; subclasses must override this
        method.

        """
        raise NotImplementedError

    def use_resource_identifiers(self):
        """Whether primary data in responses use resource identifiers or
        full resource objects.

        Subclasses that handle resource linkage should override this
        method so that it returns ``True``.

        """
        return False

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
            title = 'Validation error'
            return error_response(400, cause=exception, title=title)
        if isinstance(errors, dict):
            errors = [error(title='Validation error', status=400,
                            detail='{0}: {1}'.format(field, detail))
                      for field, detail in errors.items()]
        current_app.logger.exception(str(exception))
        return errors_response(400, errors)

    def get_all_inclusions(self, instance_or_instances):
        """Returns a list of all the requested included resources
        associated with the given instance or instances of a SQLAlchemy
        model.

        ``instance_or_instances`` is either a SQLAlchemy
        :class:`~sqlalchemy.orm.query.Query` object representing
        multiple instances of a SQLAlchemy model, or it is simply one
        instance of a model. These instances represent the resources
        that will be returned as primary data in the JSON API
        response. The resources to include will be computed based on
        these data and the client's ``include`` query parameter.

        This function raises :exc:`MultipleExceptions` if any included
        resource causes a serialization exception. If this exception is
        raised, the :attr:`MultipleExceptions.exceptions` attribute
        contains a list of the :exc:`SerializationException` objects
        that caused it.

        """
        # If `instance_or_instances` is actually just a single instance
        # of a SQLAlchemy model, get the resources to include for that
        # one instance. Otherwise, collect the resources to include for
        # each instance in `instances`.
        if isinstance(instance_or_instances, Query):
            instances = instance_or_instances
            to_include = set(chain(map(self.resources_to_include, instances)))
        else:
            instance = instance_or_instances
            to_include = self.resources_to_include(instance)
        only = self.sparse_fields
        # HACK We only need the primary data from the JSON API document,
        # not the metadata (so really the serializer is doing more work
        # than it needs to here).
        result = simple_serialize_many(to_include, only=only)
        return result['data']

    def _paginated(self, items, filters=None, sort=None, group_by=None):
        """Returns a :class:`Paginated` object representing the
        correctly paginated list of resources to return to the client,
        based on the current request.

        `items` is a SQLAlchemy query, or a Flask-SQLAlchemy query,
        containing all requested elements of a collection regardless of
        the page number or size in the client's request.

        `filters`, `sort`, and `group_by` must have already been
        extracted from the client's request (as by
        :meth:`collection_parameters`) and applied to the query.

        If `relationship` is ``True``, the resources in the query object
        will be serialized as linkage objects instead of resources
        objects.

        # This method serializes the (correct page of) resources. As such,
        # it raises an instance of :exc:`MultipleExceptions` if there is a
        # problem serializing resources.

        """
        # Determine the client's page size request. Raise an exception
        # if the page size is out of bounds, either too small or too
        # large.
        page_size = int(request.args.get(PAGE_SIZE_PARAM, self.page_size))
        if page_size < 0:
            raise PaginationError('Page size must be a positive integer')
        if page_size > self.max_page_size:
            msg = "Page size must not exceed the server's maximum: {0}"
            msg = msg.format(self.max_page_size)
            raise PaginationError(msg)
        # If the page size is 0, just return everything.
        if page_size == 0:
            # # These serialization calls may raise MultipleExceptions, or
            # # possible SerializationExceptions.
            # if is_relationship:
            #     result = self.relationship_serializer.serialize_many(items)
            # else:
            #     serialize_many = self.serializer.serialize_many
            #     result = serialize_many(items, only=self.sparse_fields)

            # TODO Ideally we would like to use the folowing code.
            #
            #     # Use `len()` here instead of doing `count(self.session,
            #     # items)` because the former should be faster.
            #     num_results = len(result['data'])
            #
            # but we can't get the length of the list of items until
            # we serialize them.
            num_results = count(self.session, items)
            return Paginated(items, page_size=0, num_results=num_results)
        # Determine the client's page number request. Raise an exception
        # if the page number is out of bounds.
        page_number = int(request.args.get(PAGE_NUMBER_PARAM, 1))
        if page_number < 0:
            raise PaginationError('Page number must be a positive integer')
        # At this point, we know the page size is positive, so we
        # paginate the response.
        #
        # If the query is really a Flask-SQLAlchemy query, we can use
        # its built-in pagination. Otherwise, we need to manually
        # compute the page numbers, the number of results, etc.
        if hasattr(items, 'paginate'):
            pagination = items.paginate(page_number, page_size,
                                        error_out=False)
            num_results = pagination.total
            first = 1
            last = pagination.pages
            prev = pagination.prev_num
            next_ = pagination.next_num
            items = pagination.items
        else:
            num_results = count(self.session, items)
            first = 1
            # Handle a special case for an empty collection of items.
            #
            # There will be no division-by-zero error here because we
            # have already checked that page size is not equal to zero
            # above.
            if num_results == 0:
                last = 1
            else:
                last = int(math.ceil(num_results / page_size))
            prev = page_number - 1 if page_number > 1 else None
            next_ = page_number + 1 if page_number < last else None
            offset = (page_number - 1) * page_size
            # TODO Use Query.slice() instead, since it's easier to use.
            items = items.limit(page_size).offset(offset)
        # Wrap the list of results in a Paginated object, which
        # represents the result set and stores some extra information
        # about how it was determined.
        return Paginated(items, num_results=num_results, first=first,
                         last=last, next_=next_, prev=prev,
                         page_size=page_size, filters=filters, sort=sort,
                         group_by=group_by)

    def _get_resource_helper(self, resource, primary_resource=None,
                             relation_name=None, related_resource=False):
        is_relationship = self.use_resource_identifiers()
        # The resource to serialize may be `None`, if we are fetching a
        # to-one relation that has no value. In this case, the "data"
        # for the JSON API response is just `None`.
        if resource is None:
            result = JsonApiDocument()
        # Otherwise, we are serializing one of several possibilities.
        #
        # - a primary resource (as in `GET /person/1`),
        # - a to-one relation (as in `GET /article/1/author`)
        # - a related resource (as in `GET /person/1/articles/2`).
        # - a to-one relationship (as in `GET /article/1/relationships/author`)
        #
        else:
            try:
                # This covers the relationship object case...
                if is_relationship:
                    result = simple_relationship_serialize(resource)
                # ...and this covers the resource object cases.
                else:
                    model = get_model(resource)
                    # Determine the serializer for this instance. If there
                    # is no serializer, use the default serializer for the
                    # current resource, even though the current model may
                    # different from the model of the current instance.
                    try:
                        serializer = serializer_for(model)
                    except ValueError:
                        # TODO Should we fail instead, thereby effectively
                        # requiring that an API has been created for each
                        # type of resource? This is mainly a design
                        # question.
                        serializer = self.serializer
                    # This may raise ValueError
                    _type = collection_name(model)
                    only = self.sparse_fields.get(_type)
                    # This may raise SerializationException
                    result = serializer.serialize(resource, only=only)
            except SerializationException as exception:
                return errors_from_serialization_exceptions([exception])

        # Determine the top-level links.
        linker = Linker(self.model)
        links = linker.generate_links(resource, primary_resource,
                                      relation_name, related_resource,
                                      is_relationship)
        result['links'] = links

        # TODO Create an Includer class, like the Linker class.
        # # Determine the top-level inclusions.
        # includer = Includer(resource)
        # includes = includer.generate_includes(resource)
        # result['includes'] = includes

        # Include any requested resources in a compound document.
        try:
            included = self.get_all_inclusions(resource)
        except MultipleExceptions as e:
            # By the way we defined `get_all_inclusions()`, we are
            # guaranteed that each of the underlying exceptions is a
            # `SerializationException`. Thus we can use
            # `errors_from_serialization_exception()`.
            return errors_from_serialization_exceptions(e.exceptions,
                                                        included=True)
        if included:
            result['included'] = included
        # HACK Need to do this here to avoid a too-long line.
        is_relation = primary_resource is not None
        is_related_resource = is_relation and related_resource
        kw = {'is_relation': is_relation,
              'is_related_resource': is_related_resource}
        # This method could have been called on a request to fetch a
        # single resource, a to-one relation, or a member of a to-many
        # relation. We need to use the appropriate postprocessor here.
        processor_type = 'GET_{0}'.format(self.resource_processor_type(**kw))
        for postprocessor in self.postprocessors[processor_type]:
            postprocessor(result=result)
        return result, 200

    def _get_collection_helper(self, resource=None, relation_name=None,
                               filters=None, sort=None, group_by=None,
                               single=False):
        if (resource is None) ^ (relation_name is None):
            raise ValueError('resource and relation must be both None or both'
                             ' not None')
        # Compute the result of the search on the model.
        is_relation = resource is not None
        if is_relation:
            search_ = partial(search_relationship, self.session, resource,
                              relation_name)
        else:
            search_ = partial(search, self.session, self.model)
        try:
            search_items = search_(filters=filters, sort=sort,
                                   group_by=group_by)
        except (FilterParsingError, FilterCreationError) as exception:
            detail = 'invalid filter object: {0}'.format(str(exception))
            return error_response(400, cause=exception, detail=detail)
        except Exception as exception:
            detail = 'Unable to construct query'
            return error_response(400, cause=exception, detail=detail)

        is_relationship = self.use_resource_identifiers()
        # Add the primary data (and any necessary links) to the JSON API
        # response object.
        #
        # If the result of the search is a SQLAlchemy query object, we need to
        # return a collection.
        if not single:
            try:
                paginated = self._paginated(search_items, filters=filters,
                                            sort=sort, group_by=group_by)
            except PaginationError as exception:
                detail = exception.args[0]
                return error_response(400, cause=exception, detail=detail)
            # Serialize the found items.
            #
            # We are serializing one of three possibilities.
            #
            # - a collection of primary resources (as in `GET /person`),
            # - a to-many relation (as in `GET /person/1/articles`),
            # - a to-many relationship (as in `GET /person/1/relationships/articles`)
            #
            items = paginated.items
            # This covers the relationship object case...
            if is_relationship:
                result = simple_relationship_serialize_many(items)
            # ...and this covers the primary resource collection and
            # to-many relation cases.
            else:
                only = self.sparse_fields
                try:
                    result = self.serializer.serialize_many(items, only=only)
                except MultipleExceptions as e:
                    return errors_from_serialization_exceptions(e.exceptions)
                except SerializationException as exception:
                    return errors_from_serialization_exceptions([exception])

            # Determine the top-level links.
            linker = Linker(self.model)
            links = linker.generate_links(resource, None, relation_name, None,
                                          is_relationship)
            pagination_linker = PaginationLinker(paginated)
            pagination_links = pagination_linker.generate_links()
            if 'links' not in result:
                result['links'] = {}
            result['links'].update(links)
            result['links'].update(pagination_links)

            # Create the metadata for the response, like headers and
            # total number of found items.
            pagination_header_links = pagination_linker.generate_header_links()
            link_header = ','.join(pagination_header_links)
            headers = dict(Link=link_header)
            num_results = paginated.num_results

        # Otherwise, the result of the search should be a single resource.
        else:
            try:
                resource = search_items.one()
            except NoResultFound as exception:
                detail = 'No result found'
                return error_response(404, cause=exception, detail=detail)
            except MultipleResultsFound as exception:
                detail = 'Multiple results found'
                return error_response(404, cause=exception, detail=detail)
            # Serialize the single resource.
            try:
                if is_relationship:
                    result = simple_relationship_serialize(resource)
                else:
                    only = self.sparse_fields.get(self.collection_name)
                    result = self.serializer.serialize(resource, only=only)
            except SerializationException as exception:
                return errors_from_serialization_exceptions([exception])

            # Determine the top-level links.
            linker = Linker(self.model)
            # Here we determine whether we are looking at a collection,
            # as in `GET /people`, or a to-many relation, as in `GET
            # /people/1/comments`.
            if resource is None:
                links = linker.generate_links(None, None, None, None, False, False)
            else:
                links = linker.generate_links(resource, None, None, False, False)
            result['links'].update(links)

            # Create the metadata for the response, like headers and
            # total number of found items.
            primary_key = primary_key_for(resource)
            pk_value = result['data'][primary_key]
            location = url_for(self.model, resource_id=pk_value)
            headers = dict(Location=location)
            num_results = 1

        # Determine the resources to include (in a compound document).
        if self.use_resource_identifiers():
            instances = resource
        else:
            instances = search_items
        # Include any requested resources in a compound document.
        try:
            included = self.get_all_inclusions(instances)
        except MultipleExceptions as e:
            # By the way we defined `get_all_inclusions()`, we are
            # guaranteed that each of the underlying exceptions is a
            # `SerializationException`. Thus we can use
            # `errors_from_serialization_exception()`.
            return errors_from_serialization_exceptions(e.exceptions,
                                                        included=True)
        if 'included' not in result:
            result['included'] = []
        result['included'].extend(included)

        # This method could have been called on either a request to
        # fetch a collection of resources or a to-many relation.
        processor_type = \
            self.collection_processor_type(is_relation=is_relation)
        processor_type = 'GET_{0}'.format(processor_type)
        for postprocessor in self.postprocessors[processor_type]:
            postprocessor(result=result, filters=filters, sort=sort,
                          group_by=group_by, single=single)
        # Add the metadata to the JSON API response object.
        #
        # HACK Provide the headers directly in the result dictionary, so that
        # the :func:`jsonpify` function has access to them. See the note there
        # for more information. They don't really need to be under the ``meta``
        # key, that's just for semantic consistency.
        status = 200
        meta = {_HEADERS: headers, _STATUS: status, 'total': num_results}
        if 'meta' not in result:
            result['meta'] = {}
        result['meta'].update(meta)
        return result, status, headers

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
        return set(chain(resources_from_path(instance, path)
                         for path in toinclude))
