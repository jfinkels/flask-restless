# exceptions.py - serialization exceptions
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
"""Exceptions that arise from serialization or deserialization."""


class SerializationException(Exception):
    """Raised when there is a problem serializing an instance of a
    SQLAlchemy model to a dictionary representation.

    `instance` is the (problematic) instance on which
    :meth:`DefaultSerializer.serialize` was invoked.

    `message` is an optional string describing the problem in more
    detail.

    `resource` is an optional partially-constructed serialized
    representation of ``instance``.

    Each of these keyword arguments is stored in a corresponding
    instance attribute so client code can access them.

    """

    def __init__(self, instance, message=None, resource=None, *args, **kw):
        super(SerializationException, self).__init__(*args, **kw)
        self.resource = resource
        self.message = message
        self.instance = instance


class MultipleExceptions(Exception):
    """Raised when there are multiple problems in serialization or
    deserialization.

    `exceptions` is a non-empty sequence of other exceptions that have
    been raised in the code.

    You may wish to raise this exception when implementing the
    :meth:`DefaultSerializer.serialize_many` method, for example, if
    there are multiple exceptions

    """

    def __init__(self, exceptions, *args, **kw):
        super(MultipleExceptions, self).__init__(*args, **kw)

        #: Sequence of other exceptions that have been raised in the code.
        self.exceptions = exceptions


class DeserializationException(Exception):
    """Raised when there is a problem deserializing a Python dictionary to an
    instance of a SQLAlchemy model.

    `status` is an integer representing the HTTP status code that
    corresponds to this error. If not specified, it is set to 400,
    representing :http:statuscode:`400`.

    `detail` is a string describing the problem in more detail. If
    provided, this will be incorporated in the return value of
    :meth:`.message`.

    Each of the keyword arguments `status` and `detail` are assigned
    directly to instance-level attributes :attr:`status` and
    :attr:`detail`.

    """

    def __init__(self, status=400, detail=None, *args, **kw):
        super(DeserializationException, self).__init__(*args, **kw)

        #: A string describing the problem in more detail.
        self.detail = detail

        #: The HTTP status code corresponding to this error.
        self.status = status

    def message(self):
        """Returns a more detailed description of the problem as a
        string.

        """
        base = 'Failed to deserialize object'
        if self.detail is not None:
            return '{0}: {1}'.format(base, self.detail)
        return base


class NotAList(DeserializationException):
    """Raised when a ``data`` element exists but is not a list when it
    should be, as when deserializing a to-many relationship.

    """

    def __init__(self, relation_name=None, *args, **kw):
        # # For now, this is only raised when calling deserialize_many()
        # # on a relationship, so this extra message should always be
        # # inserted.
        # if relation_name is not None:
        inner = ('in linkage for relationship "{0}" ').format(relation_name)
        # else:
        #     inner = ''

        detail = ('"data" element {0}must be a list when calling'
                  ' deserialize_many(); maybe you meant to call'
                  ' deserialize()?').format(inner)

        super(NotAList, self).__init__(detail=detail, *args, **kw)


class ClientGeneratedIDNotAllowed(DeserializationException):
    """Raised when attempting to deserialize a resource that provides
    an ID when an ID is not allowed.

    """

    def __init__(self, *args, **kw):
        detail = 'Server does not allow client-generated IDS'
        sup = super(ClientGeneratedIDNotAllowed, self)
        sup.__init__(status=403, detail=detail, *args, **kw)


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

    def __init__(self, expected_type, given_type, relation_name=None, *args,
                 **kw):
        if relation_name is None:
            inner = ''
        else:
            inner = (' in linkage object for relationship'
                     ' "{0}"').format(relation_name)
        detail = 'expected type "{0}" but got type "{1}"{2}'
        detail = detail.format(expected_type, given_type, inner)
        sup = super(ConflictingType, self)
        sup.__init__(status=409, detail=detail, *args, **kw)


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
        detail = 'model has no {0} "{1}"'.format(self.field_type, field)
        super(UnknownField, self).__init__(detail=detail, *args, **kw)


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

    def __init__(self, relation_name=None, *args, **kw):
        #: The relationship in which a linkage object is missing information.
        self.relation_name = relation_name

        if relation_name is not None:
            inner = (' in linkage object for relationship'
                     ' "{0}"').format(relation_name)
        else:
            inner = ''
        detail = 'missing "{0}" element{1}'.format(self.element, inner)
        super(MissingInformation, self).__init__(detail=detail, *args, **kw)


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
