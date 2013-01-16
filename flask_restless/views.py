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
import datetime
import math

from dateutil.parser import parse as parse_datetime
from flask import abort
from flask import json
from flask import jsonify
from flask import request
from flask.views import MethodView
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import class_mapper
from sqlalchemy.orm import ColumnProperty
from sqlalchemy.orm import object_mapper
from sqlalchemy.orm import RelationshipProperty
from sqlalchemy.orm.exc import MultipleResultsFound
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.properties import RelationshipProperty as RelProperty
from sqlalchemy.orm.query import Query
from sqlalchemy.sql import func

from .helpers import partition
from .helpers import unicode_keys_to_strings
from .search import create_query
from .search import search


def jsonify_status_code(status_code, *args, **kw):
    """Returns a jsonified response with the specified HTTP status code.

    The positional and keyword arguments are passed directly to the
    :func:`flask.jsonify` function which creates the response.

    """
    response = jsonify(*args, **kw)
    response.status_code = status_code
    return response


def _is_date_field(model, fieldname):
    """Returns ``True`` if and only if the field of `model` with the specified
    name corresponds to either a :class:`datetime.date` object or a
    :class:`datetime.datetime` object.

    """
    prop = getattr(model, fieldname).property
    if isinstance(prop, RelationshipProperty):
        return False
    fieldtype = prop.columns[0].type
    return isinstance(fieldtype, Date) or isinstance(fieldtype, DateTime)


def _get_or_create(session, model, **kwargs):
    """Returns the first instance of the specified model filtered by the
    keyword arguments, or creates a new instance of the model and returns that.

    This function returns a two-tuple in which the first element is the created
    or retrieved instance and the second is a boolean value which is ``True``
    if and only if an instance was created.

    The idea for this function is based on Django's ``Model.get_or_create()``
    method.

    `session` is the session in which all database transactions are made (this
    should be :attr:`flask.ext.sqlalchemy.SQLAlchemy.session`).

    `model` is the SQLAlchemy model to get or create (this should be a subclass
    of :class:`~flask.ext.restless.model.Entity`).

    `kwargs` are the keyword arguments which will be passed to the
    :func:`sqlalchemy.orm.query.Query.filter_by` function.

    """
    instance = session.query(model).filter_by(**kwargs).first()
    if instance:
        return instance, False
    instance = model(**kwargs)
    session.add(instance)
    session.commit()
    return instance, True


def _get_columns(model):
    """Returns a dictionary-like object containing all the columns of the
    specified `model` class.

    """
    return model._sa_class_manager


def _get_related_model(model, relationname):
    """Gets the class of the model to which `model` is related by the attribute
    whose name is `relationname`.

    """
    return _get_columns(model)[relationname].property.mapper.class_


def _get_relations(model):
    """Returns a list of relation names of `model` (as a list of strings)."""
    cols = _get_columns(model)
    return [k for k in cols if isinstance(cols[k].property, RelProperty)]


def _primary_key_name(model_or_instance):
    """Returns the name of the primary key of the specified model or instance
    of a model, as a string.

    If `model_or_instance` specifies multiple primary keys and ``'id'`` is one
    of them, ``'id'`` is returned. If `model_or_instance` specifies multiple
    primary keys and ``'id'`` is not one of them, only the name of the first
    one in the list of primary keys is returned.

    """
    its_a_model = isinstance(model_or_instance, type)
    mapper = class_mapper if its_a_model else object_mapper
    mapped = mapper(model_or_instance)
    primary_key_names = [key.name for key in mapped.primary_key]
    return 'id' if 'id' in primary_key_names else primary_key_names[0]


# This code was adapted from :meth:`elixir.entity.Entity.to_dict` and
# http://stackoverflow.com/q/1958219/108197.
def _to_dict(instance, deep=None, exclude=None, include=None,
             exclude_relations=None, include_relations=None):
    """Returns a dictionary representing the fields of the specified `instance`
    of a SQLAlchemy model.

    `deep` is a dictionary containing a mapping from a relation name (for a
    relation of `instance`) to either a list or a dictionary. This is a
    recursive structure which represents the `deep` argument when calling
    :func:`!_to_dict` on related instances. When an empty list is encountered,
    :func:`!_to_dict` returns a list of the string representations of the
    related instances.

    If either `include` or `exclude` is not ``None``, exactly one of them must
    be specified. If both are not ``None``, then this function will raise a
    :exc:`ValueError`. `exclude` must be a list of strings specifying the
    columns which will *not* be present in the returned dictionary
    representation of the object (in other words, it is a
    blacklist). Similarly, `include` specifies the only columns which will be
    present in the returned dictionary (in other words, it is a whitelist).

    .. note::

       If `include` is an iterable of length zero (like the empty tuple or the
       empty list), then the returned dictionary will be empty. If `include` is
       ``None``, then the returned dictionary will include all columns not
       excluded by `exclude`.

    `include_relations` is a dictionary mapping strings representing relation
    fields on the specified `instance` to a list of strings representing the
    names of fields on the related model which should be included in the
    returned dictionary; `exclude_relations` is similar.

    """
    if (exclude is not None or exclude_relations is not None) and \
            (include is not None or include_relations is not None):
        raise ValueError('Cannot specify both include and exclude.')
    # create the dictionary mapping column name to value
    columns = (p.key for p in object_mapper(instance).iterate_properties
               if isinstance(p, ColumnProperty))
    # filter the columns based on exclude and include values
    if exclude is not None:
        columns = (c for c in columns if c not in exclude)
    elif include is not None:
        columns = (c for c in columns if c in include)
    result = dict((col, getattr(instance, col)) for col in columns)
    # Convert datetime and date objects to ISO 8601 format.
    #
    # TODO We can get rid of this when issue #33 is resolved.
    for key, value in result.items():
        if isinstance(value, datetime.date):
            result[key] = value.isoformat()
    # recursively call _to_dict on each of the `deep` relations
    deep = deep or {}
    for relation, rdeep in deep.iteritems():
        # Get the related value so we can see if it is None, a list, a query
        # (as specified by a dynamic relationship loader), or an actual
        # instance of a model.
        relatedvalue = getattr(instance, relation)
        if relatedvalue is None:
            result[relation] = None
            continue
        # Determine the included and excluded fields for the related model.
        newexclude = None
        newinclude = None
        if exclude_relations is not None and relation in exclude_relations:
            newexclude = exclude_relations[relation]
        elif (include_relations is not None and
              relation in include_relations):
            newinclude = include_relations[relation]
        # Do some black magic on SQLAlchemy to decide if the related instance
        # should be rendered as a list or as a single object.
        uselist = instance._sa_class_manager[relation].property.uselist
        if uselist:
            result[relation] = [_to_dict(inst, rdeep, exclude=newexclude,
                                         include=newinclude)
                                for inst in relatedvalue]
            continue
        # If the related value is dynamically loaded, resolve the query to get
        # the single instance.
        if isinstance(relatedvalue, Query):
            relatedvalue = relatedvalue.one()
        result[relation] = _to_dict(relatedvalue, rdeep, exclude=newexclude,
                                    include=newinclude)
    return result


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


def _evaluate_functions(session, model, functions):
    """Executes each of the SQLAlchemy functions specified in ``functions``, a
    list of dictionaries of the form described below, on the given model and
    returns a dictionary mapping function name (slightly modified, see below)
    to result of evaluation of that function.

    `session` is the SQLAlchemy session in which all database transactions will
    be performed.

    `model` is the :class:`flask.ext.restless.Entity` object on which the
    specified functions will be evaluated.

    ``functions`` is a list of dictionaries of the form::

        {'name': 'avg', 'field': 'amount'}

    For example, if you want the sum and the average of the field named
    "amount"::

        >>> # assume instances of Person exist in the database...
        >>> f1 = dict(name='sum', field='amount')
        >>> f2 = dict(name='avg', field='amount')
        >>> evaluate_functions(Person, [f1, f2])
        {'avg__amount': 456, 'sum__amount': 123}

    The return value is a dictionary mapping ``'<funcname>__<fieldname>'`` to
    the result of evaluating that function on that field. If `model` is
    ``None`` or `functions` is empty, this function returns the empty
    dictionary.

    If a field does not exist on a given model, :exc:`AttributeError` is
    raised. If a function does not exist,
    :exc:`sqlalchemy.exc.OperationalError` is raised. The former exception will
    have a ``field`` attribute which is the name of the field which does not
    exist. The latter exception will have a ``function`` attribute which is the
    name of the function with does not exist.

    """
    if not model or not functions:
        return {}
    processed = []
    funcnames = []
    for function in functions:
        funcname, fieldname = function['name'], function['field']
        # We retrieve the function by name from the SQLAlchemy ``func``
        # module and the field by name from the model class.
        #
        # If the specified field doesn't exist, this raises AttributeError.
        funcobj = getattr(func, funcname)
        try:
            field = getattr(model, fieldname)
        except AttributeError, exception:
            exception.field = fieldname
            raise exception
        # Time to store things to be executed. The processed list stores
        # functions that will be executed in the database and funcnames
        # contains names of the entries that will be returned to the
        # caller.
        funcnames.append('%s__%s' % (funcname, fieldname))
        processed.append(funcobj(field))
    # Evaluate all the functions at once and get an iterable of results.
    #
    # If any of the functions
    try:
        evaluated = session.query(*processed).one()
    except OperationalError, exception:
        # HACK original error message is of the form:
        #
        #    '(OperationalError) no such function: bogusfuncname'
        original_error_msg = exception.args[0]
        bad_function = original_error_msg[37:]
        exception.function = bad_function
        raise exception
    return dict(zip(funcnames, evaluated))


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
        the_model = model or self.model
        if hasattr(the_model, 'query'):
            return the_model.query
        else:
            return self.session.query(the_model)


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
        except (TypeError, ValueError, OverflowError):
            return jsonify_status_code(400, message='Unable to decode data')
        try:
            result = _evaluate_functions(self.session, self.model,
                                         data.get('functions'))
            if not result:
                return jsonify_status_code(204)
            return jsonify(result)
        except AttributeError, exception:
            message = 'No such field "%s"' % exception.field
            return jsonify_status_code(400, message=message)
        except OperationalError, exception:
            message = 'No such function "%s"' % exception.function
            return jsonify_status_code(400, message=message)


class API(ModelView):
    """Provides method-based dispatching for :http:method:`get`,
    :http:method:`post`, :http:method:`patch`, :http:method:`put`, and
    :http:method:`delete` requests, for both collections of models and
    individual models.

    """

    def __init__(self, session, model, authentication_required_for=None,
                 authentication_function=None, exclude_columns=None,
                 include_columns=None, validation_exceptions=None,
                 results_per_page=10, max_results_per_page=100,
                 post_form_preprocessor=None, *args, **kw):
        """Instantiates this view with the specified attributes.

        `session` is the SQLAlchemy session in which all database transactions
        will be performed.

        `model` is the :class:`flask_restless.Entity` class of the database
        model for which this instance of the class is an API. This model should
        live in `database`.

        `authentication_required_for` is a list of HTTP method names (for
        example, ``['POST', 'PATCH']``) for which authentication must be
        required before clients can successfully make requests. If this keyword
        argument is specified, `authentication_function` must also be
        specified.

        `authentication_function` is a function which accepts no arguments and
        returns ``True`` if and only if a client is authorized to make a
        request on an endpoint.

        Pre-condition (callers must satisfy): if `authentication_required_for`
        is specified, so must `authentication_function`.

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

        `post_form_preprocessor` is a callback function which takes
        POST input parameters loaded from JSON and enhances them with other
        key/value pairs. The example use of this is when your ``model``
        requires to store user identity and for security reasons the identity
        is not read from the post parameters (where malicious user can tamper
        with them) but from the session.

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
        self.authentication_required_for = authentication_required_for or ()
        self.authentication_function = authentication_function
        # convert HTTP method names to uppercase
        self.authentication_required_for = \
            frozenset([m.upper() for m in self.authentication_required_for])
        self.exclude_columns, self.exclude_relations = \
            _parse_excludes(exclude_columns)
        self.include_columns, self.include_relations = \
            _parse_includes(include_columns)
        self.validation_exceptions = tuple(validation_exceptions or ())
        self.results_per_page = results_per_page
        self.max_results_per_page = max_results_per_page
        self.post_form_preprocessor = post_form_preprocessor

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
        added. Otherwise, the
        :classmethod:`~flask.ext.restless.model.get_or_create` class method
        will be used to get or create a model to add.

        """
        submodel = _get_related_model(self.model, relationname)
        if isinstance(toadd, dict):
            toadd = [toadd]
        for dictionary in toadd or []:
            if 'id' in dictionary:
                subinst = self._get_by(dictionary['id'], submodel)
            else:
                kw = unicode_keys_to_strings(dictionary)
                subinst = _get_or_create(self.session, submodel, **kw)[0]
            try:
                for instance in query:
                    getattr(instance, relationname).append(subinst)
            except AttributeError:
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
        submodel = _get_related_model(self.model, relationname)
        for dictionary in toremove or []:
            remove = dictionary.pop('__delete__', False)
            if 'id' in dictionary:
                subinst = self._get_by(dictionary['id'], submodel)
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

        `toset` is a list of dictionaries, each representing the attributes of
        an existing or new related model to set. If a dictionary contains the
        key ``'id'``, that instance of the related model will be added.
        Otherwise, the :classmethod:`~flask.ext.restless.model.get_or_create`
        class method will be used to get or create a model to set.

        """
        submodel = _get_related_model(self.model, relationname)
        subinst_list = []
        for dictionary in toset or []:
            if 'id' in dictionary:
                subinst = self._get_by(dictionary['id'], submodel)
            else:
                kw = unicode_keys_to_strings(dictionary)
                subinst = _get_or_create(self.session, submodel, **kw)[0]
            subinst_list.append(subinst)
        for instance in query:
            setattr(instance, relationname, subinst_list)

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
        relations = _get_relations(self.model)
        tochange = frozenset(relations) & frozenset(params)
        for columnname in tochange:
            if isinstance(params[columnname], list):
                toset = params[columnname]
                self._set_on_relation(query, columnname, toset=toset)
            else:
                toadd = params[columnname].get('add', [])
                toremove = params[columnname].get('remove', [])
                self._add_to_relation(query, columnname, toadd=toadd)
                self._remove_from_relation(query, columnname,
                                           toremove=toremove)
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
            except ValueError:
                # could not parse the string; we're not trying too hard here...
                return None
            msg = right[:right_bracket].strip(' "')
            fieldname = left[left_bracket + 1:].strip()
            return {fieldname: msg}
        return None

    def _strings_to_dates(self, dictionary):
        """Returns a new dictionary with all the mappings of `dictionary` but
        with date strings mapped to :class:`datetime.datetime` objects.

        The keys of `dictionary` are names of fields in the model specified in
        the constructor of this class. The values are values to set on these
        fields. If a field name corresponds to a field in the model which is a
        :class:`sqlalchemy.types.Date` or :class:`sqlalchemy.types.DateTime`,
        then the returned dictionary will have the corresponding
        :class:`datetime.datetime` Python object as the value of that mapping
        in place of the string.

        This function outputs a new dictionary; it does not modify the
        argument.

        """
        result = {}
        for fieldname, value in dictionary.iteritems():
            if _is_date_field(self.model, fieldname) and value is not None:
                result[fieldname] = parse_datetime(value)
            else:
                result[fieldname] = value
        return result

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
             "single": "True",
             "order_by": [{"field": "age", "direction": "asc"}],
             "limit": 2,
             "offset": 1,
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
            data = json.loads(request.args.get('q', '{}'))
        except (TypeError, ValueError, OverflowError):
            return jsonify_status_code(400, message='Unable to decode data')

        # perform a filtered search
        try:
            result = search(self.session, self.model, data)
        except NoResultFound:
            return jsonify(message='No result found')
        except MultipleResultsFound:
            return jsonify(message='Multiple results found')
        except:
            return jsonify_status_code(400,
                                       message='Unable to construct query')

        # create a placeholder for the relations of the returned models
        relations = frozenset(_get_relations(self.model))
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
            return self._paginated(result, deep)
        else:
            result = _to_dict(result, deep, exclude=self.exclude_columns,
                              exclude_relations=self.exclude_relations,
                              include=self.include_columns,
                              include_relations=self.include_relations)
            return jsonify(result)

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
        directly to :func:`_to_dict`.

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
        objects = [_to_dict(x, deep, exclude=self.exclude_columns,
                            exclude_relations=self.exclude_relations,
                            include=self.include_columns,
                            include_relations=self.include_relations)
                   for x in instances[start:end]]
        return jsonify(page=page_num, objects=objects, total_pages=total_pages,
                       num_results=num_results)

    def _check_authentication(self):
        """If the specified HTTP method requires authentication (see the
        constructor), this function aborts with :http:statuscode:`401` unless a
        current user is authorized with respect to the authentication function
        specified in the constructor of this class.

        """
        if (request.method in self.authentication_required_for
            and not self.authentication_function()):
            abort(401)

    def _query_by_primary_key(self, primary_key_value, model=None):
        """Returns a SQLAlchemy query object containing the result of querying
        `model` (or ``self.model`` if not specified) for instances whose
        primary key has the value `primary_key_value`.

        Presumably, the returned query should have at most one element.

        """
        the_model = model or self.model
        # force unicode primary key name to string; see unicode_keys_to_strings
        pk_name = str(_primary_key_name(the_model))
        return self.query(the_model).filter_by(**{pk_name: primary_key_value})

    def _get_by(self, primary_key_value, model=None):
        """Returns the single instance of `model` (or ``self.model`` if not
        specified) whose primary key has the value `primary_key_value`, or
        ``None`` if no such instance exists.

        """
        return self._query_by_primary_key(primary_key_value, model).first()

    def get(self, instid):
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
        self._check_authentication()
        if instid is None:
            return self._search()
        inst = self._get_by(instid)
        if inst is None:
            abort(404)
        # create a placeholder for the relations of the returned models
        relations = frozenset(_get_relations(self.model))
        # do not follow relations that will not be included in the response
        if self.include_columns is not None:
            cols = frozenset(self.include_columns)
            rels = frozenset(self.include_relations)
            relations &= (cols | rels)
        elif self.exclude_columns is not None:
            relations -= frozenset(self.exclude_columns)
        deep = dict((r, {}) for r in relations)
        result = _to_dict(inst, deep, exclude=self.exclude_columns,
                          exclude_relations=self.exclude_relations,
                          include=self.include_columns,
                          include_relations=self.include_relations)
        return jsonify(result)

    def delete(self, instid):
        """Removes the specified instance of the model with the specified name
        from the database.

        Since :http:method:`delete` is an idempotent method according to the
        :rfc:`2616`, this method responds with :http:status:`204` regardless of
        whether an object was deleted.

        """
        self._check_authentication()
        inst = self._get_by(instid)
        if inst is not None:
            self.session.delete(inst)
            self.session.commit()
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
        self._check_authentication()
        # try to read the parameters for the model from the body of the request
        try:
            params = json.loads(request.data)
        except (TypeError, ValueError, OverflowError):
            return jsonify_status_code(400, message='Unable to decode data')
        # Check for any request parameter naming a column which does not exist
        # on the current model.
        for field in params:
            if not hasattr(self.model, field):
                msg = "Model does not have field '%s'" % field
                return jsonify_status_code(400, message=msg)
        # If post_form_preprocessor is specified, call it
        if self.post_form_preprocessor:
            params = self.post_form_preprocessor(params)

        # Getting the list of relations that will be added later
        cols = _get_columns(self.model)
        relations = _get_relations(self.model)

        # Looking for what we're going to set on the model right now
        colkeys = cols.keys()
        paramkeys = params.keys()
        props = set(colkeys).intersection(paramkeys).difference(relations)

        # Special case: if there are any dates, convert the string form of the
        # date into an instance of the Python ``datetime`` object.
        params = self._strings_to_dates(params)

        try:
            # Instantiate the model with the parameters.
            modelargs = dict([(i, params[i]) for i in props])
            # HACK Python 2.5 requires __init__() keywords to be strings.
            instance = self.model(**unicode_keys_to_strings(modelargs))

            # Handling relations, a single level is allowed
            for col in set(relations).intersection(paramkeys):
                submodel = cols[col].property.mapper.class_

                if type(params[col]) == list:
                    # model has several related objects
                    for subparams in params[col]:
                        kw = unicode_keys_to_strings(subparams)
                        subinst = _get_or_create(self.session, submodel,
                                                 **kw)[0]
                        getattr(instance, col).append(subinst)
                else:
                    # model has single related object
                    kw = unicode_keys_to_strings(params[col])
                    subinst = _get_or_create(self.session, submodel, **kw)[0]
                    setattr(instance, col, subinst)

            # add the created model to the session
            self.session.add(instance)
            self.session.commit()

            pk_name = str(_primary_key_name(instance))
            pk_value = getattr(instance, pk_name)
            return jsonify_status_code(201, **{pk_name: pk_value})
        except self.validation_exceptions, exception:
            return self._handle_validation_exception(exception)

    def patch(self, instid):
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

        """
        self._check_authentication()
        # try to load the fields/values to update from the body of the request
        try:
            data = json.loads(request.data)
        except (TypeError, ValueError, OverflowError):
            # this also happens when request.data is empty
            return jsonify_status_code(400, message='Unable to decode data')
        # Check for any request parameter naming a column which does not exist
        # on the current model.
        for field in data:
            if not hasattr(self.model, field):
                msg = "Model does not have field '%s'" % field
                return jsonify_status_code(400, message=msg)
        # Check if the request is to patch many instances of the current model.
        patchmany = instid is None
        if patchmany:
            try:
                # create a SQLALchemy Query from the query parameter `q`
                query = create_query(self.session, self.model, data)
            except:
                return jsonify_status_code(400,
                                           message='Unable to construct query')
        else:
            # create a SQLAlchemy Query which has exactly the specified row
            query = self._query_by_primary_key(instid)
            if query.count() == 0:
                abort(404)
            assert query.count() == 1, 'Multiple rows with same ID'

        relations = self._update_relations(query, data)
        field_list = frozenset(data) ^ relations
        params = dict((field, data[field]) for field in field_list)

        # Special case: if there are any dates, convert the string form of the
        # date into an instance of the Python ``datetime`` object.
        params = self._strings_to_dates(params)

        try:
            # Let's update all instances present in the query
            num_modified = 0
            if params:
                for item in query.all():
                    for param, value in params.iteritems():
                        setattr(item, param, value)
                    num_modified += 1
            self.session.commit()
        except self.validation_exceptions, exception:
            return self._handle_validation_exception(exception)

        if patchmany:
            return jsonify(num_modified=num_modified)
        else:
            return self.get(instid)

    def put(self, instid):
        """Alias for :meth:`patch`."""
        return self.patch(instid)
