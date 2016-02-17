# serialization.py - JSON serialization for SQLAlchemy models
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

The abstract base classes :class:`Serializer` and :class:`Deserializer`
can be used to implement custom serialization from and deserialization
to SQLAlchemy objects. The :class:`DefaultSerializer` and
:class:`DefaultDeserializer` provide some basic serialization and
deserialization as expected by classes that follow the JSON API
protocol.

"""
from __future__ import division

from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
try:
    from urllib.parse import urljoin
except ImportError:
    from urlparse import urljoin

from flask import request
from sqlalchemy import Column
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.ext.hybrid import HYBRID_PROPERTY
from sqlalchemy.inspection import inspect
from sqlalchemy.orm.query import Query
from werkzeug.routing import BuildError
from werkzeug.urls import url_quote_plus

from .helpers import collection_name
from .helpers import is_mapped_class
from .helpers import foreign_keys
from .helpers import get_by
from .helpers import get_model
from .helpers import get_related_model
from .helpers import get_relations
from .helpers import has_field
from .helpers import is_like_list
from .helpers import primary_key_name
from .helpers import primary_key_value
from .helpers import strings_to_datetimes
from .helpers import url_for

#: Names of columns which should definitely not be considered user columns to
#: be included in a dictionary representation of a model.
COLUMN_BLACKLIST = ('_sa_polymorphic_on', )

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


class SerializationException(Exception):
    """Raised when there is a problem serializing an instance of a
    SQLAlchemy model to a dictionary representation.

    ``instance`` is the (problematic) instance on which
    :meth:`Serializer.__call__` was invoked.

    `resource` is an optional partially-constructed serialized
    representation of ``instance``.

    """

    def __init__(self, instance, resource=None, *args, **kw):
        super(SerializationException, self).__init__(*args, **kw)
        self.resource = resource
        self.instance = instance


class DeserializationException(Exception):
    """Raised when there is a problem deserializing a Python dictionary to an
    instance of a SQLAlchemy model.

    Subclasses that wish to provide more detailed about the problem
    should set the ``detail`` attribute to be a string, either as a
    class-level attribute or as an instance attribute.

    """

    def __init__(self, *args, **kw):
        super(DeserializationException, self).__init__(*args, **kw)

        #: A string describing the problem in more detail.
        #:
        #: Subclasses must set this attribute to be a string describing
        #: the problem that cause this exception.
        self.detail = None

    def message(self):
        """Returns a more detailed description of the problem as a
        string.

        """
        base = 'Failed to deserialize object'
        if self.detail is not None:
            return '{0}: {1}'.format(base, self.detail)
        return base


class ConflictingType(DeserializationException):
    """Raised when attempting to deserialize a linkage object with an
    unexpected ``'type'`` key.

    `relation_name` is a string representing the name of the
    relationship for which a linkage object has a conflicting type.

    `expected_type` is a string representing the expected type of the
    related resource.

    `given_type` is is a string representing the given value of the
    ``'type'`` element in the resource.

    """

    def __init__(self, relation_name, expected_type, given_type, *args, **kw):
        super(ConflictingType, self).__init__(*args, **kw)

        #: The name of the relationship with a conflicting type.
        self.relation_name = relation_name

        #: The expected type name for the related model.
        self.expected_type = expected_type

        #: The type name given by the client for the related model.
        self.given_type = given_type

        detail = ('expected type "{0}" but got type "{1}" in linkage object'
                  ' for relationship "{2}"')
        self.detail = detail.format(expected_type, given_type, relation_name)


class UnknownField(DeserializationException):
    """Raised when attempting to deserialize an object that references a
    field that does not exist on the model.

    `field` is the name of the unknown field as a string.

    """

    #: Whether the unknown field is given as a field or a relationship.
    #:
    #: This attribute can only take one of the two values ``'field'`` or
    #: ``'relationship'``.
    field_type = None

    def __init__(self, field, *args, **kw):
        super(UnknownField, self).__init__(*args, **kw)

        #: The name of the unknown field, as a string.
        self.field = field

        self.detail = 'model has no {0} "{1}"'.format(self.field_type, field)


class UnknownRelationship(UnknownField):
    """Raised when attempting to deserialize a linkage object that
    references a relationship that does not exist on the model.

    """
    field_type = 'relationship'


class UnknownAttribute(UnknownField):
    """Raised when attempting to deserialize an object that specifies a
    field that does not exist on the model.

    """
    field_type = 'attribute'


class MissingInformation(DeserializationException):
    """Raised when a linkage object does not specify an element required by
    the JSON API specification.

    `relation_name` is the name of the relationship in which the linkage
    object is missing information.

    """

    #: The name of the key in the dictionary that is missing.
    #:
    #: Subclasses must set this class attribute.
    element = None

    def __init__(self, relation_name, *args, **kw):
        super(MissingInformation, self).__init__(*args, **kw)

        #: The relationship in which a linkage object is missing information.
        self.relation_name = relation_name

        detail = ('missing "{0}" element in linkage object for relationship'
                  ' "{1}"')
        self.detail = detail.format(self.element, relation_name)


class MissingData(MissingInformation):
    """Raised when a resource does not specify a ``'data'`` element
    where required by the JSON API specification.

    """
    element = 'data'


class MissingID(MissingInformation):
    """Raised when a resource does not specify an ``'id'`` element where
    required by the JSON API specification.

    """
    element = 'id'


class MissingType(MissingInformation):
    """Raised when a resource does not specify a ``'type'`` element
    where required by the JSON API specification.

    """
    element = 'type'


def get_column_name(column):
    """Retrieve a column name from a column attribute of SQLAlchemy model
    class, or a string.

    Raises `TypeError` when argument does not fall into either of those
    options.

    """
    # TODO use inspection API here
    if hasattr(column, '__clause_element__'):
        clause_element = column.__clause_element__()
        if not isinstance(clause_element, Column):
            msg = 'Expected a column attribute of a SQLAlchemy ORM class'
            raise TypeError(msg)
        return clause_element.key
    return column


def create_relationship(model, instance, relation):
    """Creates a relationship from the given relation name.

    Returns a dictionary representing a relationship as described in
    the `Relationships`_ section of the JSON API specification.

    .. _Relationships: http://jsonapi.org/format/#document-resource-object-relationships

    """
    result = {}
    # Create the self and related links.
    pk_value = primary_key_value(instance)
    self_link = url_for(model, pk_value, relation, relationship=True)
    related_link = url_for(model, pk_value, relation)
    result['links'] = {'self': self_link}
    # HACK If the user has not created a GET endpoint for the related
    # resource, then there is no "related" link to provide. However,
    # `url_for` is not smart enough to know this, so it may return a
    # link that interprets the `resource_id` and `relation_name`
    # arguments as query parameters. As a workaround, we look to see if
    # those query parameters appear in the URL and if so, we don't
    # include the related link.
    #
    # TODO Check if the user has created a fetch endpoint for the
    # related model, and if so, then add a "related" link.
    has_related_fetch_endpoint = not ('resource_id=' in related_link and
                                      'relation_name=' in related_link)
    if has_related_fetch_endpoint:
        result['links']['related'] = related_link
    # Get the related value so we can see if it is a to-many
    # relationship or a to-one relationship.
    related_value = getattr(instance, relation)
    # If the related value is list-like, it represents a to-many
    # relationship.
    if is_like_list(instance, relation):
        # For the sake of brevity, rename these functions.
        cn = collection_name
        gm = get_model
        pkv = primary_key_value
        # Create the resource linkage objects.
        result['data'] = [dict(type=cn(gm(i)), id=str(pkv(i)))
                          for i in related_value]
        return result
    # At this point, we know we have a to-one relationship.
    related_model = get_related_model(model, relation)
    # If the related value is None, that means we have an empty
    # to-one relationship.
    if related_value is None:
        result['data'] = None
        return result
    # If the related value is dynamically loaded, resolve the query
    # to get the single instance in the to-one relationship.
    if isinstance(related_value, Query):
        related_value = related_value.one()
    # Create the resource linkage object for the to-one
    # relationship.
    related_type = collection_name(related_model)
    related_id = str(primary_key_value(related_value))
    result['data'] = {'type': related_type, 'id': related_id}
    return result


class Serializer(object):
    """An object that, when called, returns a dictionary representation of a
    given instance of a SQLAlchemy model.

    **This is a base class with no implementation.**

    """

    def __call__(self, instance, only=None):
        """Returns a dictionary representation of the specified instance of a
        SQLAlchemy model.

        If `only` is a list, only the fields and relationships whose names
        appear as strings in `only` should appear in the returned
        dictionary. The only exception is that the keys ``'id'`` and ``'type'``
        will always appear, regardless of whether they appear in `only`.

        **This method is not implemented in this base class; subclasses must
        override this method.**

        """
        raise NotImplementedError


class Deserializer(object):
    """An object that, when called, returns an instance of the SQLAlchemy model
    specified at instantiation time.

    `session` is the SQLAlchemy session in which to look for any related
    resources.

    `model` is the class of which instances will be created by the
    :meth:`__call__` method.

    **This is a base class with no implementation.**

    """

    def __init__(self, session, model):
        self.session = session
        self.model = model

    def __call__(self, data):
        """Creates and returns a new instance of the SQLAlchemy model specified
        in the constructor whose attributes are given by the specified
        dictionary.

        `data` must be a dictionary representation of a resource as specified
        in the JSON API specification. For more information, see the `Resource
        Objects`_ section of the JSON API specification.

        **This method is not implemented in this base class; subclasses must
        override this method.**

        .. _Resource Objects: http://jsonapi.org/format/#document-structure-resource-objects

        """
        raise NotImplementedError


class DefaultSerializer(Serializer):
    """A default implementation of a serializer for SQLAlchemy models.

    When called, this object returns a dictionary representation of a given
    SQLAlchemy instance that meets the requirements of the JSON API
    specification.

    If `only` is a list, only these fields and relationships will in the
    returned dictionary. The only exception is that the keys ``'id'`` and
    ``'type'`` will always appear, regardless of whether they appear in `only`.
    These settings take higher priority than the `only` list provided to the
    :meth:`__call__` method: if an attribute or relationship appears in the
    `only` argument to :meth:`__call__` but not here in the constructor, it
    will not appear in the returned dictionary.

    If `exclude` is a list, these fields and relationships will **not** appear
    in the returned dictionary.

    If `additional_attributes` is a list, these attributes of the instance to
    be serialized will appear in the returned dictionary. This is useful if
    your model has an attribute that is not a SQLAlchemy column but you want it
    to be exposed.

    If both `only` and `exclude` are specified, a :exc:`ValueError` is raised.
    Also, if any attributes specified in `additional_attributes` appears in
    `exclude`, a :exc:`ValueError` is raised.

    """

    def __init__(self, only=None, exclude=None, additional_attributes=None,
                 **kw):
        super(DefaultSerializer, self).__init__(**kw)
        if only is not None and exclude is not None:
            raise ValueError('Cannot specify both `only` and `exclude` keyword'
                             ' arguments simultaneously')
        if (additional_attributes is not None and exclude is not None and
                any(attr in exclude for attr in additional_attributes)):
            raise ValueError('Cannot exclude attributes listed in the'
                             ' `additional_attributes` keyword argument')
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

    def __call__(self, instance, only=None):
        """Returns a dictionary representing the fields of the specified
        instance of a SQLAlchemy model.

        The returned dictionary is suitable as an argument to
        :func:`flask.jsonify`; datetime objects (:class:`datetime.date`,
        :class:`datetime.time`, :class:`datetime.datetime`, and
        :class:`datetime.timedelta`) as well as :class:`uuid.UUID`
        objects are converted to string representations, so no special
        JSON encoder behavior is required.

        If `only` is a list, only the fields and relationships whose
        names appear as strings in `only` will appear in the resulting
        dictionary. This filter is applied *after* the default fields
        specified in the `only` keyword argument to the constructor of
        this class, so only fields that appear in both `only` keyword
        arguments will appear in the returned dictionary. The only
        exception is that the keys ``'id'`` and ``'type'`` will always
        appear, regardless of whether they appear in `only`.

        Since this function creates absolute URLs to resources linked to the
        given instance, it must be called within a `Flask request context`_.

        .. _Flask request context: http://flask.pocoo.org/docs/0.10/reqcontext/

        """
        # Always include at least the type, ID, and the self link, regardless
        # of what the user requested.
        if only is not None:
            # TODO Should the 'self' link be mandatory as well?
            # TODO In Python 2.7 or later, this should be a set literal.
            only = set(only) | set(['type', 'id'])
        model = type(instance)
        try:
            inspected_instance = inspect(model)
        except NoInspectionAvailable:
            return instance
        column_attrs = inspected_instance.column_attrs.keys()
        descriptors = inspected_instance.all_orm_descriptors.items()
        # hybrid_columns = [k for k, d in descriptors
        #                   if d.extension_type == hybrid.HYBRID_PROPERTY
        #                   and not (deep and k in deep)]
        hybrid_columns = [k for k, d in descriptors
                          if d.extension_type == HYBRID_PROPERTY]
        columns = column_attrs + hybrid_columns
        # Also include any attributes specified by the user.
        if self.additional_attributes is not None:
            columns += self.additional_attributes

        # Only include fields allowed by the user during the instantiation of
        # this object.
        if self.default_fields is not None:
            columns = (c for c in columns if c in self.default_fields)
        # If `only` is a list, only include those columns that are in the list.
        if only is not None:
            columns = (c for c in columns if c in only)

        # Exclude columns specified by the user during the instantiation of
        # this object.
        if self.exclude is not None:
            columns = (c for c in columns if c not in self.exclude)
        # Exclude column names that are blacklisted.
        columns = (c for c in columns
                   if not c.startswith('__') and c not in COLUMN_BLACKLIST)
        # Exclude column names that are foreign keys.
        foreign_key_columns = foreign_keys(model)
        columns = (c for c in columns if c not in foreign_key_columns)

        # Create a dictionary mapping attribute name to attribute value for
        # this particular instance.
        #
        # TODO In Python 2.7 and later, this should be a dict comprehension.
        attributes = dict((column, getattr(instance, column))
                          for column in columns)
        # Call any functions that appear in the result.
        #
        # TODO In Python 2.7 and later, this should be a dict comprehension.
        attributes = dict((k, (v() if callable(v) else v))
                          for k, v in attributes.items())
        # Serialize any date- or time-like objects that appear in the
        # attributes.
        #
        # TODO In Flask 1.0, the default JSON encoder for the Flask
        # application object does this automatically. Alternately, the
        # user could have set a smart JSON encoder on the Flask
        # application, which would cause these attributes to be
        # converted to strings when the Response object is created (in
        # the `jsonify` function, for example). However, we should not
        # rely on that JSON encoder since the user could set any crazy
        # encoder on the Flask application.
        for key, val in attributes.items():
            if isinstance(val, (date, datetime, time)):
                attributes[key] = val.isoformat()
            elif isinstance(val, timedelta):
                attributes[key] = total_seconds(val)
        # Recursively serialize any object that appears in the
        # attributes. This may happen if, for example, the return value
        # of one of the callable functions is an instance of another
        # SQLAlchemy model class.
        for k, v in attributes.items():
            # This is a bit of a fragile test for whether the object
            # needs to be serialized: we simply check if the class of
            # the object is a mapped class.
            if is_mapped_class(type(v)):
                attributes[k] = simple_serialize(v)
        # Get the ID and type of the resource.
        id_ = attributes.pop('id')
        type_ = collection_name(model)
        # Create the result dictionary and add the attributes.
        result = dict(id=id_, type=type_)
        if attributes:
            result['attributes'] = attributes
        # Add the self link unless it has been explicitly excluded.
        if ((self.default_fields is None or 'self' in self.default_fields)
                and (only is None or 'self' in only)):
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

        # Recursively serialize values that are themselves SQLAlchemy
        # models.
        #
        # TODO We really need to serialize each model using the
        # serializer defined for that class when the user called
        # APIManager.create_api
        for key, value in result.items():
            if key not in column_attrs and is_mapped_class(type(value)):
                result[key] = simple_serialize(value)
        # If the primary key is not named "id", we'll duplicate the
        # primary key under the "id" key.
        pk_name = primary_key_name(model)
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
        # If there are relations to convert to dictionary form, put them into a
        # special `links` key as required by JSON API.
        relations = get_relations(model)
        if self.default_fields is not None:
            relations = [r for r in relations if r in self.default_fields]
        # Only consider those relations listed in `only`.
        if only is not None:
            relations = [r for r in relations if r in only]
        # Exclude relations specified by the user during the instantiation of
        # this object.
        if self.exclude is not None:
            relations = [r for r in relations if r not in self.exclude]
        if not relations:
            return result
        # For the sake of brevity, rename this function.
        cr = create_relationship
        # TODO In Python 2.7 and later, this should be a dict comprehension.
        result['relationships'] = dict((rel, cr(model, instance, rel))
                                       for rel in relations)
        return result


# TODO Create a DefaultRelationshipDeserializer!
class DefaultRelationshipSerializer(Serializer):
    """A default implementation of a serializer for resource identifier
    objects for use in relationship objects in JSON API documents.

    This serializer differs from the default serializer for resources
    since it only provides an ``'id'`` and a ``'type'`` in the
    dictionary returned by the :meth:`__call__` method.

    """

    def __call__(self, instance, only=None, _type=None):
        if _type is None:
            _type = collection_name(get_model(instance))
        return {'id': str(primary_key_value(instance)), 'type': _type}


class DefaultDeserializer(Deserializer):
    """A default implementation of a deserializer for SQLAlchemy models.

    When called, this object returns an instance of a SQLAlchemy model with
    fields and relations specified by the provided dictionary.

    """

    def __call__(self, data):
        """Creates and returns an instance of the SQLAlchemy model specified in
        the constructor.

        For more information, see the documentation for the
        :meth:`Deserializer.__call__` method.

        """
        # Check for any request parameter naming a column which does not exist
        # on the current model.
        for field in data:
            if field == 'relationships':
                for relation in data['relationships']:
                    if not has_field(self.model, relation):
                        raise UnknownRelationship(relation)
            elif field == 'attributes':
                for attribute in data['attributes']:
                    if not has_field(self.model, attribute):
                        raise UnknownAttribute(attribute)
        # Determine which related instances need to be added.
        links = {}
        if 'relationships' in data:
            links = data.pop('relationships', {})
            for link_name, link_object in links.items():
                if 'data' not in link_object:
                    raise MissingData(link_name)
                linkage = link_object['data']
                related_model = get_related_model(self.model, link_name)
                expected_type = collection_name(related_model)
                # If this is a to-many relationship, get all the instances.
                if isinstance(linkage, list):
                    related_instances = []
                    for rel in linkage:
                        if 'id' not in rel:
                            raise MissingID(link_name)
                        if 'type' not in rel:
                            raise MissingType(link_name)
                        type_ = rel['type']
                        if type_ != expected_type:
                            raise ConflictingType(link_name, expected_type,
                                                  type_)
                        id_ = rel['id']
                        related_instance = get_by(self.session, related_model,
                                                  id_)
                        related_instances.append(related_instance)
                    links[link_name] = related_instances
                # Otherwise, if this is a to-one relationship, just get a
                # single instance.
                else:
                    if 'id' not in linkage:
                        raise MissingID(link_name)
                    if 'type' not in linkage:
                        raise MissingType(link_name)
                    type_ = linkage['type']
                    if type_ != expected_type:
                        raise ConflictingType(link_name, expected_type, type_)
                    id_ = linkage['id']
                    related_instance = get_by(self.session, related_model, id_)
                    links[link_name] = related_instance
        # TODO Need to check here if any related instances are None,
        # like we do in the patch() method. We could possibly refactor
        # the code above and the code there into a helper function...
        pass
        # Move the attributes up to the top level.
        data.update(data.pop('attributes', {}))
        # Special case: if there are any dates, convert the string form of the
        # date into an instance of the Python ``datetime`` object.
        data = strings_to_datetimes(self.model, data)
        # Create the new instance by keyword attributes.
        instance = self.model(**data)
        # Set each relation specified in the links.
        for relation_name, related_value in links.items():
            setattr(instance, relation_name, related_value)
        return instance


#: Provides basic, uncustomized serialization functionality as provided by
#: :class:`DefaultSerializer`.
#:
#: This function is suitable for calling on its own, no other instantiation or
#: customization necessary.
simple_serialize = DefaultSerializer()


#: Basic serializer for relationship objects.
#:
#: This function is suitable for calling on its own, no other instantiation or
#: customization necessary.
simple_relationship_serialize = DefaultRelationshipSerializer()
