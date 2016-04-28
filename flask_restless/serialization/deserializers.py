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
Flask-Restless code.

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
from ..helpers import strings_to_datetimes


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

        .. _Resource Objects: http://jsonapi.org/format/#document-structure-resource-objects

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

        .. _Resource Objects: http://jsonapi.org/format/#document-structure-resource-objects

        """
        raise NotImplementedError


class DefaultDeserializer(Deserializer):
    """A default implementation of a deserializer for SQLAlchemy models.

    When called, this object returns an instance of a SQLAlchemy model
    with fields and relations specified by the provided dictionary.

    """

    def __init__(self, session, model, allow_client_generated_ids=False, **kw):
        super(DefaultDeserializer, self).__init__(session, model, **kw)

        #: Whether to allow client generated IDs.
        self.allow_client_generated_ids = allow_client_generated_ids

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
        if 'type' not in data:
            raise MissingType
        if 'id' in data and not self.allow_client_generated_ids:
            raise ClientGeneratedIDNotAllowed
        type_ = data.pop('type')
        expected_type = collection_name(self.model)
        if type_ != expected_type:
            raise ConflictingType(expected_type, type_)
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
                related_model = get_related_model(self.model, link_name)
                DRD = DefaultRelationshipDeserializer
                deserializer = DRD(self.session, related_model, link_name)
                # Create the deserializer for this relationship object.
                if is_like_list(self.model, link_name):
                    deserialize = deserializer.deserialize_many
                else:
                    deserialize = deserializer.deserialize
                # This may raise a DeserializationException or
                # MultipleExceptions.
                links[link_name] = deserialize(link_object)
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

    def deserialize(self, document):
        """Creates and returns an instance of the SQLAlchemy model
        specified in the JSON API document.

        Everything in the `document` other than the `data` element is
        ignored.

        For more information, see the documentation for the
        :meth:`Deserializer.deserialize` method.

        """
        if 'data' not in document:
            raise MissingData
        data = document['data']
        return self._load(data)

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


class DefaultRelationshipDeserializer(Deserializer):
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

    def _load(self, data):
        """Gets the resource associated with the given resource
        identifier object.

        `data` must be a dictionary containing exactly two elements,
        ``'type'`` and ``'id'``, or a list of dictionaries of that
        form. In the former case, the `data` represents a to-one
        relation and in the latter a to-many relation.

        Returns the instance or instances of the SQLAlchemy model
        specified in the constructor whose ID or IDs match the given
        `data`.

        May raise :exc:`MissingID`, :exc:`MissingType`, or
        :exc:`ConflictingType`.

        """
        # If this is a to-one relationship, get the sole instance of the model.
        if 'id' not in data:
            raise MissingID(self.relation_name)
        if 'type' not in data:
            raise MissingType(self.relation_name)
        type_ = data['type']
        if type_ != self.type_name:
            raise ConflictingType(self.relation_name, self.type_name,
                                  type_)
        id_ = data['id']
        return get_by(self.session, self.model, id_)

    def deserialize(self, document):
        """Returns the SQLAlchemy instance identified by the resource
        identifier given as the primary data in the given document.

        The type given in the resource identifier must match the
        collection name associated with the SQLAlchemy model specified
        in the constructor of this class. If not, this raises
        :exc:`ConflictingType`.

        """
        if 'data' not in document:
            raise MissingData(self.relation_name)
        resource_identifier = document['data']
        return self._load(resource_identifier)

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
