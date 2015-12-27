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
from sqlalchemy.exc import DataError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm.exc import FlushError
from sqlalchemy.orm.exc import MultipleResultsFound
from sqlalchemy.orm.exc import NoResultFound
from werkzeug import parse_options_header
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
from .helpers import upper_keys as upper
from .helpers import url_for
from .search import ComparisonToNull
from .search import search
from .search import search_relationship
from .serialization import simple_serialize
from .serialization import simple_relationship_serialize
from .serialization import DefaultDeserializer
from .serialization import DeserializationException
from .serialization import SerializationException

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

#: SQLAlchemy errors that, when caught, trigger a rollback of the session.
ROLLBACK_ERRORS = (DataError, IntegrityError, ProgrammingError, FlushError)

#: Strings that indicate a database conflict when appearing in an error
#: message of an exception raised by SQLAlchemy.
CONFLICT_INDICATORS = ('conflicts with', 'UNIQUE constraint failed')

#: The names of pagination links that appear in both ``Link`` headers
#: and JSON API links.
LINK_NAMES = ('first', 'last', 'prev', 'next')

#: The query parameter key that identifies filter objects in a
#: :http:method:`get` request.
FILTER_PARAM = 'filter[objects]'

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

# for explanation of "media-range", etc. see Sections 5.3.{1,2} of RFC 7231
_accept_re = re.compile(
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
            detail = exception.description or str(exception)
            status = exception.code
            return error_response(status, cause=exception, detail=detail)
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

    Returns an iterable of ``(value, extra)`` tuples. If there were no
    media type parameters, then ``extra`` is simply ``None``.

    """
    def match_to_pair(match):
        name = match.group(1)
        extra = match.group(2)
        # This is the main difference between our implementation and
        # Werkzeug's implementation: all we want to know is whether
        # there is any media type parameters or not, so we mark the
        # quality is ``None`` instead of ``1`` here.
        quality = max(min(float(extra), 1), 0) if extra else None
        return name, quality
    return (match_to_pair(match) for match in _accept_re.finditer(value))


def requires_json_api_accept(func):
    """Decorator that requires requests have the ``Accept`` header
    required by the JSON API specification.

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
        header = request.headers.get('Accept')
        header_pairs = parse_accept_header(header)
        jsonapi_pairs = [(name, extra) for name, extra in header_pairs
                         if name.startswith(CONTENT_TYPE)]
        if (len(jsonapi_pairs) > 0
            and all(extra is not None for name, extra in jsonapi_pairs)):
            detail = ('Accept header contained JSON API content type, but each'
                      ' instance occurred with media type parameters; at least'
                      ' one instance must appear without parameters (the part'
                      ' after the semicolon)')
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
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kw):
            try:
                return func(*args, **kw)
            # TODO should `sqlalchemy.exc.InvalidRequestError`s also be caught?
            except ROLLBACK_ERRORS as exception:
                session.rollback()
                # Special status code for conflicting instances: 409 Conflict
                status = 409 if is_conflict(exception) else 400
                detail = str(exception)
                return error_response(status, cause=exception, detail=detail)
        return wrapped
    return decorator


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
    fields = {key[7:-1]: set(value.split(','))
              for key, value in request.args.items()
              if key.startswith('fields[') and key.endswith(']')}
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
    nextlevel = {instance}
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


def error_response(status, cause=None, **kw):
    """Returns a correctly formatted error response with the specified
    parameters.

    This is a convenience function for::

        errors_response(status, [error(**kw)])

    For more information, see :func:`errors_response`.

    """
    if cause is not None:
        current_app.logger.exception(str(cause))
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
    def _to_url(base_url, query_params):
        """Returns the specified base URL augmented with the given query
        parameters.

        `base_url` is a string representing a URL.

        `query_params` is a dictionary whose keys and values are strings,
        representing the query parameters to append to the given URL.

        If the base URL already has query parameters, the ones given in
        `query_params` are appended.

        """
        query_string = '&'.join('='.join((k, v))
                                for k, v in query_params.items())
        scheme, netloc, path, params, query, fragment = urlparse(base_url)
        if query:
            query_string = '&'.join((query, query_string))
        parsed = (scheme, netloc, path, params, query_string, fragment)
        return urlunparse(parsed)

    def __init__(self, items, first=None, last=None, prev=None, next_=None,
                 page_size=None, page_number=None, num_results=None,
                 filters=None, sort=None, group_by=None):
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
                url = Paginated._to_url(request.base_url, query_params)
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
        return self._items

    @property
    def num_results(self):
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
            detail = 'Unable to decode JSON in `functions` query parameter'
            return error_response(400, cause=exception, detail=detail)
        try:
            result = evaluate_functions(self.session, self.model, data)
        except AttributeError as exception:
            detail = 'No such field "{0}"'.format(exception.field)
            return error_response(400, cause=exception, detail=detail)
        except KeyError as exception:
            detail = str(exception)
            return error_response(400, cause=exception, detail=detail)
        except OperationalError as exception:
            detail = 'No such function "{0}"'.format(exception.function)
            return error_response(400, cause=exception, detail=detail)
        return dict(data=result)


class APIBase(ModelView):
    """Base class for view classes that provide fetch, create, update, and
    delete functionality for resources and relationships on resources.

    `session` and `model` are as described in the constructor of the
    superclass.

    `preprocessors` and `postprocessors` are as described in :ref:`processors`.

    `primary_key` is as described in :ref:`primarykey`.

    `validation_exceptions` are as described in :ref:`validation`.

    `allow_to_many_replacement` is as described in :ref:`allowreplacement`.

    """

    #: List of decorators applied to every method of this class.
    decorators = [catch_processing_exceptions] + ModelView.decorators

    def __init__(self, session, model, preprocessors=None, postprocessors=None,
                 primary_key=None, serializer=None, deserializer=None,
                 validation_exceptions=None, includes=None, page_size=10,
                 max_page_size=100, allow_to_many_replacement=None, *args,
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
        #: Use our default serializer if none is specified.
        self.serialize = serializer or simple_serialize

        #: A custom serialization function for linkage objects.
        self.serialize_relationship = simple_relationship_serialize

        #: A custom deserialization function for primary resources; see
        #: :ref:`serialization` for more information.
        #:
        #: Use our default deserializer if none is specified.
        self.deserialize = deserializer or DefaultDeserializer(session, model)

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
            title = 'Validation error'
            return error_response(400, cause=exception, title=title)
        if isinstance(errors, dict):
            errors = [error(title='Validation error',
                            detail='{0}: {1}'.format(field, detail))
                      for field, detail in errors.items()]
        current_app.logger.exception(str(exception))
        return errors_response(400, errors)

    def _collection_parameters(self):
        """Gets filtering, sorting, grouping, and other settings from the
        request that affect the collection of resources in a response.

        Returns a four-tuple of the form ``(filters, sort, group_by,
        single)``. These can be provided to the
        :func:`~flask_restless.search.search` function; for more
        information, see the documentation for that function.

        """
        # Determine filtering options.
        filters = json.loads(request.args.get(FILTER_PARAM, '[]'))
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
        if any(order not in ('+', '-') for order, field in sort):
            raise SortKeyError('sort parameter must begin with "+" or "-"')

        # Determine grouping options.
        group_by = request.args.get(GROUP_PARAM)
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

    def _paginated(self, items, filters=None, sort=None, group_by=None,
                   only=None):
        """Returns a :class:`Paginated` object representing the
        correctly paginated list of resources to return to the client,
        based on the current request.

        `items` is a SQLAlchemy query, or a Flask-SQLAlchemy query,
        containing all requested elements of a collection regardless of
        the page number or size in the client's request.

        `filters`, `sort`, and `group_by` must have already been
        extracted from the client's request (as by
        :meth:`_collection_parameters`) and applied to the query.

        `only` must have already been parsed from the request (as by
        :func:`parse_sparse_fields`).

        If `relationship` is ``True``, the resources in the query object
        will be serialized as linkage objects instead of resources
        objects.

        This method serializes the (correct page of) resources. As such,
        it may raise :exc:`SerializationException` if there is a problem
        serializing any of the resources.

        """
        if self.use_relationship_links():
            serialize = self.serialize_relationship
        else:
            serialize = self.serialize
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
            num_results = count(self.session, items)
            items = [serialize(instance, only=only) for instance in items]
            return Paginated(items, page_size=page_size,
                             num_results=num_results)
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
            # There will be no division-by-zero error here because we
            # have already checked that page size is not equal to zero
            # above.
            last = int(math.ceil(num_results / page_size))
            prev = page_number - 1 if page_number > 1 else None
            next_ = page_number + 1 if page_number < last else None
            offset = (page_number - 1) * page_size
            items = items.limit(page_size).offset(offset)
        items = [serialize(instance, only=only) for instance in items]
        return Paginated(items, num_results=num_results, first=first,
                         last=last, next_=next_, prev=prev,
                         page_size=page_size, page_number=page_number,
                         filters=filters, sort=sort, group_by=group_by)

    # TODO Document that subclasses should override these.
    def collection_processor_type(self, *args, **kw):
        raise NotImplemented

    def resource_processor_type(self, *args, **kw):
        raise NotImplemented

    # TODO Change the name of this method, since it is used for more
    # than just determining whether to use relationship links.
    def use_relationship_links(self):
        return False

    def _get_resource_helper(self, resource, primary_resource=None,
                             relation_name=None, related_resource=False):
        if self.use_relationship_links():
            serialize = self.serialize_relationship
        else:
            serialize = self.serialize
        # Determine the fields to include for each type of object.
        fields = parse_sparse_fields()

        # The resource to serialize may be `None`, if we are fetching a
        # to-one relation that has no value. In this case, the "data"
        # for the JSON API response is just `None`.
        if resource is None:
            data = None
        else:
            type_ = self.collection_name
            fields_for_resource = fields.get(type_)
            # Serialize the resource.
            try:
                data = serialize(resource, only=fields_for_resource)
            except SerializationException as exception:
                detail = 'Failed to serialize resource of type {0}'.format(type_)
                return error_response(400, cause=exception, detail=detail)
        # Prepare the dictionary that will contain the JSON API response.
        result = {'jsonapi': {'version': JSONAPI_VERSION}, 'meta': {},
                  'links': {}, 'data': data}
        # Determine the top-level links.
        is_relation = primary_resource is not None
        is_related_resource = is_relation and related_resource
        if is_related_resource:
            resource_id = primary_key_value(primary_resource)
            related_resource_id = primary_key_value(resource)
            # `self.model` should match `get_model(primary_resource)`
            self_link = url_for(self.model, resource_id, relation_name,
                                related_resource_id)
            result['links']['self'] = self_link
        elif is_relation:
            resource_id = primary_key_value(primary_resource)
            # `self.model` should match `get_model(primary_resource)`
            if self.use_relationship_links():
                self_link = url_for(self.model, resource_id, relation_name,
                                    relationship=True)
                related_link = url_for(self.model, resource_id, relation_name)
                result['links']['self'] = self_link
                result['links']['related'] = related_link
            else:
                self_link = url_for(self.model, resource_id, relation_name)
                result['links']['self'] = self_link
        else:
            result['links']['self'] = url_for(self.model)
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
                detail = 'Failed to serialize resource of type {0}'
                detail = detail.format(type_)
                return error_response(400, cause=exception, detail=detail)
            included.append(serialized)
        if included:
            result['included'] = included
        # This method could have been called on either a request to
        # fetch a single resource or a to-one relation.
        processor_type = self.resource_processor_type(is_relation=is_relation)
        processor_type = 'GET_{0}'.format(processor_type)
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
        except ComparisonToNull as exception:
            detail = str(exception)
            return error_response(400, cause=exception, detail=detail)
        except Exception as exception:
            detail = 'Unable to construct query'
            return error_response(400, cause=exception, detail=detail)

        # Determine the client's request for which fields to include for this
        # type of object.
        fields = parse_sparse_fields()
        fields_for_this = fields.get(self.collection_name)

        # Prepare the dictionary that will contain the JSON API response.
        result = {'links': {'self': url_for(self.model)},
                  'jsonapi': {'version': JSONAPI_VERSION},
                  'meta': {}}

        # Add the primary data (and any necessary links) to the JSON API
        # response object.
        #
        # If the result of the search is a SQLAlchemy query object, we need to
        # return a collection.
        if not single:
            try:
                paginated = self._paginated(search_items, filters=filters,
                                            sort=sort, group_by=group_by,
                                            only=fields_for_this)
            except SerializationException as exception:
                detail = 'Failed to deserialize object'
                return error_response(400, cause=exception, detail=detail)
            except PaginationError as exception:
                detail = exception.args[0]
                return error_response(400, cause=exception, detail=detail)
            # Wrap the resulting object or list of objects under a `data` key.
            result['data'] = paginated.items
            # Provide top-level links.
            result['links'].update(paginated.pagination_links)
            link_header = ','.join(paginated.header_links)
            headers = dict(Link=link_header)
            num_results = paginated.num_results
        # Otherwise, the result of the search should be a single resource.
        else:
            try:
                data = search_items.one()
            except NoResultFound as exception:
                detail = 'No result found'
                return error_response(404, cause=exception, detail=detail)
            except MultipleResultsFound as exception:
                detail = 'Multiple results found'
                return error_response(404, cause=exception, detail=detail)
            # Wrap the resulting resource under a `data` key.
            try:
                result['data'] = self.serialize(data, only=fields_for_this)
            except SerializationException as exception:
                detail = 'Failed to serialize resource'
                return error_response(400, cause=exception, detail=detail)
            primary_key = self.primary_key or primary_key_name(data)
            pk_value = result['data'][primary_key]
            # The URL at which a client can access the instance matching this
            # search query.
            url = '{0}/{1}'.format(request.base_url, pk_value)
            headers = dict(Location=url)
            num_results = 1

        # Determine the resources to include (in a compound document).
        if self.use_relationship_links():
            to_include = self.resources_to_include(resource)
        else:
            to_include = set(chain(self.resources_to_include(resource)
                                   for resource in search_items))
        # Include any requested resources in a compound document.
        included = []
        for included_resource in to_include:
            type_ = collection_name(get_model(included_resource))
            fields_for_this = fields.get(type_)
            try:
                serialized = self.serialize(included_resource,
                                            only=fields_for_this)
            except SerializationException as exception:
                detail = 'Failed to serialize resource of type {0}'
                detail = detail.format(type_)
                return error_response(400, cause=exception, detail=detail)
            included.append(serialized)
        if included:
            result['included'] = included

        # This method could have been called on either a request to
        # fetch a collection of resources or a to-many relation.
        processor_type = self.collection_processor_type(is_relation=is_relation)
        processor_type = 'GET_{0}'.format(processor_type)
        for postprocessor in self.postprocessors[processor_type]:
            postprocessor(result=result, filters=filters, sort=sort,
                          single=single)
        # Add the metadata to the JSON API response object.
        #
        # HACK Provide the headers directly in the result dictionary, so that
        # the :func:`jsonpify` function has access to them. See the note there
        # for more information. They don't really need to be under the ``meta``
        # key, that's just for semantic consistency.
        status = 200
        result['meta'][_HEADERS] = headers
        result['meta'][_STATUS] = status
        result['meta']['total'] = num_results
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


class API(APIBase):
    """Provides method-based dispatching for :http:method:`get`,
    :http:method:`post`, :http:method:`patch`, and :http:method:`delete`
    requests, for both collections of resources and individual resources.

    `session` and `model` are as described in the constructor of the
    superclass. In addition to those described below, this constructor also
    accepts all the keyword arguments of the constructor of the superclass.

    `page_size`, `max_page_size`, `serializer`, `deserializer`, `includes`, and
    `allow_client_generated_ids` are as described in
    :meth:`APIManager.create_api`.

    """

    def __init__(self, session, model, allow_client_generated_ids=False, *args,
                 **kw):
        super(API, self).__init__(session, model, *args, **kw)

        #: Whether this API allows the client to specify the ID for the
        #: resource to create; for more information, see
        #: :ref:`clientids`.
        self.allow_client_generated_ids = allow_client_generated_ids

        #: Whether any side-effect changes are made to the SQLAlchemy
        #: model on updates.
        self.changes_on_update = changes_on_update(self.model)

    def collection_processor_type(self, is_relation=False, **kw):
        return 'TO_MANY_RELATION' if is_relation else 'COLLECTION'

    def resource_processor_type(self, is_relation=False, **kw):
        return 'TO_ONE_RELATION' if is_relation else 'RESOURCE'

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
        for preprocessor in self.preprocessors['GET_RELATED_RESOURCE']:
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
        primary_resource = get_by(self.session, self.model, resource_id,
                                  self.primary_key)
        # Return an error if there is no resource with the specified ID.
        if primary_resource is None:
            detail = 'No instance with ID {0}'.format(resource_id)
            return error_response(404, detail=detail)
        # Return an error if the relation is a to-one relation.
        if not is_like_list(primary_resource, relation_name):
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
        resources = getattr(primary_resource, relation_name)
        # Check if one of the related resources has the specified ID. (JSON API
        # expects all IDs to be strings.)
        primary_keys = (primary_key_value(i) for i in resources)
        if not any(str(k) == related_resource_id for k in primary_keys):
            detail = 'No related resource with ID {0}'
            detail = detail.format(related_resource_id)
            return error_response(404, detail=detail)
        # Get the related resource by its ID.
        resource = get_by(self.session, related_model, related_resource_id)
        return self._get_resource_helper(resource,
                                         primary_resource=primary_resource,
                                         relation_name=relation_name,
                                         related_resource=True)

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
        try:
            filters, sort, group_by, single = self._collection_parameters()
        except (TypeError, ValueError, OverflowError) as exception:
            detail = 'Unable to decode filter objects as JSON list'
            return error_response(400, cause=exception, detail=detail)
        except SortKeyError as exception:
            detail = 'Each sort parameter must begin with "+" or "-"'
            return error_response(400, cause=exception, detail=detail)
        except SingleKeyError as exception:
            detail = 'Invalid format for filter[single] query parameter'
            return error_response(400, cause=exception, detail=detail)

        for preprocessor in self.preprocessors['GET_RELATION']:
            temp_result = preprocessor(resource_id=resource_id,
                                       relation_name=relation_name,
                                       filters=filters, sort=sort,
                                       group_by=group_by, single=single)
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
        primary_resource = get_by(self.session, self.model, resource_id, self.primary_key)
        if primary_resource is None:
            detail = 'No resource with ID {0}'.format(resource_id)
            return error_response(404, detail=detail)
        # Get the model of the specified relation.
        related_model = get_related_model(self.model, relation_name)
        if related_model is None:
            detail = 'No such relation: {0}'.format(related_model)
            return error_response(404, detail=detail)
        # Determine if this is a to-one or a to-many relation.
        if is_like_list(primary_resource, relation_name):
            return self._get_collection_helper(resource=primary_resource,
                                               relation_name=relation_name,
                                               filters=filters, sort=sort,
                                               group_by=group_by, single=single)
        else:
            resource = getattr(primary_resource, relation_name)
            return self._get_resource_helper(resource=resource,
                                             primary_resource=primary_resource,
                                             relation_name=relation_name)

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
        return self._get_resource_helper(resource)

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
            detail = 'Unable to decode filter objects as JSON list'
            return error_response(400, cause=exception, detail=detail)
        except SortKeyError as exception:
            detail = 'Each sort parameter must begin with "+" or "-"'
            return error_response(400, cause=exception, detail=detail)
        except SingleKeyError as exception:
            detail = 'Invalid format for filter[single] query parameter'
            return error_response(400, cause=exception, detail=detail)

        for preprocessor in self.preprocessors['GET_COLLECTION']:
            preprocessor(filters=filters, sort=sort, group_by=group_by,
                         single=single)

        return self._get_collection_helper(filters=filters, sort=sort,
                                           group_by=group_by, single=single)

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
        instance = get_by(self.session, self.model, resource_id,
                          self.primary_key)
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
            detail = 'Unable to decode data'
            return error_response(400, cause=exception, detail=detail)
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
            detail = 'Failed to deserialize object'
            return error_response(400, cause=exception, detail=detail)
        except self.validation_exceptions as exception:
            return self._handle_validation_exception(exception)
        fields = parse_sparse_fields()
        fields_for_this = fields.get(self.collection_name)
        # Get the dictionary representation of the new instance as it
        # appears in the database.
        try:
            result = self.serialize(instance, only=fields_for_this)
        except SerializationException as exception:
            detail = 'Failed to serialize object'
            return error_response(400, cause=exception, detail=detail)
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
        # Include any requested resources in a compound document.
        to_include = self.resources_to_include(instance)
        included = []
        for included_resource in to_include:
            type_ = collection_name(get_model(included_resource))
            fields_for_this = fields.get(type_)
            try:
                serialized = self.serialize(included_resource,
                                            only=fields_for_this)
            except SerializationException as exception:
                detail = 'Failed to serialize resource of type {0}'
                detail = detail.format(type_)
                return error_response(400, cause=exception, detail=detail)
            included.append(serialized)
        if included:
            result['included'] = included
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
        links = data.pop('relationships', {})
        for linkname, link in links.items():
            # TODO: The client is obligated by JSON API to provide linkage if
            # the `links` attribute exists, but we should probably error out
            # in a more constructive way if it's missing.
            linkage = link['data']
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
                return self._handle_validation_exception(exception)

        # Now consider only the attributes to update.
        data = data.pop('attributes', {})
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
            detail = 'Unable to decode data'
            return error_response(400, cause=exception, detail=detail)
        for preprocessor in self.preprocessors['PATCH_RESOURCE']:
            temp_result = preprocessor(instance_id=resource_id, data=data)
            # See the note under the preprocessor in the get() method.
            if temp_result is not None:
                resource_id = temp_result
        # Get the instance on which to set the new attributes.
        instance = get_by(self.session, self.model, resource_id,
                          self.primary_key)
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
        if self.changes_on_update:
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
    ``/people/1/relationships/articles``, and the requests and responses
    include **link objects**, as opposed to **resource objects**.

    `session` and `model` are as described in the constructor of the
    superclass. In addition to those described below, this constructor
    also accepts all the keyword arguments of the constructor of the
    superclass.

    `allow_delete_from_to_many_relationships` is as described in
    :meth:`APIManager.create_api`.

    """

    def __init__(self, session, model,
                 allow_delete_from_to_many_relationships=False, *args, **kw):
        super(RelationshipAPI, self).__init__(session, model, *args, **kw)
        self.allow_delete_from_to_many_relationships = \
            allow_delete_from_to_many_relationships

    def collection_processor_type(self, *args, **kw):
        return 'TO_MANY_RELATIONSHIP'

    def resource_processor_type(self, *args, **kw):
        return 'TO_ONE_RELATIONSHIP'

    def use_relationship_links(self):
        return True

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
        # get the instance of the "main" model whose ID is `resource_id`
        primary_resource = get_by(self.session, self.model, resource_id,
                          self.primary_key)
        if primary_resource is None:
            detail = 'No resource with ID {0}'.format(resource_id)
            return error_response(404, detail=detail)
        if is_like_list(primary_resource, relation_name):
            try:
                filters, sort, group_by, single = self._collection_parameters()
            except (TypeError, ValueError, OverflowError) as exception:
                detail = 'Unable to decode filter objects as JSON list'
                return error_response(400, cause=exception, detail=detail)
            except SortKeyError as exception:
                detail = 'Each sort parameter must begin with "+" or "-"'
                return error_response(400, cause=exception, detail=detail)
            except SingleKeyError as exception:
                detail = 'Invalid format for filter[single] query parameter'
                return error_response(400, cause=exception, detail=detail)
            return self._get_collection_helper(resource=primary_resource,
                                               relation_name=relation_name,
                                               filters=filters, sort=sort,
                                               group_by=group_by,
                                               single=single)
        resource = getattr(primary_resource, relation_name)
        return self._get_resource_helper(resource,
                                         primary_resource=primary_resource,
                                         relation_name=relation_name)

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
            detail = 'Unable to decode data'
            return error_response(400, cause=exception, detail=detail)
        for preprocessor in self.preprocessors['POST_RELATIONSHIP']:
            temp_result = preprocessor(instance_id=resource_id,
                                       relation_name=relation_name, data=data)
            # See the note under the preprocessor in the get() method.
            if temp_result is not None:
                resource_id, relation_name = temp_result
        instance = get_by(self.session, self.model, resource_id,
                          self.primary_key)
        # If no instance of the model exists with the specified instance ID,
        # return a 404 response.
        if instance is None:
            detail = 'No instance with ID {0} in model {1}'
            detail = detail.format(resource_id, self.model)
            return error_response(404, detail=detail)
        # If no such relation exists, return a 404.
        if not hasattr(instance, relation_name):
            detail = 'Model {0} has no relation named {1}'
            detail = detail.format(self.model, relation_name)
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
            detail = 'Unable to decode data'
            return error_response(400, cause=exception, detail=detail)
        for preprocessor in self.preprocessors['PATCH_RELATIONSHIP']:
            temp_result = preprocessor(instance_id=resource_id,
                                       relation_name=relation_name, data=data)
            # See the note under the preprocessor in the get() method.
            if temp_result is not None:
                resource_id, relation_name = temp_result
        instance = get_by(self.session, self.model, resource_id,
                          self.primary_key)
        # If no instance of the model exists with the specified instance ID,
        # return a 404 response.
        if instance is None:
            detail = 'No instance with ID {0} in model {1}'
            detail = detail.format(resource_id, self.model)
            return error_response(404, detail=detail)
        # If no such relation exists, return a 404.
        if not hasattr(instance, relation_name):
            detail = 'Model {0} has no relation named {1}'
            detail = detail.format(self.model, relation_name)
            return error_response(404, detail=detail)
        related_model = get_related_model(self.model, relation_name)
        # related_value = getattr(instance, relation_name)

        # Unwrap the data from the request.
        data = data.pop('data', {})
        # If the client sent a null value, we assume it wants to remove a
        # to-one relationship.
        if data is None:
            if is_like_list(instance, relation_name):
                detail = 'Cannot set null value on a to-many relationship'
                return error_response(400, detail=detail)
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
            detail = 'Unable to decode data'
            return error_response(400, cause=exception, detail=detail)
        was_deleted = False
        for preprocessor in self.preprocessors['DELETE_RELATIONSHIP']:
            temp_result = preprocessor(instance_id=resource_id,
                                       relation_name=relation_name)
            # See the note under the preprocessor in the get() method.
            if temp_result is not None:
                resource_id = temp_result
        instance = get_by(self.session, self.model, resource_id,
                          self.primary_key)
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
