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
    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
from __future__ import division

from collections import defaultdict
from functools import wraps
import math
import warnings

from flask import current_app
from flask import json
from flask import jsonify
from flask import request
from flask.views import MethodView
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import MultipleResultsFound
from sqlalchemy.orm.exc import NoResultFound

from .exceptions import json_abort
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
from .helpers import unicode_keys_to_strings
from .helpers import upper_keys
from .search import create_query
from .search import search


#: Format string for creating Link headers in paginated responses.
LINKTEMPLATE = '<%s?page=%s&results_per_page=%s>; rel="%s"'


class ProcessingException(Exception):
    """Raised when a preprocessor or postprocessor encounters a problem.

    This exception should be raised by functions supplied in the
    ``preprocessors`` and ``postprocessors`` keyword arguments to
    :class:`APIManager.create_api`. When this exception is raised, all
    preprocessing or postprocessing halts, so any processors appearing later in
    the list will not be invoked.

    `status_code` is the HTTP status code of the response supplied to the
    client in the case that this exception is raised. `message` is an error
    message describing the cause of this exception. This message will appear in
    the JSON object in the body of the response to the client.

    """
    def __init__(self, message='', status_code=400, *args, **kwargs):
        super(ProcessingException, self).__init__(*args, **kwargs)
        self.message = message
        self.status_code = status_code


def create_link_string(page, last_page, per_page):
    """Returns a string representing the value of the ``Link`` header.

    `page` is the number of the current page, `last_page` is the last page in
    the pagination, and `per_page` is the number of results per page.

    """
    linkstring = ''
    if page < last_page:
        next_page = page + 1
        linkstring = LINKTEMPLATE % (request.base_url, next_page,
                                     per_page, 'next') + ', '
    linkstring += LINKTEMPLATE % (request.base_url, last_page,
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
        except ProcessingException, exception:
            current_app.logger.exception(exception.message)
            status, message = exception.status_code, exception.message
            return jsonify_status_code(status_code=status, message=message)
    return decorator


def set_headers(response, headers):
    """Sets the specified headers on the specified response.

    `response` is a Flask response object, and `headers` is a dictionary of
    headers to set on the specified response. Any existing headers that
    conflict with `headers` will be overwritten.

    """
    for key, value in headers.iteritems():
        response.headers[key] = value


def jsonify_status_code(status_code, headers=None, *args, **kw):
    """Returns a jsonified response with the specified HTTP status code.

    If `headers` is specified, it must be a dictionary specifying headers to
    set before sending the JSONified response to the client. Headers on the
    response will be overwritten by headers specified in the `headers`
    dictionary.

    The remaining positional and keyword arguments are passed directly to the
    :func:`flask.jsonify` function which creates the response.

    """
    response = jsonify(*args, **kw)
    response.status_code = status_code
    if headers:
        set_headers(response, headers)
    return response


def jsonpify(*args, **kw):
    """Passes the specified arguments directly to :func:`jsonify_status_code`
    with a status code of 200, then wraps the response with the name of a
    JSON-P callback function specified as a query parameter called
    ``'callback'`` (or does nothing if no such callback function is specified
    in the request).

    If `headers` is specified, it must be a dictionary specifying headers to
    set before sending the JSONified response to the client. Headers on the
    response will be overwritten by headers specified in the `headers`
    dictionary.

    """
    response = jsonify(*args, **kw)
    callback = request.args.get('callback', False)
    if callback:
        content = '%s(%s)' % (callback, response.data)
        # Note that this is different from the mimetype used in Flask for JSON
        # responses; Flask uses 'application/json'.
        mimetype = 'application/javascript'
        response = current_app.response_class(content, mimetype=mimetype)
    if 'headers' in kw:
        set_headers(response, kw['headers'])
    return response


def _parse_includes(column_names):
    """Returns a pair, consisting of a list of column names to include on the
    left and a dictionary mapping relation name to a list containing the names
    of fields on the related model which should be included.

    `column_names` is either ``None`` or a list of strings. If it is ``None``,
    the returned pair will be ``(None, None)``.

    If the name of a relation appears as a key in the dictionary, then it will
    not appear in the list.

    """
    if column_names is None:
        return None, None
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

    `column_names` is either ``None`` or a list of strings. If it is ``None``,
    the returned pair will be ``(None, None)``.

    If the name of a relation appears in the list then it will not appear in
    the dictionary.

    """
    if column_names is None:
        return None, None
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
        try:
            data = json.loads(request.args.get('q')) or {}
        except (TypeError, ValueError, OverflowError), exception:
            current_app.logger.exception(exception.message)
            return jsonify_status_code(400, message='Unable to decode data')
        try:
            result = evaluate_functions(self.session, self.model,
                                        data.get('functions'))
            if not result:
                return jsonify_status_code(204)
            return jsonpify(result)
        except AttributeError, exception:
            current_app.logger.exception(exception.message)
            message = 'No such field "%s"' % exception.field
            return jsonify_status_code(400, message=message)
        except OperationalError, exception:
            current_app.logger.exception(exception.message)
            message = 'No such function "%s"' % exception.function
            return jsonify_status_code(400, message=message)


class API(ModelView):
    """Provides method-based dispatching for :http:method:`get`,
    :http:method:`post`, :http:method:`patch`, :http:method:`put`, and
    :http:method:`delete` requests, for both collections of models and
    individual models.

    """

    #: List of decorators applied to every method of this class.
    decorators = [catch_processing_exceptions]

    def __init__(self, session, model, exclude_columns=None,
                 include_columns=None, validation_exceptions=None,
                 results_per_page=10, max_results_per_page=100,
                 post_form_preprocessor=None, preprocessors=None,
                 postprocessors=None, *args, **kw):
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
        self.exclude_columns, self.exclude_relations = \
            _parse_excludes(exclude_columns)
        self.include_columns, self.include_relations = \
            _parse_includes(include_columns)
        self.validation_exceptions = tuple(validation_exceptions or ())
        self.results_per_page = results_per_page
        self.max_results_per_page = max_results_per_page
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
            except AttributeError, exception:
                current_app.logger.exception(exception.message)
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
                kw = unicode_keys_to_strings(dictionary)
                subinst = self.query(submodel).filter_by(**kw).first()
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
            if (isinstance(params[columnname], dict) and
                any(k in params[columnname] for k in ['add', 'remove'])):

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
        errors = self._extract_error_messages(exception) or \
            'Could not determine specific validation errors'
        return jsonify_status_code(400, validation_errors=errors)

    def _extract_error_messages(self, exception):
        """Tries to extract a dictionary mapping field name to validation error
        messages from `exception`, which is a validation exception as provided
        in the ``validation_exceptions`` keyword argument in the constructor of
        this class.

        Since the type of the exception is provided by the user in the
        constructor of this class, we don't know for sure where the validation
        error messages live inside `exception`. Therefore this method simply
        attempts to access a few likely attributes and returns the first one it
        finds (or ``None`` if no error messages dictionary can be extracted).

        """
        # 'errors' comes from sqlalchemy_elixir_validations
        if hasattr(exception, 'errors'):
            return exception.errors
        # 'message' comes from savalidation
        if hasattr(exception, 'message'):
            # TODO this works only if there is one validation error
            try:
                left, right = exception.message.rsplit(':', 1)
                left_bracket = left.rindex('[')
                right_bracket = right.rindex(']')
            except ValueError, exception:
                current_app.logger.exception(exception.message)
                # could not parse the string; we're not trying too hard here...
                return None
            msg = right[:right_bracket].strip(' "')
            fieldname = left[left_bracket + 1:].strip()
            return {fieldname: msg}
        return None

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

        `instances` is a list of model instances.

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
        num_results = len(instances)
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
                           include_relations=self.include_relations)
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
                       include_relations=self.include_relations)

    def _instid_to_dict(self, instid):
        """Returns the dictionary representation of the instance specified by
        `instid`.

        If no such instance of the model exists, this method aborts with a
        :http:statuscode:`404`.

        """
        inst = get_by(self.session, self.model, instid)
        if inst is None:
            json_abort(404)
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
        except (TypeError, ValueError, OverflowError), exception:
            current_app.logger.exception(exception.message)
            return jsonify_status_code(400, message='Unable to decode data')

        for preprocessor in self.preprocessors['GET_MANY']:
            preprocessor(search_params=search_params)

        # perform a filtered search
        try:
            result = search(self.session, self.model, search_params)
        except NoResultFound:
            return jsonify_status_code(400, message='No result found')
        except MultipleResultsFound:
            return jsonify_status_code(400, message='Multiple results found')
        except Exception, exception:
            current_app.logger.exception(exception.message)
            return jsonify_status_code(400,
                                       message='Unable to construct query')

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
        if isinstance(result, list):
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
            primary_key = primary_key_name(result)
            result = to_dict(result, deep, exclude=self.exclude_columns,
                             exclude_relations=self.exclude_relations,
                             include=self.include_columns,
                             include_relations=self.include_relations)
            # The URL at which a client can access the instance matching this
            # search query.
            url = '%s/%s' % (request.base_url, result[primary_key])
            headers = dict(Location=url)

        for postprocessor in self.postprocessors['GET_MANY']:
            postprocessor(result=result)

        return jsonpify(result, headers=headers)

    def get(self, instid, relationname):
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
            preprocessor(instance_id=instid)
        # get the instance of the "main" model whose ID is instid
        instance = get_by(self.session, self.model, instid)
        if instance is None:
            json_abort(404)
        # If no relation is requested, just return the instance. Otherwise,
        # get the value of the relation specified by `relationname`.
        if relationname is None:
            result = self._inst_to_dict(instance)
        else:
            related_value = getattr(instance, relationname)
            # create a placeholder for the relations of the returned models
            related_model = get_related_model(self.model, relationname)
            relations = frozenset(get_relations(related_model))
            deep = dict((r, {}) for r in relations)
            # for security purposes, don't transmit list as top-level JSON
            if is_like_list(instance, relationname):
                result = self._paginated(list(related_value), deep)
            else:
                result = to_dict(related_value, deep)
        for postprocessor in self.postprocessors['GET_SINGLE']:
            postprocessor(result=result)
        return jsonpify(result)

    def delete(self, instid, relationname):
        """Removes the specified instance of the model with the specified name
        from the database.

        Since :http:method:`delete` is an idempotent method according to the
        :rfc:`2616`, this method responds with :http:status:`204` regardless of
        whether an object was deleted.

        This function ignores the `relationname` keyword argument.

        .. versionadded:: 0.10
           Added the `relationname` keyword argument.

        """
        is_deleted = False
        for preprocessor in self.preprocessors['DELETE']:
            preprocessor(instance_id=instid)
        inst = get_by(self.session, self.model, instid)
        if inst is not None:
            self.session.delete(inst)
            self.session.commit()
            is_deleted = True
        for postprocessor in self.postprocessors['DELETE']:
            postprocessor(is_deleted=is_deleted)
        return jsonify_status_code(204)

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
        # try to read the parameters for the model from the body of the request
        try:
            params = json.loads(request.data)
        except (TypeError, ValueError, OverflowError), exception:
            current_app.logger.exception(exception.message)
            return jsonify_status_code(400, message='Unable to decode data')

        # apply any preprocessors to the POST arguments
        for preprocessor in self.preprocessors['POST']:
            preprocessor(data=params)

        # Check for any request parameter naming a column which does not exist
        # on the current model.
        for field in params:
            if not has_field(self.model, field):
                msg = "Model does not have field '%s'" % field
                return jsonify_status_code(400, message=msg)

        # Getting the list of relations that will be added later
        cols = get_columns(self.model)
        relations = get_relations(self.model)

        # Looking for what we're going to set on the model right now
        colkeys = cols.keys()
        paramkeys = params.keys()
        props = set(colkeys).intersection(paramkeys).difference(relations)

        # Special case: if there are any dates, convert the string form of the
        # date into an instance of the Python ``datetime`` object.
        params = strings_to_dates(self.model, params)

        try:
            # Instantiate the model with the parameters.
            modelargs = dict([(i, params[i]) for i in props])
            # HACK Python 2.5 requires __init__() keywords to be strings.
            instance = self.model(**unicode_keys_to_strings(modelargs))

            # Handling relations, a single level is allowed
            for col in set(relations).intersection(paramkeys):
                submodel = get_related_model(self.model, col)

                if type(params[col]) == list:
                    # model has several related objects
                    for subparams in params[col]:
                        subinst = get_or_create(self.session, submodel,
                                                subparams)
                        getattr(instance, col).append(subinst)
                else:
                    # model has single related object
                    subinst = get_or_create(self.session, submodel,
                                            params[col])
                    setattr(instance, col, subinst)

            # add the created model to the session
            self.session.add(instance)
            self.session.commit()
            result = self._inst_to_dict(instance)

            for postprocessor in self.postprocessors['POST']:
                postprocessor(result=result)

            # The URL at which a client can access the newly created instance
            # of the model.
            primary_key = primary_key_name(instance)
            url = '%s/%s' % (request.base_url, result[primary_key])
            # Provide that URL in the Location header in the response.
            headers = dict(Location=url)
            return jsonify_status_code(201, headers=headers, **result)
        except self.validation_exceptions, exception:
            return self._handle_validation_exception(exception)
        except IntegrityError, exception:
            current_app.logger.exception(exception.message)
            return jsonify_status_code(400, message=exception.message)

    def patch(self, instid, relationname):
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

        This function ignores the `relationname` keyword argument.

        .. versionadded:: 0.10
           Added the `relationname` keyword argument.

        """
        # try to load the fields/values to update from the body of the request
        try:
            data = json.loads(request.data)
        except (TypeError, ValueError, OverflowError), exception:
            # this also happens when request.data is empty
            current_app.logger.exception(exception.message)
            return jsonify_status_code(400, message='Unable to decode data')
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
                preprocessor(instance_id=instid, data=data)

        # Check for any request parameter naming a column which does not exist
        # on the current model.
        for field in data:
            if not has_field(self.model, field):
                msg = "Model does not have field '%s'" % field
                return jsonify_status_code(400, message=msg)

        if patchmany:
            try:
                # create a SQLALchemy Query from the query parameter `q`
                query = create_query(self.session, self.model, search_params)
            except Exception, exception:
                current_app.logger.exception(exception.message)
                return jsonify_status_code(400,
                                           message='Unable to construct query')
        else:
            # create a SQLAlchemy Query which has exactly the specified row
            query = query_by_primary_key(self.session, self.model, instid)
            if query.count() == 0:
                json_abort(404)
            assert query.count() == 1, 'Multiple rows with same ID'

        relations = self._update_relations(query, data)
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
                    for field, value in data.iteritems():
                        setattr(item, field, value)
                    num_modified += 1
            self.session.commit()
        except self.validation_exceptions, exception:
            current_app.logger.exception(exception.message)
            return self._handle_validation_exception(exception)
        except IntegrityError, exception:
            current_app.logger.exception(exception.message)
            return jsonify_status_code(400, message=exception.message)

        # Perform any necessary postprocessing.
        if patchmany:
            result = dict(num_modified=num_modified)
            for postprocessor in self.postprocessors['PATCH_MANY']:
                postprocessor(query=query, result=result)
        else:
            result = self._instid_to_dict(instid)
            for postprocessor in self.postprocessors['PATCH_SINGLE']:
                postprocessor(result=result)

        return jsonify(result)

    def put(self, instid, relationname):
        """Alias for :meth:`patch`."""
        return self.patch(instid, relationname)
