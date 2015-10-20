"""
    flask.ext.restless.helpers
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    Helper functions for Flask-Restless.

    :copyright: 2012, 2013, 2014, 2015 Jeffrey Finkelstein
                <jeffrey.finkelstein@gmail.com> and contributors.
    :license: GNU AGPLv3+ or BSD

"""
import datetime
import inspect

from dateutil.parser import parse as parse_datetime
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Interval
from sqlalchemy import Time
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.associationproxy import AssociationProxy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import ColumnProperty
from sqlalchemy.orm import class_mapper
from sqlalchemy.orm import RelationshipProperty as RelProperty
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.orm.attributes import QueryableAttribute
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import ColumnElement
from sqlalchemy.inspection import inspect as sqlalchemy_inspect
from werkzeug.urls import url_quote_plus

#: Names of attributes which should definitely not be considered relations when
#: dynamically computing a list of relations of a SQLAlchemy model.
RELATION_BLACKLIST = ('query', 'query_class', '_sa_class_manager',
                      '_decl_class_registry')

#: Types which should be considered columns of a model when iterating over all
#: attributes of a model class.
COLUMN_TYPES = (InstrumentedAttribute, hybrid_property)

#: Strings which, when received by the server as the value of a date or time
#: field, indicate that the server should use the current time when setting the
#: value of the field.
CURRENT_TIME_MARKERS = ('CURRENT_TIMESTAMP', 'CURRENT_DATE', 'LOCALTIMESTAMP')


def session_query(session, model):
    """Returns a SQLAlchemy query object for the specified `model`.

    If `model` has a ``query`` attribute already, ``model.query`` will be
    returned. If the ``query`` attribute is callable ``model.query()`` will be
    returned instead.

    If `model` has no such attribute, a query based on `session` will be
    created and returned.

    """
    if hasattr(model, 'query'):
        if callable(model.query):
            query = model.query()
        else:
            query = model.query
        if hasattr(query, 'filter'):
            return query
    return session.query(model)


def upper_keys(d):
    """Returns a new dictionary with the keys of `d` converted to upper case
    and the values left unchanged.

    """
    return dict(zip((k.upper() for k in d.keys()), d.values()))


def get_relations(model):
    """Returns a list of relation names of `model` (as a list of strings)."""
    return [k for k in dir(model)
            if not (k.startswith('__') or k in RELATION_BLACKLIST)
            and get_related_model(model, k)]


def get_related_model(model, relationname):
    """Gets the class of the model to which `model` is related by the attribute
    whose name is `relationname`.

    """
    if hasattr(model, relationname):
        # inspector = sqlalchemy_inspect(model)
        # attributes = inspector.attrs
        # if relationname in attributes:
        #     state = attributes[relationname]
        attr = getattr(model, relationname)
        if hasattr(attr, 'property') \
                and isinstance(attr.property, RelProperty):
            return attr.property.mapper.class_
        if isinstance(attr, AssociationProxy):
            return get_related_association_proxy_model(attr)
    return None


def get_related_association_proxy_model(attr):
    """Returns the model class specified by the given SQLAlchemy relation
    attribute, or ``None`` if no such class can be inferred.

    `attr` must be a relation attribute corresponding to an association proxy.

    """
    prop = attr.remote_attr.property
    for attribute in ('mapper', 'parent'):
        if hasattr(prop, attribute):
            return getattr(prop, attribute).class_
    return None


def foreign_key_columns(model):
    """Returns a list of the :class:`sqlalchemy.Column` objects that contain
    foreign keys for relationships in the specified model class.

    """
    try:
        inspector = sqlalchemy_inspect(model)
    except NoInspectionAvailable:
        # Well, the inspection of a model class returns a mapper anyway, so
        # let's just assume the inspection would have returned the mapper.
        inspector = class_mapper(model)
    all_columns = inspector.columns
    return [c for c in all_columns if c.foreign_keys]


def foreign_keys(model):
    """Returns a list of the names of columns that contain foreign keys for
    relationships in the specified model class.

    """
    return [column.name for column in foreign_key_columns(model)]


def has_field(model, fieldname):
    """Returns ``True`` if the `model` has the specified field or if it has a
    settable hybrid property for this field name.

    """
    descriptors = sqlalchemy_inspect(model).all_orm_descriptors._data
    if fieldname in descriptors and hasattr(descriptors[fieldname], 'fset'):
        return descriptors[fieldname].fset is not None
    return hasattr(model, fieldname)


def get_field_type(model, fieldname):
    """Helper which returns the SQLAlchemy type of the field."""
    field = getattr(model, fieldname)
    if isinstance(field, ColumnElement):
        return field.type
    if isinstance(field, AssociationProxy):
        field = field.remote_attr
    if hasattr(field, 'property'):
        prop = field.property
        if isinstance(prop, RelProperty):
            return None
        return prop.columns[0].type
    return None


def primary_key_names(model):
    """Returns all the primary keys for a model."""
    return [key for key, field in inspect.getmembers(model)
            if isinstance(field, QueryableAttribute)
            and isinstance(field.property, ColumnProperty)
            and field.property.columns[0].primary_key]


def primary_key_name(model_or_instance):
    """Returns the name of the primary key of the specified model or instance
    of a model, as a string.

    If `model_or_instance` specifies multiple primary keys and ``'id'`` is one
    of them, ``'id'`` is returned. If `model_or_instance` specifies multiple
    primary keys and ``'id'`` is not one of them, only the name of the first
    one in the list of primary keys is returned.

    """
    its_a_model = isinstance(model_or_instance, type)
    model = model_or_instance if its_a_model else model_or_instance.__class__
    pk_names = primary_key_names(model)
    return 'id' if 'id' in pk_names else pk_names[0]


def primary_key_value(instance, as_string=False):
    """Returns the value of the primary key field of the specified `instance`
    of a SQLAlchemy model.

    This is a convenience function for::

        getattr(instance, primary_key_name(instance))

    If `as_string` is ``True``, try to coerce the return value to a string.

    """
    result = getattr(instance, primary_key_name(instance))
    if not as_string:
        return result
    try:
        return str(result)
    except UnicodeEncodeError:
        return url_quote_plus(result.encode('utf-8'))


def is_like_list(instance, relation):
    """Returns ``True`` if and only if the relation of `instance` whose name is
    `relation` is list-like.

    A relation may be like a list if, for example, it is a non-lazy one-to-many
    relation, or it is a dynamically loaded one-to-many.

    """
    if relation in instance._sa_class_manager:
        return instance._sa_class_manager[relation].property.uselist
    elif hasattr(instance, relation):
        attr = getattr(instance._sa_instance_state.class_, relation)
        if hasattr(attr, 'property'):
            return attr.property.uselist
    related_value = getattr(type(instance), relation, None)
    if isinstance(related_value, AssociationProxy):
        local_prop = related_value.local_attr.prop
        if isinstance(local_prop, RelProperty):
            return local_prop.uselist
    return False


def is_mapped_class(cls):
    """Returns ``True`` if and only if the specified SQLAlchemy model class is
    a mapped class.

    """
    try:
        sqlalchemy_inspect(cls)
        return True
    except:
        return False


def evaluate_functions(session, model, functions):
    """Executes each of the SQLAlchemy functions specified in ``functions``, a
    list of dictionaries of the form described below, on the given model and
    returns a dictionary mapping function name (slightly modified, see below)
    to result of evaluation of that function.

    `session` is the SQLAlchemy session in which all database transactions will
    be performed.

    `model` is the SQLAlchemy model class on which the specified functions will
    be evaluated.

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
        return []
    processed = []
    # funcnames = []
    for function in functions:
        if 'name' not in function:
            raise KeyError('Missing `name` key in function object')
        if 'field' not in function:
            raise KeyError('Missing `field` key in function object')
        funcname, fieldname = function['name'], function['field']
        # We retrieve the function by name from the SQLAlchemy ``func``
        # module and the field by name from the model class.
        #
        # If the specified field doesn't exist, this raises AttributeError.
        funcobj = getattr(func, funcname)
        try:
            field = getattr(model, fieldname)
        except AttributeError as exception:
            exception.field = fieldname
            raise exception
        # Store the functions that will be executed in the database.
        # funcnames.append('{0}__{1}'.format(funcname, fieldname))
        processed.append(funcobj(field))
    # Evaluate all the functions at once and get an iterable of results.
    try:
        evaluated = session.query(*processed).one()
    except OperationalError as exception:
        # HACK original error message is of the form:
        #
        #    '(OperationalError) no such function: bogusfuncname'
        #
        original_error_msg = exception.args[0]
        bad_function = original_error_msg[37:]
        exception.function = bad_function
        raise exception
    return list(evaluated)


def query_by_primary_key(session, model, primary_key_value, primary_key=None):
    """Returns a SQLAlchemy query object containing the result of querying
    `model` for instances whose primary key has the value `primary_key_value`.

    If `primary_key` is specified, the column specified by that string is used
    as the primary key column. Otherwise, the column named ``id`` is used.

    Presumably, the returned query should have at most one element.

    """
    pk_name = primary_key or primary_key_name(model)
    query = session_query(session, model)
    return query.filter(getattr(model, pk_name) == primary_key_value)


def get_by(session, model, primary_key_value, primary_key=None):
    """Returns the first instance of `model` whose primary key has the value
    `primary_key_value`, or ``None`` if no such instance exists.

    If `primary_key` is specified, the column specified by that string is used
    as the primary key column. Otherwise, the column named ``id`` is used.

    """
    result = query_by_primary_key(session, model, primary_key_value,
                                  primary_key)
    return result.first()


def string_to_datetime(model, fieldname, value):
    if value is None:
        return value
    # If this is a date, time or datetime field, parse it and convert it to
    # the appropriate type.
    field_type = get_field_type(model, fieldname)
    if isinstance(field_type, (Date, Time, DateTime)):
        # If the string is empty, no datetime can be inferred from it.
        if value.strip() == '':
            return None
        # If the string is a string indicating that the value of should be the
        # current datetime on the server, get the current datetime that way.
        if value in CURRENT_TIME_MARKERS:
            return getattr(func, value.lower())()
        value_as_datetime = parse_datetime(value)
        # If the attribute on the model needs to be a Date or Time object as
        # opposed to a DateTime object, just get the date component of the
        # datetime.
        if isinstance(field_type, Date):
            return value_as_datetime.date()
        if isinstance(field_type, Time):
            return value_as_datetime.time()
        return value_as_datetime
    # If this is an Interval field, convert the integer value to a timedelta.
    if isinstance(field_type, Interval) and isinstance(value, int):
        return datetime.timedelta(seconds=value)
    # In any other case, simply copy the value unchanged.
    return value


def strings_to_datetimes(model, dictionary):
    """Returns a new dictionary with all the mappings of `dictionary` but
    with date strings and intervals mapped to :class:`datetime.datetime` or
    :class:`datetime.timedelta` objects.

    The keys of `dictionary` are names of fields in the model specified in the
    constructor of this class. The values are values to set on these fields. If
    a field name corresponds to a field in the model which is a
    :class:`sqlalchemy.types.Date`, :class:`sqlalchemy.types.DateTime`, or
    :class:`sqlalchemy.Interval`, then the returned dictionary will have the
    corresponding :class:`datetime.datetime` or :class:`datetime.timedelta`
    Python object as the value of that mapping in place of the string.

    This function outputs a new dictionary; it does not modify the argument.

    """
    # In Python 3, this should be
    #     return {k: string_to_datetime(model, k, v)
    #             for k, v in dictionary.items() if k not in ('type', 'links')}
    #
    return dict((k, string_to_datetime(model, k, v))
                for k, v in dictionary.items() if k not in ('type', 'links'))


def count(session, query):
    """Returns the count of the specified `query`.

    This function employs an optimization that bypasses the
    :meth:`sqlalchemy.orm.Query.count` method, which can be very slow for large
    queries.

    """
    counts = query.selectable.with_only_columns([func.count()])
    num_results = session.execute(counts.order_by(None)).scalar()
    if num_results is None or query._limit:
        return query.count()
    return num_results


def get_model(instance):
    """Returns the model class of which the specified object is an instance."""
    return type(instance)


def changes_on_update(model):
    """Returns a best guess at whether the specified SQLAlchemy model class is
    modified on updates.

    We guess whether this happens by checking whether any columns of model have
    the :attr:`sqlalchemy.Column.onupdate` attribute set.

    """
    return any(column.onupdate is not None
               for column in sqlalchemy_inspect(model).columns)


# This code comes from <http://stackoverflow.com/a/6798042/108197>, which is
# licensed under the Creative Commons Attribution-ShareAlike License version
# 3.0 Unported.
#
# That is an answer originally authored by the user
# <http://stackoverflow.com/users/500584/agf> to the question
# <http://stackoverflow.com/q/6760685/108197>.
#
# TODO This code is for simultaneous Python 2 and 3 usage. It can be greatly
# simplified when removing Python 2 support.
class _Singleton(type):
    """A metaclass for a singleton class."""

    #: The known instances of the class instantiating this metaclass.
    _instances = {}

    def __call__(cls, *args, **kwargs):
        """Returns the singleton instance of the specified class."""
        if cls not in cls._instances:
            supercls = super(_Singleton, cls)
            cls._instances[cls] = supercls.__call__(*args, **kwargs)
        return cls._instances[cls]


class Singleton(_Singleton('SingletonMeta', (object,), {})):
    """Base class for a singleton class."""
    pass


class KnowsAPIManagers:

    def __init__(self):
        #: A global list of created :class:`APIManager` objects.
        self.created_managers = set()

    def register(self, apimanager):
        self.created_managers.add(apimanager)


class ModelFinder(KnowsAPIManagers, Singleton):
    """The singleton class that backs the :func:`model_for` function."""

    def __call__(self, collection_name, _apimanager=None, **kw):
        if _apimanager is not None:
            # This may raise ValueError.
            return _apimanager.model_for(collection_name, **kw)
        for manager in self.created_managers:
            try:
                return self(collection_name, _apimanager=manager, **kw)
            except ValueError:
                pass
        message = ('No model with collection name {0} is known to any'
                   ' APIManager objects; maybe you have not set the'
                   ' `collection_name` keyword argument when calling'
                   ' `APIManager.create_api()`?').format(collection_name)
        raise ValueError(message)


class CollectionNameFinder(KnowsAPIManagers, Singleton):
    """The singleton class that backs the :func:`collection_name` function."""

    def __call__(self, model, _apimanager=None, **kw):
        if _apimanager is not None:
            if model not in _apimanager.created_apis_for:
                message = ('APIManager {0} has not created an API for model '
                           ' {1}').format(_apimanager, model)
                raise ValueError(message)
            return _apimanager.collection_name(model, **kw)
        for manager in self.created_managers:
            try:
                return self(model, _apimanager=manager, **kw)
            except ValueError:
                pass
        message = ('Model {0} is not known to any APIManager'
                   ' objects; maybe you have not called'
                   ' APIManager.create_api() for this model.').format(model)
        raise ValueError(message)


class UrlFinder(KnowsAPIManagers, Singleton):
    """The singleton class that backs the :func:`url_for` function."""

    def __call__(self, model, resource_id=None, relation_name=None,
                 related_resource_id=None, _apimanager=None,
                 relationship=False, **kw):
        if _apimanager is not None:
            if model not in _apimanager.created_apis_for:
                message = ('APIManager {0} has not created an API for model '
                           ' {1}; maybe another APIManager instance'
                           ' did?').format(_apimanager, model)
                raise ValueError(message)
            return _apimanager.url_for(model, resource_id=resource_id,
                                       relation_name=relation_name,
                                       related_resource_id=related_resource_id,
                                       relationship=relationship, **kw)
        for manager in self.created_managers:
            try:
                return self(model, resource_id=resource_id,
                            relation_name=relation_name,
                            related_resource_id=related_resource_id,
                            relationship=relationship, _apimanager=manager,
                            **kw)
            except ValueError:
                pass
        message = ('Model {0} is not known to any APIManager'
                   ' objects; maybe you have not called'
                   ' APIManager.create_api() for this model.').format(model)
        raise ValueError(message)


#: Returns the URL for the specified model, similar to :func:`flask.url_for`.
#:
#: `model` is a SQLAlchemy model class. This should be a model on which
#: :meth:`APIManager.create_api_blueprint` (or :meth:`APIManager.create_api`)
#: has been invoked previously. If no API has been created for it, this
#: function raises a `ValueError`.
#:
#: If `_apimanager` is not ``None``, it must be an instance of
#: :class:`APIManager`. Restrict our search for endpoints exposing `model` to
#: only endpoints created by the specified :class:`APIManager` instance.
#:
#: `resource_id`, `relation_name`, and `relationresource_id` allow you to get a more
#: specific sub-resource.
#:
#: For example, suppose you have a model class ``Person`` and have created the
#: appropriate Flask application and SQLAlchemy session::
#:
#:     >>> manager = APIManager(app, session=session)
#:     >>> manager.create_api(Person, collection_name='people')
#:     >>> url_for(Person, resource_id=3)
#:     'http://example.com/api/people/3'
#:     >>> url_for(Person, resource_id=3, relation_name=computers)
#:     'http://example.com/api/people/3/computers'
#:     >>> url_for(Person, resource_id=3, relation_name=computers, related_resource_id=9)
#:     'http://example.com/api/people/3/computers/9'
#:
#: If a `resource_id` and a `relation_name` are provided, and you wish
#: to determine the relationship endpoint URL instead of the related
#: resource URL, set the `relationship` keyword argument to ``True``::
#:
#:     >>> url_for(Person, resource_id=3, relation_name=computers, relationshi=True)
#:     'http://example.com/api/people/3/relatonships/computers'
#:
#: The remaining keyword arguments, `kw`, are passed directly on to
#: :func:`flask.url_for`.
#:
#: Since this function creates absolute URLs to resources linked to the given
#: instance, it must be called within a `Flask request context`_.
#:
#:  .. _Flask request context: http://flask.pocoo.org/docs/0.10/reqcontext/
#:
url_for = UrlFinder()

#: Returns the collection name for the specified model, as specified by the
#: ``collection_name`` keyword argument to :meth:`APIManager.create_api` when
#: it was previously invoked on the model.
#:
#: `model` is a SQLAlchemy model class. This should be a model on which
#: :meth:`APIManager.create_api_blueprint` (or :meth:`APIManager.create_api`)
#: has been invoked previously. If no API has been created for it, this
#: function raises a `ValueError`.
#:
#: If `_apimanager` is not ``None``, it must be an instance of
#: :class:`APIManager`. Restrict our search for endpoints exposing `model` to
#: only endpoints created by the specified :class:`APIManager` instance.
#:
#: For example, suppose you have a model class ``Person`` and have created the
#: appropriate Flask application and SQLAlchemy session::
#:
#:     >>> from mymodels import Person
#:     >>> manager = APIManager(app, session=session)
#:     >>> manager.create_api(Person, collection_name='people')
#:     >>> collection_name(Person)
#:     'people'
#:
#: This function is the inverse of :func:`model_for`::
#:
#:     >>> manager.collection_name(manager.model_for('people'))
#:     'people'
#:     >>> manager.model_for(manager.collection_name(Person))
#:     <class 'mymodels.Person'>
#:
collection_name = CollectionNameFinder()

#: Returns the model corresponding to the given collection name, as specified
#: by the ``collection_name`` keyword argument to :meth:`APIManager.create_api`
#: when it was previously invoked on the model.
#:
#: `collection_name` is a string corresponding to the "type" of a model. This
#: should be a model on which :meth:`APIManager.create_api_blueprint` (or
#: :meth:`APIManager.create_api`) has been invoked previously. If no API has
#: been created for it, this function raises a `ValueError`.
#:
#: If `_apimanager` is not ``None``, it must be an instance of
#: :class:`APIManager`. Restrict our search for endpoints exposing `model` to
#: only endpoints created by the specified :class:`APIManager` instance.
#:
#: For example, suppose you have a model class ``Person`` and have created the
#: appropriate Flask application and SQLAlchemy session::
#:
#:     >>> from mymodels import Person
#:     >>> manager = APIManager(app, session=session)
#:     >>> manager.create_api(Person, collection_name='people')
#:     >>> model_for('people')
#:     <class 'mymodels.Person'>
#:
#: This function is the inverse of :func:`collection_name`::
#:
#:     >>> manager.collection_name(manager.model_for('people'))
#:     'people'
#:     >>> manager.model_for(manager.collection_name(Person))
#:     <class 'mymodels.Person'>
#:
model_for = ModelFinder()
