# deserializers.py - SQLAlchemy deserializers for JSON documents
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
"""Classes for deserialization of JSON API documents to SQLAlchemy.

The abstract base class :class:`Deserializer` can be used to implement
custom deserialization from JSON API documents to SQLAlchemy
objects. The :class:`DefaultDeserializer` provide some basic
deserialization as expected by classes that follow the JSON API
protocol.

The implementations here are closely coupled to the rest of the
Flask-Restless code. Specifically, they use global helper functions
(like :func:`.model_for`) that rely on information provided to the
:class:`.APIManager` at the time of API creation.

"""
from .exceptions import ClientGeneratedIDNotAllowed
from .exceptions import ConflictingType
from .exceptions import DeserializationException
from .exceptions import MissingData
from .exceptions import MissingID
from .exceptions import MissingType
from .exceptions import MultipleExceptions
from .exceptions import NotAList
from .exceptions import UnknownRelationship
from .exceptions import UnknownAttribute
from ..helpers import collection_name
from ..helpers import get_related_model
from ..helpers import get_by
from ..helpers import has_field
from ..helpers import is_like_list
from ..helpers import model_for
from ..helpers import primary_key_for
from ..helpers import string_to_datetime as to_datetime


class Deserializer(object):
    """An object that transforms a dictionary representation of a JSON
    API document into an instance or instances of the SQLAlchemy model
    specified at instantiation time.

    `session` is the SQLAlchemy session in which to look for any related
    resources.

    `model` is the class of which instances will be created by the
    :meth:`.deserialize` and :meth:`.deserialize_many` methods.

    **This is a base class with no implementation.**

    """

    def __init__(self, session, model):
        self.session = session
        self.model = model

    def deserialize(self, document):
        """Creates and returns a new instance of the SQLAlchemy model
        specified in the constructor whose attributes are given by the
        specified dictionary.

        `document` must be a dictionary representation of a JSON API
        document containing a single resource as primary data, as
        specified in the JSON API specification. For more information,
        see the `Resource Objects`_ section of the JSON API
        specification.

        **This method is not implemented in this base class; subclasses
        must override this method.**

        .. _Resource Objects:
           http://jsonapi.org/format/#document-structure-resource-objects

        """
        raise NotImplementedError

    def deserialize_many(self, document):
        """Creates and returns a list of instances of the SQLAlchemy
        model specified in the constructor whose fields are given in the
        JSON API document.

        `document` must be a dictionary representation of a JSON API
        document containing a list of resources as primary data, as
        specified in the JSON API specification. For more information,
        see the `Resource Objects`_ section of the JSON API
        specification.

        **This method is not implemented in this base class; subclasses
        must override this method.**

        .. _Resource Objects:
           http://jsonapi.org/format/#document-structure-resource-objects

        """
        raise NotImplementedError


class DeserializerBase(Deserializer):

    def __init__(self, session, model):
        super(DeserializerBase, self).__init__(session, model)

        self.relation_name = None

    def _check_type_and_id(self, data):
        """Check that an object has a valid type and ID.

        `data` is a dictionary representation of a JSON API resource
        object or a resource identifier object. This method does not
        return anything, but implementing subclasses may raise an
        exception here, for example if the ``type`` key is missing.

        This is an abstract method; concrete subclasses must override
        and implement it.

        """
        raise NotImplementedError

    def _resource_to_model(self, data):
        """Get the SQLAlchemy model for the type of the given resource.

        `data` is a dictionary representation of a JSON API resource
        object. This method returns the SQLAlchemy model class
        corresponding to the resource type given in the ``type`` key of
        the resource object.

        This method raises :exc:`ConflictingType` if the type of the
        resource object does not match the SQLAlchemy model specified in
        the constructor of this class (that is, the
        :attr:`.Deserializer.model` instance attribute).

        """
        type_ = data['type']
        expected_type = collection_name(self.model)
        try:
            model = model_for(type_)
        except ValueError:
            raise ConflictingType(expected_type, type_, self.relation_name)
        # If we wanted to allow deserializing a subclass of the model,
        # we could use:
        #
        #     if not issubclass(model, self.model) and type != expected_type:
        #
        if type_ != expected_type:
            raise ConflictingType(expected_type, type_, self.relation_name)
        return model

    def _check_unknown_fields(self, data):
        """Check for any unknown fields in an object.

        `data` is a dictionary representation of a JSON API resource
        object or resource identifier object.

        `model` is a SQLAlchemy model class. The `data` object should
        represent an instance of `model`.

        This method does not return anything, but implementing
        subclasses may raise an exception here, for example if `data`
        includes a field that does not exist on `model`.

        This is an abstract method; concrete subclasses must override
        and implement it.

        """
        raise NotImplementedError

    def _extract_attributes(self, data, model):
        """Generate the attributes given in an object.

        `data` is a dictionary representation of a JSON API resource
        object or resource identifier object.

        `model` is a SQLAlchemy model class. The `data` object should
        represent an instance of `model`.

        This method is an iterator generator. It yields pairs in which
        the left element is a string naming an attribute and the right
        element is the value of the attribute to assign to the instance
        of `model` being deserialized. The attributes are passed along
        to the :meth:`._get_or_create` method.

        This is an abstract method; concrete subclasses must override
        and implement it.

        """
        raise NotImplementedError

    def _get_or_create(self, model, attributes):
        """Get or create an instance of a model with the given attributes.

        `model` is a SQLAlchemy model class. `attributes` is a
        dictionary in which keys are strings naming instance attributes
        of `model` and values are the values to assign to those
        attributes.

        This method may return either a new instance or an existing
        instance of the given model that has the given attributes.

        If an implementing subclass returns an existing instance, it
        should (but is not obligated to) yield at least a pair of the
        form ``(pk_name, pk_value)``, where ``pk_name`` is a string
        naming the primary key attribute of `model` and ``pk_value`` is
        the primary key value as it appears in `data`.

        This is an abstract method; concrete subclasses must override
        and implement it.

        """
        raise NotImplementedError

    def _load_related_resources(self, data, model):
        """Generate identifiers for related resources, if necessary.

        This method is only relevant for subclasses that deserialize
        resource objects, not for subclasses that deserialize resource
        identifier objects (since resource identifier objects do not
        contain any relationship information).

        `data` is a dictionary representation of a JSON API resource
        object.

        `model` is a SQLAlchemy model class. The `data` resource object
        should represent an instance of `model`.

        This method is an iterator generator. It yields pairs in which
        the left element is a string naming a relationship and the right
        element is a deserialized version of the JSON API resource
        identifiers of the relationship. For a to-one relationship, this
        is just a single SQLAlchemy model instance. For a to-many
        relationship, it is a list of SQLAlchemy model instances.

        For example::

            >>> # session = ...
            >>> # class Article(Base): ...
            >>> deserializer = DefaultDeserializer(session, Article)
            >>> data = {
            ...     'relationships': {
            ...         'comments': [
            ...             {'type': 'comment', 'id': 1}
            ...         ],
            ...         'author': {'type': 'person', 'id': 1}
            ...     }
            ... }
            >>> rels = deserializer._load_related_resources(data, Article)
            >>> for name, obj in sorted(rels):
            ...     print(name, obj)
            author <Person object at 0x...>
            comments [<Comment object at 0x...>]

        This method raises :exc:`DeserializationException` or
        :exc:`MultipleExceptions` if there is a problem deserializing
        any of the related resources.

        This is an abstract method; concrete subclasses must override
        and implement it.

        """
        raise NotImplementedError

    def _assign_related_resources(self, instance, related_resources):
        """Assign related resources to a given instance of a SQLAlchemy model.

        This method is only relevant for subclasses that deserialize
        resource objects, not for subclasses that deserialize resource
        identifier objects (since resource identifier objects do not
        contain any relationship information).

        `instance` is an instance of a SQLAlchemy model class.
        `related_resources` is a dictionary whose keys are strings
        naming relationships of the SQLAlchemy model and whose values
        are the corresponding relationship values.

        This method does not return anything but modifies `instance` by
        setting the value of the attributes named by
        `related_resources`.

        This is an abstract method; concrete subclasses must override
        and implement it.

        """
        raise NotImplementedError

    def _load(self, data):
        """Returns a new instance of a SQLAlchemy model represented by
        the given resource object.

        `data` is a dictionary representation of a JSON API resource
        object.

        This method may raise one of various
        :exc:`DeserializationException` subclasses. If the instance has
        a to-many relationship, this method may raise
        :exc:`MultipleExceptions` as well, if there are multiple
        exceptions when deserializing the related instances.

        """
        self._check_type_and_id(data)
        model = self._resource_to_model(data)
        self._check_unknown_fields(data, model)
        attributes = self._extract_attributes(data, model)
        instance = self._get_or_create(model, dict(attributes))
        related_resources = self._load_related_resources(data, model)
        # TODO Need to check here if any related instances are None,
        # like we do in the patch() method. We could possibly refactor
        # the code above and the code there into a helper function...
        self._assign_related_resources(instance, dict(related_resources))
        return instance

    def deserialize(self, document):
        """Creates and returns a new instance of the SQLAlchemy model specified
        in the constructor whose attributes are given in the JSON API
        document.

        `document` must be a dictionary representation of a JSON API
        document containing a single resource as primary data, as
        specified in the JSON API specification. For more information,
        see the `Resource Objects`_ section of the JSON API
        specification.

        *Implementation note:* everything in the document other than the
        ``data`` element is ignored.

        .. _Resource Objects:
           http://jsonapi.org/format/#document-structure-resource-objects

        """
        if 'data' not in document:
            raise MissingData(self.relation_name)
        data = document['data']
        return self._load(data)


class DefaultDeserializer(DeserializerBase):
    """A default implementation of a deserializer for SQLAlchemy models.

    When called, this object returns an instance of a SQLAlchemy model
    with fields and relations specified by the provided dictionary.

    """

    def __init__(self, session, model, allow_client_generated_ids=False, **kw):
        super(DefaultDeserializer, self).__init__(session, model, **kw)

        #: Whether to allow client generated IDs.
        self.allow_client_generated_ids = allow_client_generated_ids

    def _check_type_and_id(self, data):
        """Check that the resource object has a valid type and ID.

        `data` is a dictionary representation of a JSON API resource
        object. This method does not return anything, but raises
        :exc:`MissingType` if the ``type`` key is missing and
        :exc:`ClientGeneratedIDNotAllowed` if the ``id`` key is present
        when not allowed.

        """
        if 'type' not in data:
            raise MissingType
        if 'id' in data and not self.allow_client_generated_ids:
            raise ClientGeneratedIDNotAllowed

    def _check_unknown_fields(self, data, model):
        """Check for any unknown fields in a resource object.

        `data` is a dictionary representation of a JSON API resource
        object.

        `model` is a SQLAlchemy model class. The `data` resource should
        represent an instance of `model`.

        This method does not return anything, but raises
        :exc:`UnknownRelationship` or :exc:`UnknownAttribute` if any
        relationship or attribute, respectively, does not exist on the
        given model.

        """
        for relation in data.get('relationships', []):
            if not has_field(model, relation):
                raise UnknownRelationship(relation)
        for attribute in data.get('attributes', []):
            if not has_field(model, attribute):
                raise UnknownAttribute(attribute)

    def _load_related_resources(self, data, model):
        """Generate identifiers for related resources.

        `data` is a dictionary representation of a JSON API resource
        object.

        `model` is a SQLAlchemy model class. The `data` resource should
        represent an instance of `model`.

        This method is an iterator generator. It yields pairs in which
        the left element is a string naming a relationship and the right
        element is a deserialized version of the JSON API resource
        identifiers of the relationship. For a to-one relationship, this
        is just a single SQLAlchemy model instance. For a to-many
        relationship, it is a list of SQLAlchemy model instances.

        For example::

            >>> # session = ...
            >>> # class Article(Base): ...
            >>> deserializer = DefaultDeserializer(session, Article)
            >>> data = {
            ...     'relationships': {
            ...         'comments': [
            ...             {'type': 'comment', 'id': 1}
            ...         ],
            ...         'author': {'type': 'person', 'id': 1}
            ...     }
            ... }
            >>> rels = deserializer._load_related_resources(data, Article)
            >>> for name, obj in sorted(rels):
            ...     print(name, obj)
            author <Person object at 0x...>
            comments [<Comment object at 0x...>]

        This method raises :exc:`DeserializationException` or
        :exc:`MultipleExceptions` if there is a problem deserializing
        any of the related resources.

        """
        for link_name, link_object in data.get('relationships', {}).items():
            related_model = get_related_model(model, link_name)
            # Create the deserializer for this relationship object and
            # decide whether we need to deserialize a to-one
            # relationship or a to-many relationship.
            #
            # These may raise a DeserializationException or
            # MultipleExceptions.
            DRD = DefaultRelationshipDeserializer
            deserializer = DRD(self.session, related_model, link_name)
            if is_like_list(model, link_name):
                deserialize = deserializer.deserialize_many
            else:
                deserialize = deserializer.deserialize
            yield link_name, deserialize(link_object)

    def _extract_attributes(self, data, model):
        """Generate the attributes given in the resource object.

        `data` is a dictionary representation of a JSON API resource
        object.

        `model` is a SQLAlchemy model class. The `data` resource should
        represent an instance of `model`.

        This method is an iterator generator. It yields pairs in which
        the left element is a string naming an attribute and the right
        element is the value of the attribute to assign to the instance
        of `model` being created.

        This method yields the attributes as-is from the resource object
        given in `data`, with the exception that strings are parsed into
        :class:`datetime.date` or :class:`datetime.datetime` objects
        when appropriate, based on the columns of the given `model`.

        """
        # Yield the primary key name and value, if it exists.
        pk = primary_key_for(model)
        if pk in data:
            yield pk, data[pk]
        for k, v in data.get('attributes', {}).items():
            # Special case: if there are any dates, convert the string
            # form of the date into an instance of the Python
            # ``datetime`` object.
            yield k, to_datetime(model, k, v)

    def _get_or_create(self, model, attributes):
        """Get or create an instance of a model with the given attributes.

        `model` is a SQLAlchemy model class. `attributes` is a
        dictionary in which keys are strings naming instance attributes
        of `model` and values are the values to assign to those
        attributes.

        This method returns a new instance of the given model (created
        using the constructor) with the given attributes set on it.

        """
        return model(**attributes)

    def _assign_related_resources(self, instance, related_resources):
        """Assign related resources to a given instance of a SQLAlchemy model.

        `instance` is an instance of a SQLAlchemy model class.
        `related_resources` is a dictionary whose keys are strings
        naming relationships of the SQLAlchemy model and whose values
        are the corresponding relationship values.

        This method does not return anything but modifies `instance` by
        setting the value of the attributes named by
        `related_resources`.

        """
        for relation_name, related_value in related_resources.items():
            setattr(instance, relation_name, related_value)

    # # TODO JSON API currently doesn't support bulk creation of resources,
    # # so this code cannot be accurately used/tested.
    # def deserialize_many(self, document):
    #     """Creates and returns a list of instances of the SQLAlchemy
    #     model specified in the constructor whose fields are given in the
    #     JSON API document.
    #
    #     This method assumes that each resource in the given document is
    #     of the same type.
    #
    #     For more information, see the documentation for the
    #     :meth:`Deserializer.deserialize_many` method.
    #
    #     """
    #     if 'data' not in document:
    #         raise MissingData
    #     data = document['data']
    #     if not isinstance(data, list):
    #         raise NotAList
    #     # Since loading each instance from a given resource object
    #     # representation could theoretically raise a
    #     # DeserializationException, we collect all the errors and wrap
    #     # them in a MultipleExceptions exception object.
    #     result = []
    #     failed = []
    #     for resource in data:
    #         try:
    #             instance = self._load(resource)
    #             result.append(instance)
    #         except DeserializationException as exception:
    #             failed.append(exception)
    #     if failed:
    #         raise MultipleExceptions(failed)
    #     return result


class DefaultRelationshipDeserializer(DeserializerBase):
    """A default implementation of a deserializer for resource
    identifier objects for use in relationships in JSON API documents.

    Each instance of this class should correspond to a particular
    relationship of a model.

    This deserializer differs from the default deserializer for
    resources since it expects that the ``'data'`` element of the input
    dictionary to :meth:`.deserialize` contains only ``'id'`` and
    ``'type'`` keys.

    `session` is the SQLAlchemy session in which to look for any related
    resources.

    `model` is the SQLAlchemy model class of the relationship, *not the
    primary resource*. With the related model class, this deserializer
    will be able to use the ID provided to the :meth:`__call__` method
    to determine the instance of the `related_model` class which is
    being deserialized.

    `relation_name` is the name of the relationship being deserialized,
    given as a string. This is used mainly for more helpful error
    messages.

    """

    def __init__(self, session, model, relation_name=None):
        super(DefaultRelationshipDeserializer, self).__init__(session, model)
        #: The related model whose objects this deserializer will return
        #: in the :meth:`__call__` method.
        self.model = model

        #: The collection name given to the related model.
        self.type_name = collection_name(self.model)

        #: The name of the relationship being deserialized, as a string.
        self.relation_name = relation_name

    def _check_type_and_id(self, data):
        """Check that the resource identifier object has a valid type and ID.

        `data` is a dictionary representation of a JSON API resource
        identifier object. This method does not return anything, but
        raises :exc:`MissingType` if the ``type`` key is missing and
        :exc:`MissingID` if the ``id`` key is missing.

        """
        if 'type' not in data:
            raise MissingType(self.relation_name)
        if 'id' not in data:
            raise MissingID(self.relation_name)

    def _check_unknown_fields(self, data, model):
        """Do nothing.

        Since there are no attributes or relationships in `data`, a
        resource identifier object, there is nothing to do here.

        """
        pass

    def _extract_attributes(self, data, model):
        """Yield the primary key name/value pair of the resource identifier."""
        pk_name = primary_key_for(model)
        yield pk_name, data[pk_name]

    def _get_or_create(self, model, attributes):
        """Get a resource identified by primary key.

        `model` is a SQLAlchemy model class. `attributes` includes the
        primary key name/value pair that identifies an instance of the
        model. This method returns that instance.

        """
        pk_name = primary_key_for(model)
        pk_value = attributes[pk_name]
        return get_by(self.session, model, pk_value)

    def _load_related_resources(self, data, model):
        """Return an empty list.

        There is no relationship information for a resource identifer.

        """
        return []

    def _assign_related_resources(self, instance, related_resources):
        """Do nothing.

        Since there are no relationships in a resource identifier
        object, there is nothing to do here.

        """
        pass

    def deserialize_many(self, document):
        """Returns a list of SQLAlchemy instances identified by the
        resource identifiers given as the primary data in the given
        document.

        The type given in each resource identifier must match the
        collection name associated with the SQLAlchemy model specified
        in the constructor of this class. If not, this raises
        :exc:`ConflictingType`.

        """
        if 'data' not in document:
            raise MissingData(self.relation_name)
        resource_identifiers = document['data']
        if not isinstance(resource_identifiers, list):
            raise NotAList(self.relation_name)
        # Since loading each related instance from a given resource
        # identifier object representation could theoretically raise a
        # DeserializationException, we collect all the errors and wrap
        # them in a MultipleExceptions exception object.
        result = []
        failed = []
        for resource_identifier in resource_identifiers:
            try:
                instance = self._load(resource_identifier)
                result.append(instance)
            except DeserializationException as exception:
                failed.append(exception)
        if failed:
            raise MultipleExceptions(failed)
        return result
