# serializers.py - JSON serializers for SQLAlchemy models
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
"""Classes for JSON serialization of SQLAlchemy models.

The abstract base class :class:`Serializer` can be used to implement
custom serialization from SQLAlchemy objects. The
:class:`DefaultSerializer` provide some basic serialization as expected
by classes that follow the JSON API protocol.

The implementations here are closely coupled to the rest of the
Flask-Restless code.

"""
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
try:
    from urllib.parse import urljoin
except ImportError:
    from urlparse import urljoin

from flask import request
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.ext.associationproxy import _AssociationDict
from sqlalchemy.ext.associationproxy import _AssociationList
from sqlalchemy.ext.associationproxy import _AssociationSet
from sqlalchemy.ext.hybrid import HYBRID_PROPERTY
from sqlalchemy.inspection import inspect
from werkzeug.routing import BuildError
from werkzeug.urls import url_quote_plus

from .exceptions import SerializationException
from .exceptions import MultipleExceptions
from ..helpers import assoc_proxy_scalar_collections
from ..helpers import collection_name
from ..helpers import foreign_keys
from ..helpers import get_model
from ..helpers import get_related_model
from ..helpers import get_relations
from ..helpers import is_like_list
from ..helpers import is_mapped_class
from ..helpers import primary_key_for
from ..helpers import primary_key_value
from ..helpers import serializer_for
from ..helpers import url_for

#: Names of columns which should definitely not be considered user columns to
#: be included in a dictionary representation of a model.
COLUMN_BLACKLIST = ('_sa_polymorphic_on', )

#: The highest version of the JSON API specification supported by
#: Flask-Restless.
JSONAPI_VERSION = '1.0'


# TODO In Python 2.7 or later, we can just use `timedelta.total_seconds()`.
if hasattr(timedelta, 'total_seconds'):
    def total_seconds(td):
        return td.total_seconds()
else:
    # This formula comes from the Python 2.7 documentation for the
    # `timedelta.total_seconds` method.
    def total_seconds(td):
        secs = td.seconds + td.days * 24 * 3600
        return (td.microseconds + secs * 10**6) / 10**6


def to_unicode(s):
    """Convert a string to a Unicode string, if on Python 2."""
    try:
        return unicode(s)  # noqa
    except NameError:
        return s


def create_relationship(model, instance, relation):
    """Creates a relationship from the given relation name.

    Returns a dictionary representing a relationship as described in
    the `Relationships`_ section of the JSON API specification.

    `model` is the model class of the primary resource for which a
    relationship object is being created.

    `instance` is the instance of the model for which we are considering
    a related value.

    `relation` is the name of the relation of `instance` given as a
    string.

    This function may raise :exc:`ValueError` if an API has not been
    created for the primary model, `model`, or the model of the
    relation.

    .. _Relationships:
       http://jsonapi.org/format/#document-resource-object-relationships

    """
    result = {}
    # Create the self and related links.
    pk_value = primary_key_value(instance)
    self_link = url_for(model, pk_value, relation, relationship=True)
    related_link = url_for(model, pk_value, relation)
    result['links'] = {'self': self_link}
    # If the user has not created a GET endpoint for the related
    # resource, then there is no "related" link to provide, so we check
    # whether the URL exists before setting the related link.
    try:
        related_model = get_related_model(model, relation)
        url_for(related_model)
    except ValueError:
        pass
    else:
        result['links']['related'] = related_link
    # Get the related value so we can see if it is a to-many
    # relationship or a to-one relationship.
    related_value = getattr(instance, relation)
    # There are three possibilities for the relation: it could be a
    # to-many relationship, a null to-one relationship, or a non-null
    # to-one relationship. We decide whether the relation is to-many by
    # determining whether it is list-like.
    if is_like_list(instance, relation):
        # We could pre-compute the "type" name for the related instances
        # here and provide it in the `_type` keyword argument to the
        # serialization function, but the to-many relationship could be
        # heterogeneous.
        result['data'] = list(map(simple_relationship_dump, related_value))
    elif related_value is not None:
        result['data'] = simple_relationship_dump(related_value)
    else:
        result['data'] = None
    return result


def JsonApiDocument():
    """A skeleton JSON API document, containing the basic elements but
    no data.

    """
    document = {
        'data': None,
        'jsonapi': {
            'version': JSONAPI_VERSION
        },
        'links': {},
        'meta': {},
        'included': []
    }
    return document


def get_column_name(column):
    """Retrieve a column name from a column attribute of SQLAlchemy model
    class, or a string.

    Raises `TypeError` when argument does not fall into either of those
    options.

    """
    try:
        inspected_column = inspect(column)
    except NoInspectionAvailable:
        # In this case, we assume the column is actually just a string.
        return column
    else:
        return inspected_column.key


class Serializer(object):
    """An object that serializes one or many instances of a SQLAlchemy
    model to a dictionary representation.

    **This is a base class with no implementation.**

    """

    def serialize(self, instance, only=None):
        """Returns a dictionary representation of the specified instance
        of a SQLAlchemy model.

        If `only` is a list, only the fields and relationships whose
        names appear as strings in `only` should appear in the returned
        dictionary.

        **This method is not implemented in this base class; subclasses must
        override this method.**

        """
        raise NotImplementedError

    def serialize_many(self, instances, only=None):
        """Returns a dictionary representation of the specified
        instances of a SQLAlchemy model.

        If `only` is a list, only the fields and relationships whose
        names appear as strings in `only` should appear in the returned
        dictionary.

        **This method is not implemented in this base class; subclasses must
        override this method.**

        """
        raise NotImplementedError


class DefaultSerializer(Serializer):
    """A default implementation of a JSON API serializer for SQLAlchemy
    models.

    The :meth:`.serialize` method of this class returns a complete JSON
    API document as a dictionary containing the resource object
    representation of the given instance of a SQLAlchemy model as its
    primary data. Similarly, the :meth:`.serialize_many` method returns
    a JSON API document containing a a list of resource objects as its
    primary data.

    If `only` is a list, only these fields and relationships will in the
    returned dictionary. The only exception is that the keys ``'id'``
    and ``'type'`` will always appear, regardless of whether they appear
    in `only`.  These settings take higher priority than the `only` list
    provided to the :meth:`.serialize` or :meth:`.serialize_many`
    methods: if an attribute or relationship appears in the `only`
    argument to those method but not here in the constructor, it will
    not appear in the returned dictionary.

    If `exclude` is a list, these fields and relationships will **not**
    appear in the returned dictionary.

    If `additional_attributes` is a list, these attributes of the
    instance to be serialized will appear in the returned
    dictionary. This is useful if your model has an attribute that is
    not a SQLAlchemy column but you want it to be exposed.

    You **must not** specify both `only` and `exclude` lists; if you do,
    the behavior of this function is undefined.

    You **must not** specify a field in both `exclude` and in
    `additional_attributes`; if you do, the behavior of this function is
    undefined.

    """

    def __init__(self, only=None, exclude=None, additional_attributes=None,
                 **kw):
        super(DefaultSerializer, self).__init__(**kw)
        # Always include at least the type and ID, regardless of what the user
        # specified.
        if only is not None:
            # Convert SQLAlchemy Column objects to strings if necessary.
            #
            # TODO In Python 2.7 or later, this should be a set comprehension.
            only = set(get_column_name(column) for column in only)
            # TODO In Python 2.7 or later, this should be a set literal.
            only |= set(['type', 'id'])
        if exclude is not None:
            # Convert SQLAlchemy Column objects to strings if necessary.
            #
            # TODO In Python 2.7 or later, this should be a set comprehension.
            exclude = set(get_column_name(column) for column in exclude)
        self.default_fields = only
        self.exclude = exclude
        self.additional_attributes = additional_attributes

    def _is_excluded(self, f, only):
        """Decide whether a field should be excluded from serialization.

        `f` is a string naming a column (either an attribute or a
        relationship) of a resource. `only` is a list of strings naming
        fields, as described in :meth:`.DefaultSerializer.serialize`.

        This function returns a Boolean indicating whether the field
        should be excluded from serialization. The decision is based on
        the `only` fields requested by the client as well as the default
        included or excluded fields specified in the constructor of this
        class.

        """
        if self.default_fields is not None and f not in self.default_fields:
            return True
        if only is not None and f not in only:
            return True
        if self.exclude is not None and f in self.exclude:
            return True
        return False

    def _dump(self, instance, only=None):
        # Always include at least the type and ID, regardless of what
        # the user requested.
        if only is not None:
            # TODO In Python 2.7 or later, this should be a set literal.
            only = set(only) | set(['type', 'id'])
        model = type(instance)
        try:
            inspected_instance = inspect(model)
        except NoInspectionAvailable:
            message = 'failed to get columns for model {0}'.format(model)
            raise SerializationException(instance, message=message)

        # Determine the columns to serialize as "attributes".
        #
        # This include plain old columns (like strings and integers, for
        # example), hybrid properties, and association proxies to scalar
        # collections (like a list of strings, for example).
        column_attrs = inspected_instance.column_attrs.keys()
        assoc_scalars = list(assoc_proxy_scalar_collections(model))
        descriptors = inspected_instance.all_orm_descriptors.items()
        hybrid_columns = [k for k, d in descriptors
                          if d.extension_type == HYBRID_PROPERTY]
        columns = column_attrs + assoc_scalars + hybrid_columns
        # Also include any attributes specified by the user.
        if self.additional_attributes is not None:
            columns += self.additional_attributes

        # Serialize each attribute, excluding those that should be excluded.
        attributes = {}
        foreign_key_columns = foreign_keys(model)
        pk_name = primary_key_for(model)
        for column in columns:
            if self._is_excluded(column, only=only):
                continue
            # Exclude column names that are blacklisted.
            if column.startswith('__') or column in COLUMN_BLACKLIST:
                continue
            # Exclude column names that are foreign keys (unless the
            # foreign key is the primary key for the model; this can
            # happen in the joined table inheritance database
            # configuration).
            if column in foreign_key_columns and column != pk_name:
                continue

            # Get the value for this column. Call it if it is callable.
            value = getattr(instance, column)
            if callable(value):
                value = value()
            # Attributes values that come from association proxy
            # collections need to be cast to plain old Python data types
            # so that the JSON serializer can handle them.
            if isinstance(value, _AssociationList):
                value = list(value)
            elif isinstance(value, _AssociationSet):
                value = set(value)
            elif isinstance(value, _AssociationDict):
                value = dict(value)
            # Serialize any date- or time-like objects that appear in
            # the attributes.
            #
            # TODO In Flask 0.11, the default JSON encoder for the Flask
            # application object does this automatically. Alternately,
            # the user could have set a smart JSON encoder on the Flask
            # application, which would cause these attributes to be
            # converted to strings when the Response object is created
            # (in the `jsonify` function, for example). However, we
            # should not rely on that JSON encoder since the user could
            # set any crazy encoder on the Flask application.
            if isinstance(value, (date, datetime, time)):
                value = value.isoformat()
            elif isinstance(value, timedelta):
                value = total_seconds(value)
            # Recursively serialize any object that appears in the
            # attributes. This may happen if, for example, the return
            # value of one of the callable functions is an instance of
            # another SQLAlchemy model class.
            #
            # This is a bit of a fragile test for whether the object
            # needs to be serialized: we simply check if the class of
            # the object is a mapped class.
            if is_mapped_class(type(value)):
                model_ = get_model(value)
                try:
                    serializer = serializer_for(model_)
                    serialized_val = serializer.serialize(value)
                except ValueError:
                    # TODO Should this cause an exception, or fail
                    # silently? See similar comments in `views/base.py`.
                    # # raise SerializationException(instance)
                    serialized_val = simple_serialize(value)
                # We only need the data from the JSON API document, not
                # the metadata. (So really the serializer is doing more
                # work than it needs to here.)
                value = serialized_val['data']

            # Set this column's value in the attributes dictionary.
            attributes[column] = value

        # Get the ID and type of the resource.
        id_ = attributes.pop('id', None)
        type_ = collection_name(model)
        # Create the result dictionary and add the attributes.
        result = dict(id=id_, type=type_)
        if attributes:
            result['attributes'] = attributes

        # Add the self link unless it has been explicitly excluded.
        is_self_in_default = (self.default_fields is None or
                              'self' in self.default_fields)
        is_self_in_only = only is None or 'self' in only
        if is_self_in_default and is_self_in_only:
            instance_id = primary_key_value(instance)
            # `url_for` may raise a `BuildError` if the user has not created a
            # GET API endpoint for this model. In this case, we simply don't
            # provide a self link.
            #
            # TODO This might fail if the user has set the
            # `current_app.build_error_handler` attribute, in which case, the
            # exception may not be raised.
            try:
                path = url_for(model, instance_id, _method='GET')
            except BuildError:
                pass
            else:
                # HACK In order to support users using Python 2.7 with
                # the `future` compatibility library, we need to ensure
                # that both `request.url_root` and `path` are of the
                # same type.
                path = to_unicode(path)
                url = urljoin(request.url_root, path)
                result['links'] = dict(self=url)
        # # add any included methods
        # if include_methods is not None:
        #     for method in include_methods:
        #         if '.' not in method:
        #             value = getattr(instance, method)
        #             # Allow properties and static attributes in
        #             # include_methods
        #             if callable(value):
        #                 value = value()
        #             result[method] = value

        # If the primary key is not named "id", we'll duplicate the
        # primary key under the "id" key.
        if pk_name != 'id':
            result['id'] = result['attributes'][pk_name]
        # TODO Same problem as above.
        #
        # In order to comply with the JSON API standard, primary keys must be
        # returned to the client as strings, so we convert it here.
        if 'id' in result:
            try:
                result['id'] = str(result['id'])
            except UnicodeEncodeError:
                result['id'] = url_quote_plus(result['id'].encode('utf-8'))

        # Serialize each relationship, excluding those that should be excluded.
        relationships = {}
        for r in get_relations(model):
            if not self._is_excluded(r, only=only):
                relationships[r] = create_relationship(model, instance, r)

        if relationships:
            result['relationships'] = relationships

        return result

    def serialize(self, instance, only=None):
        """Returns a complete JSON API document as a dictionary
        containing the resource object representation of the given
        instance of a SQLAlchemy model as its primary data.

        The returned dictionary is suitable as an argument to
        :func:`flask.json.jsonify`. Specifically, date and time objects
        (:class:`datetime.date`, :class:`datetime.time`,
        :class:`datetime.datetime`, and :class:`datetime.timedelta`) as
        well as :class:`uuid.UUID` objects are converted to string
        representations, so no special JSON encoder behavior is
        required.

        If `only` is a list, only the fields and relationships whose
        names appear as strings in `only` will appear in the resulting
        dictionary. This filter is applied *after* the default fields
        specified in the `only` keyword argument to the constructor of
        this class, so only fields that appear in both `only` keyword
        arguments will appear in the returned dictionary. The only
        exception is that the keys ``'id'`` and ``'type'`` will always
        appear, regardless of whether they appear in `only`.

        Since this method creates absolute URLs to resources linked to
        the given instance, it must be called within a `Flask request
        context`_.

        .. _Flask request context: http://flask.pocoo.org/docs/0.10/reqcontext/

        """
        resource = self._dump(instance, only=only)
        result = JsonApiDocument()
        result['data'] = resource
        return result

    def serialize_many(self, instances, only=None):
        """Serializes each instance using its model-specific serializer.

        This method works for heterogeneous collections of instances
        (that is, collections in which each instance is of a different
        type).

        The `only` keyword argument must be a dictionary mapping
        resource type name to list of fields representing a sparse
        fieldset. The values in this dictionary must be valid values for
        the `only` keyword argument in the
        :meth:`DefaultSerializer.serialize` method.

        """
        resources = []
        failed = []
        for instance in instances:
            # Determine the serializer for this instance.
            model = get_model(instance)
            try:
                serializer = serializer_for(model)
            except ValueError:
                message = 'Failed to find serializer class'
                exception = SerializationException(instance, message=message)
                failed.append(exception)
                continue
            # This may also raise ValueError
            try:
                _type = collection_name(model)
            except ValueError:
                message = 'Failed to find collection name'
                exception = SerializationException(instance, message=message)
                failed.append(exception)
                continue
            _only = only.get(_type)
            try:
                serialized = serializer.serialize(instance, only=_only)
                # We only need the data from the JSON API document, not
                # the metadata. (So really the serializer is doing more
                # work than it needs to here.)
                #
                # TODO We could use `serializer._dump` instead.
                serialized = serialized['data']
                resources.append(serialized)
            except SerializationException as exception:
                failed.append(exception)
        if failed:
            raise MultipleExceptions(failed)
        result = JsonApiDocument()
        result['data'] = resources
        return result


class DefaultRelationshipSerializer(Serializer):
    """A default implementation of a serializer for resource identifier
    objects for use in relationship objects in JSON API documents.

    This serializer differs from the default serializer for resources
    since it only provides an ``'id'`` and a ``'type'`` in the
    dictionary returned by the :meth:`.serialize` and
    :meth:`.serialize_many` methods.

    """

    def _dump(self, instance, _type=None):
        if _type is None:
            _type = collection_name(get_model(instance))
        id_ = primary_key_value(instance, as_string=True)
        return {'id': id_, 'type': _type}

    def serialize(self, instance, only=None, _type=None):
        resource_identifier = self._dump(instance, _type=_type)
        result = JsonApiDocument()
        result['data'] = resource_identifier
        return result

    def serialize_many(self, instances, only=None, _type=None):
        # Since dumping each resource identifier from a given instance
        # could theoretically raise a SerializationException, we collect
        # all the errors and wrap them in a MultipleExceptions exception
        # object.
        resource_identifiers = []
        failed = []
        for instance in instances:
            try:
                resource_identifier = self._dump(instance, _type=_type)
                resource_identifiers.append(resource_identifier)
            except SerializationException as exception:
                failed.append(exception)
        if failed:
            raise MultipleExceptions(failed)
        result = JsonApiDocument()
        result['data'] = resource_identifiers
        return result


#: This is an instance of the default serializer class,
#: :class:`DefaultSerializer`.
#:
#: The purpose of this instance is to provide easy access to default
#: serialization methods.
singleton_serializer = DefaultSerializer()

#: This is an instance of the default relationship serializer class,
#: :class:`DefaultRelationshipSerializer`.
#:
#: The purpose of this instance is to provide easy access to default
#: serialization methods.
singleton_relationship_serializer = DefaultRelationshipSerializer()

simple_dump = singleton_serializer.serialize

#: Provides basic, uncustomized serialization functionality as provided
#: by the :meth:`DefaultSerializer.serialize` method.
#:
#: This function is suitable for calling on its own, no other
#: instantiation or customization necessary.
simple_serialize = singleton_serializer.serialize

#: Provides basic, uncustomized serialization functionality as provided
#: by the :meth:`DefaultSerializer.serialize_many` method.
#:
#: This function is suitable for calling on its own, no other
#: instantiation or customization necessary.
simple_serialize_many = singleton_serializer.serialize_many

simple_relationship_dump = singleton_relationship_serializer._dump

#: Provides basic, uncustomized serialization functionality as provided
#: by the :meth:`DefaultRelationshipSerializer.serialize` method.
#:
#: This function is suitable for calling on its own, no other
#: instantiation or customization necessary.
simple_relationship_serialize = singleton_relationship_serializer.serialize

#: Provides basic, uncustomized serialization functionality as provided
#: by the :meth:`DefaultRelationshipSerializer.serialize_many` method.
#:
#: This function is suitable for calling on its own, no other
#: instantiation or customization necessary.
simple_relationship_serialize_many = \
    singleton_relationship_serializer.serialize_many
