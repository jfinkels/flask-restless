import datetime
try:
    from urllib.parse import urljoin
except ImportError:
    from urlparse import urljoin
import uuid

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


class SerializationException(Exception):
    """Raised when there is a problem serializing an instance of a SQLAlchemy
    model to a dictionary representation.

    """
    pass


class DeserializationException(Exception):
    """Raised when there is a problem deserializing a Python dictionary to an
    instance of a SQLAlchemy model.

    """
    pass


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


class Serializer(object):

    def __call__(self, instance, only=None):
        raise NotImplemented


class Deserializer(object):

    def __init__(self, session, model):
        self.session = session
        self.model = model

    def __call__(self, data):
        raise NotImplemented


class DefaultSerializer(Serializer):

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
            only = {get_column_name(column) for column in only}
            # TODO Should the 'self' link be mandatory as well?
            only |= {'type', 'id'}
        if exclude is not None:
            # Convert SQLAlchemy Column objects to strings if necessary.
            exclude = {get_column_name(column) for column in exclude}
        self.default_fields = only
        self.exclude = exclude
        self.additional_attributes = additional_attributes

    # TODO only=... is the client's request for which fields to include.
    def __call__(self, instance, only=None):
        """Returns a dictionary representing the fields of the specified
        instance of a SQLAlchemy model.

        The returned dictionary is suitable as an argument to
        :func:`flask.jsonify`; :class:`datetime.date` and :class:`uuid.UUID`
        objects are converted to string representations, so no special JSON
        encoder behavior is required.

        If `only` is a list, only the fields and relationships whose names
        appear as strings in `only` will appear in the resulting
        dictionary. The only exception is that the keys ``'id'`` and ``'type'``
        will always appear, regardless of whether they appear in `only`.

        Since this function creates absolute URLs to resources linked to the
        given instance, it must be called within a `Flask request context`_.

        .. _Flask request context: http://flask.pocoo.org/docs/0.10/reqcontext/

        """
        # Always include at least the type, ID, and the self link, regardless
        # of what the user requested.
        if only is not None:
            # TODO Should the 'self' link be mandatory as well?
            only = set(only) | {'type', 'id'}
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
        result = {column: getattr(instance, column) for column in columns}
        # Call any functions that appear in the result.
        result = {k: (v() if callable(v) else v) for k, v in result.items()}
        # Add the resource type to the result dictionary.
        result['type'] = collection_name(model)
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

        # TODO Should the responsibility for serializing date and uuid objects
        # move outside of this function? I think so.
        #
        # Check for objects in the dictionary that may not be serializable by
        # default.
        for key, value in result.items():
            # Convert date, time, and datetime objects to ISO 8601 format.
            if isinstance(value, (datetime.date, datetime.time)):
                result[key] = value.isoformat()
            # Convert UUIDs to hexadecimal strings.
            elif isinstance(value, uuid.UUID):
                result[key] = str(value)
            # Recurse on values that are themselves SQLAlchemy models.
            #
            # TODO really we need to serialize each model using the serializer
            # defined for that class when the user called APIManager.create_api
            elif key not in column_attrs and is_mapped_class(type(value)):
                result[key] = simple_serialize(value)
        # If the primary key is not named "id", we'll duplicate the primary key
        # under the "id" key.
        pk_name = primary_key_name(model)
        if pk_name != 'id':
            result['id'] = result[pk_name]
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
        if not relations:
            return result
        # The links mapping may already exist if a self link was added
        # above.
        if 'links' not in result:
            result['links'] = {}
        for relation in relations:
            # Create the common elements in the link object: the `self` and
            # `resource` links.
            result['links'][relation] = {}
            link = result['links'][relation]
            link['self'] = url_for(model, primary_key_value(instance),
                                   relation, relationship=True)
            link['related'] = url_for(model, primary_key_value(instance),
                                      relation)
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
                # Create the link objects.
                link['linkage'] = [dict(type=cn(gm(i)), id=str(pkv(i)))
                                   for i in related_value]
                continue
            # At this point, we know we have a to-one relationship.
            related_model = get_related_model(model, relation)
            link['linkage'] = dict(type=collection_name(related_model))
            # If the related value is None, that means we have an empty
            # to-one relationship.
            if related_value is None:
                link['linkage']['id'] = None
                continue
            # If the related value is dynamically loaded, resolve the query
            # to get the single instance in the to-one relationship.
            if isinstance(related_value, Query):
                related_value = related_value.one()
            link['linkage']['id'] = str(primary_key_value(related_value))
        return result


simple_serialize = DefaultSerializer()


class DefaultDeserializer(Deserializer):

    def __call__(self, data):
        """Returns an instance of the model with the specified attributes."""
        # Check for any request parameter naming a column which does not exist
        # on the current model.
        for field in data:
            if field == 'links':
                for relation in data['links']:
                    if not has_field(self.model, relation):
                        msg = ('Model does not have relationship'
                               ' "{0}"').format(relation)
                        raise DeserializationException(msg)
            elif not has_field(self.model, field):
                msg = "Model does not have field '{0}'".format(field)
                raise DeserializationException(msg)
        # Determine which related instances need to be added.
        links = {}
        if 'links' in data:
            links = data.pop('links', {})
            for link_name, link_object in links.items():
                # TODO raise an exception on missing 'linkage' key
                linkage = link_object['linkage']
                related_model = get_related_model(self.model, link_name)
                # TODO check for type conflicts
                #
                # If this is a to-many relationship, get all the instances.
                if isinstance(linkage, list):
                    related_instances = [get_by(self.session, related_model,
                                                rel['id'])
                                         for rel in linkage]
                    links[link_name] = related_instances
                # Otherwise, if this is a to-one relationship, just get a
                # single instance.
                else:
                    id_ = linkage['id']
                    related_instance = get_by(self.session, related_model, id_)
                    links[link_name] = related_instance
        # TODO Need to check here if any related instances are None, like we do
        # in the put() method. We could possibly refactor the code above and
        # the code there into a helper function...
        pass
        # Special case: if there are any dates, convert the string form of the
        # date into an instance of the Python ``datetime`` object.
        #
        # TODO This should be done as part of _dict_to_inst(), not done on its
        # own here.
        data = strings_to_datetimes(self.model, data)
        # Create the new instance by keyword attributes.
        instance = self.model(**data)
        # Set each relation specified in the links.
        for relation_name, related_value in links.items():
            setattr(instance, relation_name, related_value)
        return instance
