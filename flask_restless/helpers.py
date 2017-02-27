# helpers.py - helper functions for Flask-Restless
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
"""Helper functions for Flask-Restless.

Many of the functions in this module use the `SQLAlchemy inspection
API`_. As a rule, however, these functions do not catch
:exc:`sqlalchemy.exc.NoInspectionAvailable` exceptions; the
responsibility is on the calling function to ensure that functions that
expect, for example, a SQLAlchemy model actually receive a SQLAlchemy
model.

.. _SQLAlchemy inspection API:
   https://docs.sqlalchemy.org/en/latest/core/inspection.html

"""
import datetime
import inspect

from dateutil.parser import parse as parse_datetime
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Interval
from sqlalchemy import Time
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.ext.associationproxy import AssociationProxy
from sqlalchemy.orm import RelationshipProperty
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import ColumnElement
from sqlalchemy.inspection import inspect as sqlalchemy_inspect
from werkzeug.urls import url_quote_plus

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


def assoc_proxy_scalar_collections(model):
    """Yields the name of each association proxy collection as a string.

    This includes each association proxy that proxies to a scalar
    collection (for example, a list of strings) via an association
    table. It excludes each association proxy that proxies to a
    collection of instances (for example, a to-many relationship) via an
    association object.

    .. seealso::

       :func:`scalar_collection_proxied_relations`

    .. versionadded:: 1.0.0

    """
    mapper = sqlalchemy_inspect(model)
    for k, v in mapper.all_orm_descriptors.items():
        if isinstance(v, AssociationProxy) \
           and not isinstance(v.remote_attr.property, RelationshipProperty) \
           and is_like_list(model, v.local_attr.key):
            yield k


def get_relations(model):
    """Yields the name of each relationship of a model as a string.

    For a relationship via an association proxy, this function shows
    only the remote attribute, not the intermediate relationship. For
    example, if there is a table for ``Article`` and ``Tag`` and a table
    associating the two via a many-to-many relationship, ::

        from sqlalchemy import Column
        from sqlalchemy import ForeignKey
        from sqlalchemy import Integer
        from sqlalchemy.ext.declarative import declarative_base
        from sqlalchemy.orm import relationship

        Base = declarative_base()

        class Article(Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            articletags = relationship('ArticleTag')
            tags = association_proxy('articletags', 'tag',
                                     creator=lambda tag: ArticleTag(tag=tag))

        class ArticleTag(Base):
            __tablename__ = 'articletag'
            article_id = Column(Integer, ForeignKey('article.id'),
                                primary_key=True)
            tag_id = Column(Integer, ForeignKey('tag.id'), primary_key=True)
            tag = relationship('Tag')

        class Tag(self.Base):
            __tablename__ = 'tag'
            id = Column(Integer, primary_key=True)

    then this function reveals the ``tags`` proxy::

        >>> list(get_relations(Article))
        ['tags']

    Similarly, for association proxies that proxy to a scalar collection
    via an association table, this will show the related model. For
    example, if there is an association proxy for a scalar collection
    like this::

        from sqlalchemy import Column
        from sqlalchemy import ForeignKey
        from sqlalchemy import Integer
        from sqlalchemy import Table
        from sqlalchemy.ext.declarative import declarative_base
        from sqlalchemy.orm import relationship

        Base = declarative_base()

        class Article(Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            tags = relationship('Tag', secondary=lambda: articletags_table)
            tag_names = association_proxy('tags', 'name',
                                          creator=lambda s: Tag(name=s))

        class Tag(self.Base):
            __tablename__ = 'tag'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)

        articletags_table = \
            Table('articletags', Base.metadata,
                  Column('article_id', Integer, ForeignKey('article.id'),
                         primary_key=True),
                  Column('tag_id', Integer, ForeignKey('tag.id'),
                         primary_key=True)
            )

    then this function yields only the ``tags`` relationship, not the
    ``tag_names`` attribute::

        >>> list(get_relations(Article))
        ['tags']

    """
    mapper = sqlalchemy_inspect(model)

    # If we didn't have to deal with association proxies, we could just
    # do `return list(mapper.relationships)`.
    #
    # However, we need to deal with (at least) two different usages of
    # association proxies: one in which the proxy is to a scalar
    # collection (like a list of strings) and one in which the proxy is
    # to a collection of instances (like a to-many relationship).
    #
    # First we record each association proxy and the the local attribute
    # through which it proxies. This information is stored in a mapping
    # from local attribute key to proxy name. For example, an
    # association proxy defined like this::
    #
    #     tags = associationproxy('articletags', 'tag')
    #
    # is stored below as a dictionary entry mapping 'articletags' to
    # 'tags'.
    association_proxies = {}
    for k, v in mapper.all_orm_descriptors.items():
        if isinstance(v, AssociationProxy):
            association_proxies[v.local_attr.key] = k

    # Next we determine which association proxies represent scalar
    # collections as opposed to to-many relationships. We need to ignore
    # these.
    scalar_collections = set(assoc_proxy_scalar_collections(model))

    # Finally we find all plain old relationships and all association
    # proxy relationships.
    #
    # If the association proxy is through an association object, we
    # yield that too.
    for r in mapper.relationships.keys():
        yield r
        proxy = association_proxies.get(r)
        if proxy is not None and proxy not in scalar_collections:
                yield association_proxies[r]


def get_related_model(model, relationname):
    """Gets the class of the model to which `model` is related by the attribute
    whose name is `relationname`.

    For example, if we have the model classes ::

        class Person(Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            articles = relationship('Article')

        class Article(Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')

    then ::

        >>> get_related_model(Person, 'articles')
        <class 'Article'>
        >>> get_related_model(Article, 'author')
        <class 'Person'>

    This function also "sees through" association proxies and returns
    the model of the proxied remote relation.

    """
    mapper = sqlalchemy_inspect(model)
    attribute = mapper.all_orm_descriptors[relationname]
    # HACK This is required for Python 3.3 only. I'm guessing it lazily
    # loads the attribute or something like that.
    hasattr(model, relationname)
    return get_related_model_from_attribute(attribute)


def get_related_model_from_attribute(attribute):
    """Gets the class of the model related to the given attribute via
    the given name.

    `attribute` may be an
    :class:`~sqlalchemy.orm.attributes.InstrumentedAttribute` or an
    :class:`~sqlalchemy.ext.associationproxy.AssociationProxy`, for
    example ``Article.comments`` or ``Comment.tags``. This function
    "sees through" association proxies to return the model of the
    proxied remote relation.

    """
    if isinstance(attribute, AssociationProxy):
        return attribute.remote_attr.mapper.class_
    return attribute.property.mapper.class_


def foreign_key_columns(model):
    """Returns a list of the :class:`sqlalchemy.Column` objects that contain
    foreign keys for relationships in the specified model class.

    """
    mapper = sqlalchemy_inspect(model)
    return [c for c in mapper.columns if c.foreign_keys]


def foreign_keys(model):
    """Returns a list of the names of columns that contain foreign keys for
    relationships in the specified model class.

    """
    return [column.name for column in foreign_key_columns(model)]


def has_field(model, fieldname):
    """Returns ``True`` if the `model` has the specified field or if it has a
    settable hybrid property for this field name.

    """
    mapper = sqlalchemy_inspect(model)
    # Get all descriptors, which include columns, relationships, and
    # other things like association proxies and hybrid properties.
    descriptors = mapper.all_orm_descriptors
    if fieldname not in descriptors:
        return False
    field = descriptors[fieldname]
    # First, we check whether `fieldname` specifies a settable hybrid
    # property. This is a bit flimsy: we check whether the `fset`
    # attribute has been set on the `hybrid_property` instance. The
    # `fset` instance attribute is only set if the user defined a hybrid
    # property setter.
    if hasattr(field, 'fset'):
        return field.fset is not None
    # At this point, we simply check that the attribute is not callable.
    return not callable(getattr(model, fieldname))


def is_relationship(model, fieldname):
    """Decides whether a field is a relationship (as opposed to a
    field).

    `model` is a SQLAlchemy model.

    `fieldname` is a string naming a field of the given model. This
    function returns True if and only if the field is a relationship.

    This function currently does *not* return `True` for association
    proxies.

    """
    mapper = sqlalchemy_inspect(model)
    return fieldname in mapper.relationships


def get_field_type(model, fieldname):
    """Returns the SQLAlchemy type of the field.

    This works for plain columns and association proxies. If `fieldname`
    specifies a hybrid property, this function returns `None`.

    """
    field = getattr(model, fieldname)
    if isinstance(field, ColumnElement):
        return field.type
    if isinstance(field, AssociationProxy):
        field = field.remote_attr
    if hasattr(field, 'property'):
        prop = field.property
        if isinstance(prop, RelationshipProperty):
            return None
        return prop.columns[0].type
    return None


def primary_key_names(model):
    """Returns a list of all the primary keys for a model.

    The returned list contains the name of each primary key as a string.

    """
    mapper = sqlalchemy_inspect(model)
    return [column.name for column in mapper.primary_key]


def primary_key_value(instance, as_string=False):
    """Returns the value of the primary key field of the specified `instance`
    of a SQLAlchemy model.

    This essentially a convenience function for::

        getattr(instance, primary_key_for(instance))

    If `as_string` is ``True``, try to coerce the return value to a string.

    """
    result = getattr(instance, primary_key_for(instance))
    if not as_string:
        return result
    try:
        return str(result)
    except UnicodeEncodeError:
        return url_quote_plus(result.encode('utf-8'))


def is_like_list(model_or_instance, relationname):
    """Decides whether a relation of a SQLAlchemy model is list-like.

    A relation may be like a list if it behaves like a to-many relation
    (either lazy or eager)

    `model_or_instance` may be either a SQLAlchemy model class or an
    instance of such a class.

    `relationname` is a string naming a relationship of the given
    model or instance.

    """
    # Use Python's built-in inspect module to decide whether the
    # argument is a model or an instance of a model.
    if not inspect.isclass(model_or_instance):
        model = get_model(model_or_instance)
    else:
        model = model_or_instance
    mapper = sqlalchemy_inspect(model)
    relation = mapper.all_orm_descriptors[relationname]
    if isinstance(relation, AssociationProxy):
        relation = relation.local_attr
    return relation.property.uselist


def is_mapped_class(cls):
    """Returns ``True`` if and only if the specified SQLAlchemy model class is
    a mapped class.

    """
    try:
        sqlalchemy_inspect(cls)
    except NoInspectionAvailable:
        return False
    else:
        return True


def query_by_primary_key(session, model, pk_value, primary_key=None):
    """Returns a SQLAlchemy query object containing the result of querying
    `model` for instances whose primary key has the value `pk_value`.

    If `primary_key` is specified, the column specified by that string is used
    as the primary key column. Otherwise, the column named ``id`` is used.

    Presumably, the returned query should have at most one element.

    """
    pk_name = primary_key or primary_key_for(model)
    query = session_query(session, model)
    return query.filter(getattr(model, pk_name) == pk_value)


def get_by(session, model, pk_value, primary_key=None):
    """Returns the first instance of `model` whose primary key has the value
    `pk_value`, or ``None`` if no such instance exists.

    If `primary_key` is specified, the column specified by that string is used
    as the primary key column. Otherwise, the column named ``id`` is used.

    """
    result = query_by_primary_key(session, model, pk_value, primary_key)
    return result.first()


def string_to_datetime(model, fieldname, value):
    """Casts `value` to a :class:`datetime.datetime` or
    :class:`datetime.timedelta` object if the given field of the given
    model is a date-like or interval column.

    If the field name corresponds to a field in the model which is a
    :class:`sqlalchemy.types.Date`, :class:`sqlalchemy.types.DateTime`,
    or :class:`sqlalchemy.Interval`, then the returned value will be the
    :class:`datetime.datetime` or :class:`datetime.timedelta` Python
    object corresponding to `value`. Otherwise, the `value` is returned
    unchanged.

    """
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
            return value_as_datetime.timetz()
        return value_as_datetime
    # If this is an Interval field, convert the integer value to a timedelta.
    if isinstance(field_type, Interval) and isinstance(value, int):
        return datetime.timedelta(seconds=value)
    # In any other case, simply copy the value unchanged.
    return value


def get_model(instance):
    """Returns the model class of which the specified object is an instance."""
    return type(instance)


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
    """An object that allows client code to register :class:`APIManager`
    objects.

    """

    def __init__(self):
        #: A global list of created :class:`APIManager` objects.
        self.created_managers = set()

    def register(self, apimanager):
        """Inform this object about the specified :class:`APIManager` object.

        """
        self.created_managers.add(apimanager)


class ModelFinder(KnowsAPIManagers, Singleton):
    """The singleton class that backs the :func:`model_for` function."""

    def __call__(self, resource_type, _apimanager=None, **kw):
        if _apimanager is not None:
            # This may raise ValueError.
            return _apimanager.model_for(resource_type, **kw)
        for manager in self.created_managers:
            try:
                return self(resource_type, _apimanager=manager, **kw)
            except ValueError:
                pass
        message = ('No model with collection name {0} is known to any'
                   ' APIManager objects; maybe you have not set the'
                   ' `collection_name` keyword argument when calling'
                   ' `APIManager.create_api()`?').format(resource_type)
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


class SerializerFinder(KnowsAPIManagers, Singleton):
    """The singleton class that backs the :func:`serializer_for` function."""

    def __call__(self, model, _apimanager=None, **kw):
        if _apimanager is not None:
            if model not in _apimanager.created_apis_for:
                message = ('APIManager {0} has not created an API for model '
                           ' {1}').format(_apimanager, model)
                raise ValueError(message)
            return _apimanager.serializer_for(model, **kw)
        for manager in self.created_managers:
            try:
                return self(model, _apimanager=manager, **kw)
            except ValueError:
                pass
        message = ('Model {0} is not known to any APIManager'
                   ' objects; maybe you have not called'
                   ' APIManager.create_api() for this model.').format(model)
        raise ValueError(message)


class PrimaryKeyFinder(KnowsAPIManagers, Singleton):
    """The singleton class that backs the :func:`primary_key_for` function."""

    def __call__(self, instance_or_model, _apimanager=None, **kw):
        if isinstance(instance_or_model, type):
            model = instance_or_model
        else:
            model = instance_or_model.__class__

        if _apimanager is not None:
            managers_to_search = [_apimanager]
        else:
            managers_to_search = self.created_managers
        for manager in managers_to_search:
            if model in manager.created_apis_for:
                primary_key = manager.primary_key_for(model, **kw)
                break
        else:
            message = ('Model "{0}" is not known to {1}; maybe you have not'
                       ' called APIManager.create_api() for this model?')
            if _apimanager is not None:
                manager_string = 'APIManager "{0}"'.format(_apimanager)
            else:
                manager_string = 'any APIManager objects'
            message = message.format(model, manager_string)
            raise ValueError(message)

        # If `APIManager.create_api(model)` was called without providing
        # a value for the `primary_key` keyword argument, then we must
        # compute the primary key name from the model directly.
        if primary_key is None:
            pk_names = primary_key_names(model)
            primary_key = 'id' if 'id' in pk_names else pk_names[0]
        return primary_key


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
#: The `resource_id`, `relation_name`, and `relationresource_id` keyword
#: arguments allow you to get the URL for a more specific sub-resource.
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
#:     >>> url_for(Person, resource_id=3, relation_name=computers,
#:     ...         related_resource_id=9)
#:     'http://example.com/api/people/3/computers/9'
#:
#: If a `resource_id` and a `relation_name` are provided, and you wish
#: to determine the relationship endpoint URL instead of the related
#: resource URL, set the `relationship` keyword argument to ``True``::
#:
#:     >>> url_for(Person, resource_id=3, relation_name=computers,
#:     ...         relationship=True)
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

#: Returns the callable serializer object for the specified model, as
#: specified by the `serializer` keyword argument to
#: :meth:`APIManager.create_api` when it was previously invoked on the
#: model.
#:
#: `model` is a SQLAlchemy model class. This should be a model on which
#: :meth:`APIManager.create_api_blueprint` (or :meth:`APIManager.create_api`)
#: has been invoked previously. If no API has been created for it, this
#: function raises a `ValueError`.
#:
#: If `_apimanager` is not ``None``, it must be an instance of
#: :class:`APIManager`. Restrict our search for endpoints exposing
#: `model` to only endpoints created by the specified
#: :class:`APIManager` instance.
#:
#: For example, suppose you have a model class ``Person`` and have
#: created the appropriate Flask application and SQLAlchemy session::
#:
#:     >>> from mymodels import Person
#:     >>> def my_serializer(model, *args, **kw):
#:     ...     # return something cool here...
#:     ...     return {}
#:     ...
#:     >>> manager = APIManager(app, session=session)
#:     >>> manager.create_api(Person, serializer=my_serializer)
#:     >>> serializer_for(Person)
#:     <function my_serializer at 0x...>
#:
serializer_for = SerializerFinder()

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

#: Returns the primary key to be used for the given model or model instance,
#: as specified by the ``primary_key`` keyword argument to
#: :meth:`APIManager.create_api` when it was previously invoked on the model.
#:
#: `primary_key` is a string corresponding to the primary key identifier
#: to be used by flask-restless for a model. If no primary key has been set
#: at the flask-restless level (by using the ``primary_key`` keyword argument
#: when calling :meth:`APIManager.create_api_blueprint`, the model's primary
#: key will be returned. If no API has been created for the model, this
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
#:     >>> manager.create_api(Person, primary_key='name')
#:     >>> primary_key_for(Person)
#:     'name'
#:     >>> my_person = Person(name="Bob")
#:     >>> primary_key_for(my_person)
#:     'name'
#:
#: This is in contrast to the typical default:
#:
#:     >>> manager = APIManager(app, session=session)
#:     >>> manager.create_api(Person)
#:     >>> primary_key_for(Person)
#:     'id'
#:
primary_key_for = PrimaryKeyFinder()
