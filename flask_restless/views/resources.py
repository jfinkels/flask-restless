# resources.py - views for requests on SQLAlchemy resources
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
"""Views for fetching, creating, updating, and deleting resources.

The main class in this module, :class:`API`, is a
:class:`~flask.MethodView` subclass that handles creating endpoints from
SQLAlchemy models compatible with the JSON API specification.

"""
from flask import json
from flask import request
from werkzeug.exceptions import BadRequest

from ..helpers import collection_name
from ..helpers import get_by
from ..helpers import get_related_model
from ..helpers import has_field
from ..helpers import is_like_list
from ..helpers import primary_key_value
from ..helpers import strings_to_datetimes
from ..serialization import ClientGeneratedIDNotAllowed
from ..serialization import ConflictingType
from ..serialization import DeserializationException
from ..serialization import SerializationException
from .base import APIBase
from .base import error
from .base import error_response
from .base import errors_from_serialization_exceptions
from .base import errors_response
from .base import JSONAPI_VERSION
from .base import MultipleExceptions
from .base import SingleKeyError
from .helpers import changes_on_update


class API(APIBase):
    """Provides method-based dispatching for :http:method:`get`,
    :http:method:`post`, :http:method:`patch`, and :http:method:`delete`
    requests, for both collections of resources and individual resources.

    `session` and `model` are as described in the constructor of the
    superclass. In addition to those described below, this constructor also
    accepts all the keyword arguments of the constructor of the superclass.

    `page_size`, `max_page_size`, `serializer`, `deserializer`, and
    `includes` are as described in :meth:`APIManager.create_api`.

    """

    def __init__(self, *args, **kw):
        super(API, self).__init__(*args, **kw)

        #: Whether any side-effect changes are made to the SQLAlchemy
        #: model on updates.
        self.changes_on_update = changes_on_update(self.model)

    def collection_processor_type(self, is_relation=False, **kw):
        """The suffix for the pre- and postprocessor identifiers for
        requests on collections of resources.

        `is_relation` is ``True`` if and only if the request is for a
        to-many relation. Otherwise, the request is for a collection of
        primary resources.

        """
        return 'TO_MANY_RELATION' if is_relation else 'COLLECTION'

    def resource_processor_type(self, is_relation=False,
                                is_related_resource=False, **kw):
        """The suffix for the pre- and postprocessor identifiers for
        requests on a single resource.

        `is_relation` is ``True`` if and only if the request is for a
        to-one relation. Otherwise, the request is for a single
        resource.

        """
        if is_relation:
            if is_related_resource:
                return 'RELATED_RESOURCE'
            return 'TO_ONE_RELATION'
        return 'RESOURCE'

    def _get_related_resource(self, resource_id, relation_name,
                              related_resource_id):
        """Returns a response containing a resource related to a given
        resource.

        For example, a request like this::

            GET /people/1/articles/2

        will fetch the article with ID 2 that is related to the person with ID
        1 via the ``articles`` relationship. In general, this method is called
        on requests of the form::

            GET /<collection_name>/<resource_id>/<relation_name>/<related_resource_id>

        """
        for preprocessor in self.preprocessors['GET_RELATED_RESOURCE']:
            temp_result = preprocessor(resource_id=resource_id,
                                       relation_name=relation_name,
                                       related_resource_id=related_resource_id)
            # Let the return value of the preprocessor be the new value of
            # instid, thereby allowing the preprocessor to effectively specify
            # which instance of the model to process on.
            #
            # We assume that if the preprocessor returns None, it really just
            # didn't return anything, which means we shouldn't overwrite the
            # instid.
            if temp_result is not None:
                if isinstance(temp_result, tuple):
                    if len(temp_result) == 2:
                        resource_id, relation_name = temp_result
                    else:
                        resource_id, relation_name, related_resource_id = \
                            temp_result
                else:
                    resource_id = temp_result
        # Get the resource with the specified ID.
        primary_resource = get_by(self.session, self.model, resource_id,
                                  self.primary_key)
        # Return an error if there is no resource with the specified ID.
        if primary_resource is None:
            detail = 'No instance with ID {0}'.format(resource_id)
            return error_response(404, detail=detail)
        # Get the model of the specified relation.
        related_model = get_related_model(self.model, relation_name)
        # Return an error if no such relation exists.
        if related_model is None:
            detail = 'No such relation: {0}'.format(relation_name)
            return error_response(404, detail=detail)
        # Return an error if the relation is a to-one relation.
        if not is_like_list(primary_resource, relation_name):
            detail = ('Cannot access a related resource by ID from a to-one'
                      ' relation')
            return error_response(404, detail=detail)
        # Get the related resources.
        resources = getattr(primary_resource, relation_name)
        # Check if one of the related resources has the specified ID. (JSON API
        # expects all IDs to be strings.)
        primary_keys = (primary_key_value(resource, as_string=True)
                        for resource in resources)
        if not any(k == str(related_resource_id) for k in primary_keys):
            detail = 'No related resource with ID {0}'
            detail = detail.format(related_resource_id)
            return error_response(404, detail=detail)
        # Get the related resource by its ID.
        resource = get_by(self.session, related_model, related_resource_id)
        return self._get_resource_helper(resource,
                                         primary_resource=primary_resource,
                                         relation_name=relation_name,
                                         related_resource=True)

    def _get_relation(self, resource_id, relation_name):
        """Returns a response containing a resource or a collection of
        resources related to a given resource.

        For example, a request for a to-many relationship like this::

            GET /people/1/articles

        will fetch the articles related to the person with ID 1 via the
        ``articles`` relationship. On a request to a to-one relationship::

            GET /articles/2/author

        a single resource will be returned.

        In general, this method is called on requests of the form::

            GET /<collection_name>/<resource_id>/<relation_name>

        """
        try:
            filters, sort, group_by, single = self._collection_parameters()
        except (TypeError, ValueError, OverflowError) as exception:
            detail = 'Unable to decode filter objects as JSON list'
            return error_response(400, cause=exception, detail=detail)
        except SingleKeyError as exception:
            detail = 'Invalid format for filter[single] query parameter'
            return error_response(400, cause=exception, detail=detail)

        for preprocessor in self.preprocessors['GET_RELATION']:
            temp_result = preprocessor(resource_id=resource_id,
                                       relation_name=relation_name,
                                       filters=filters, sort=sort,
                                       group_by=group_by, single=single)
            # Let the return value of the preprocessor be the new value of
            # instid, thereby allowing the preprocessor to effectively specify
            # which instance of the model to process on.
            #
            # We assume that if the preprocessor returns None, it really just
            # didn't return anything, which means we shouldn't overwrite the
            # instid.
            if temp_result is not None:
                if isinstance(temp_result, tuple) and len(temp_result) == 2:
                    resource_id, relation_name = temp_result
                else:
                    resource_id = temp_result

        # Get the resource with the specified ID.
        primary_resource = get_by(self.session, self.model, resource_id,
                                  self.primary_key)
        if primary_resource is None:
            detail = 'No resource with ID {0}'.format(resource_id)
            return error_response(404, detail=detail)
        # Get the model of the specified relation.
        related_model = get_related_model(self.model, relation_name)
        if related_model is None:
            detail = 'No such relation: {0}'.format(relation_name)
            return error_response(404, detail=detail)
        # Determine if this is a to-one or a to-many relation.
        if is_like_list(primary_resource, relation_name):
            return self._get_collection_helper(resource=primary_resource,
                                               relation_name=relation_name,
                                               filters=filters, sort=sort,
                                               group_by=group_by,
                                               single=single)
        else:
            resource = getattr(primary_resource, relation_name)
            return self._get_resource_helper(resource=resource,
                                             primary_resource=primary_resource,
                                             relation_name=relation_name)

    def _get_resource(self, resource_id):
        """Returns a response containing a single resource with the specified
        ID.

        For example, a request like::

            GET /people/1

        will fetch the person resource with ID 1.

        In general, this method is called on requests of the form::

            GET /<collection_name>/<resource_id>

        """
        for preprocessor in self.preprocessors['GET_RESOURCE']:
            temp_result = preprocessor(resource_id=resource_id)
            # Let the return value of the preprocessor be the new value of
            # instid, thereby allowing the preprocessor to effectively specify
            # which instance of the model to process on.
            #
            # We assume that if the preprocessor returns None, it really just
            # didn't return anything, which means we shouldn't overwrite the
            # instid.
            if temp_result is not None:
                resource_id = temp_result
        # Get the resource with the specified ID.
        resource = get_by(self.session, self.model, resource_id,
                          self.primary_key)
        if resource is None:
            detail = 'No resource with ID {0}'.format(resource_id)
            return error_response(404, detail=detail)
        return self._get_resource_helper(resource)

    def _get_collection(self):
        """Returns a response containing a collection of resources of the type
        specified by the ``model`` argument to the constructor of this class.

        For example, a request like::

            GET /people

        will fetch a collection of people resources.

        In general, this method is called on requests of the form::

            GET /<collection_name>

        Filtering, sorting, grouping, and pagination are applied to the
        response in this method.

        """
        try:
            filters, sort, group_by, single = self._collection_parameters()
        except (TypeError, ValueError, OverflowError) as exception:
            detail = 'Unable to decode filter objects as JSON list'
            return error_response(400, cause=exception, detail=detail)
        except SingleKeyError as exception:
            detail = 'Invalid format for filter[single] query parameter'
            return error_response(400, cause=exception, detail=detail)

        for preprocessor in self.preprocessors['GET_COLLECTION']:
            preprocessor(filters=filters, sort=sort, group_by=group_by,
                         single=single)

        return self._get_collection_helper(filters=filters, sort=sort,
                                           group_by=group_by, single=single)

    def get(self, resource_id, relation_name, related_resource_id):
        """Returns the JSON document representing a resource or a collection of
        resources.

        If ``resource_id`` is ``None`` (that is, if the request is of the form
        :http:get:`/people/`), this method returns a collection of resources.

        Otherwise, if ``relation_name`` is ``None`` (that is, if the request is
        of the form :http:get:`/people/1`), this method returns a resource with
        the specified ID.

        Otherwise, if ``related_resource_id`` is ``None`` (that is, if the
        request is of the form :http:get:`/people/1/articles` or
        :http:get:`/articles/1/author`), this method returns either a resource
        in the case of a to-one relationship or a collection of resources in
        the case of a to-many relationship.

        Otherwise, if none of the arguments are ``None`` (that is, if the
        request is of the form :http:get:`/people/1/articles/2`), this method
        returns the particular resource in the to-many relationship with the
        specified ID.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        if resource_id is None:
            return self._get_collection()
        if relation_name is None:
            return self._get_resource(resource_id)
        if related_resource_id is None:
            return self._get_relation(resource_id, relation_name)
        return self._get_related_resource(resource_id, relation_name,
                                          related_resource_id)

    def delete(self, resource_id):
        """Deletes the resource with the specified ID.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        for preprocessor in self.preprocessors['DELETE_RESOURCE']:
            temp_result = preprocessor(resource_id=resource_id)
            # See the note under the preprocessor in the get() method.
            if temp_result is not None:
                resource_id = temp_result
        was_deleted = False
        instance = get_by(self.session, self.model, resource_id,
                          self.primary_key)
        if instance is None:
            detail = 'No resource found with ID {0}'.format(resource_id)
            return error_response(404, detail=detail)
        self.session.delete(instance)
        was_deleted = len(self.session.deleted) > 0
        self.session.commit()
        for postprocessor in self.postprocessors['DELETE_RESOURCE']:
            postprocessor(was_deleted=was_deleted)
        if not was_deleted:
            detail = 'There was no instance to delete.'
            return error_response(404, detail=detail)
        return {}, 204

    def post(self):
        """Creates a new resource based on request data.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        # try to read the parameters for the model from the body of the request
        try:
            data = json.loads(request.get_data()) or {}
        except (BadRequest, TypeError, ValueError, OverflowError) as exception:
            detail = 'Unable to decode data'
            return error_response(400, cause=exception, detail=detail)
        # apply any preprocessors to the POST arguments
        for preprocessor in self.preprocessors['POST_RESOURCE']:
            preprocessor(data=data)
        # Convert the dictionary representation into an instance of the
        # model.
        try:
            instance = self.deserialize(data)
            self.session.add(instance)
            self.session.commit()
        except ClientGeneratedIDNotAllowed as exception:
            detail = exception.message()
            return error_response(403, cause=exception, detail=detail)
        except ConflictingType as exception:
            detail = exception.message()
            return error_response(409, cause=exception, detail=detail)
        except DeserializationException as exception:
            detail = exception.message()
            return error_response(400, cause=exception, detail=detail)
        except self.validation_exceptions as exception:
            return self._handle_validation_exception(exception)
        fields_for_this = self.sparse_fields.get(self.collection_name)
        # Get the dictionary representation of the new instance as it
        # appears in the database.
        try:
            data = self.serialize(instance, only=fields_for_this)
        except SerializationException as exception:
            detail = 'Failed to serialize object'
            return error_response(400, cause=exception, detail=detail)
        # Determine the value of the primary key for this instance and
        # encode URL-encode it (in case it is a Unicode string).
        primary_key = primary_key_value(instance, as_string=True)
        # The URL at which a client can access the newly created instance
        # of the model.
        url = '{0}/{1}'.format(request.base_url, primary_key)
        # Provide that URL in the Location header in the response.
        headers = dict(Location=url)
        # Wrap the resulting object or list of objects under a 'data' key.
        result = {'jsonapi': {'version': JSONAPI_VERSION}, 'data': data}
        # Include any requested resources in a compound document.
        try:
            included = self.get_all_inclusions(instance)
        except MultipleExceptions as e:
            # By the way we defined `get_all_inclusions()`, we are
            # guaranteed that each of the underlying exceptions is a
            # `SerializationException`. Thus we can use
            # `errors_from_serialization_exception()`.
            return errors_from_serialization_exceptions(e.exceptions,
                                                        included=True)
        if included:
            result['included'] = included
        status = 201
        for postprocessor in self.postprocessors['POST_RESOURCE']:
            postprocessor(result=result)
        return result, status, headers

    def _update_instance(self, instance, data, resource_id):
        """Updates the attributes and relationships of the specified instance
        according to the elements in the `data` dictionary.

        `instance` must be an instance of the SQLAlchemy model class specified
        in the constructor of this class.

        `data` must be a dictionary representation of a resource object as
        described in the `Updating Resources`_ section of the JSON API
        specification.

        `resource_id` is the ID of the `instance` as determined from the
        URL, given as a string. This is passed directly from the
        :meth:`patch` method.

        .. _Updating Resources: http://jsonapi.org/format/#crud-updating

        """
        # Update any relationships.
        links = data.pop('relationships', {})
        for linkname, link in links.items():
            if not isinstance(link, dict):
                detail = ('missing relationship object for "{0}" in resource'
                          ' of type "{1}" with ID "{2}"')
                detail = detail.format(linkname, self.collection_name,
                                       resource_id)
                return error_response(400, detail=detail)
            # The client is obligated by JSON API to provide linkage if
            # the `links` attribute exists.
            if 'data' not in link:
                detail = 'relationship "{0}" is missing resource linkage'
                detail = detail.format(linkname)
                return error_response(400, detail=detail)
            linkage = link['data']
            related_model = get_related_model(self.model, linkname)
            # If this is a to-many relationship, get all the related
            # resources.
            if is_like_list(instance, linkname):
                # Replacement of a to-many relationship may have been disabled
                # by the user.
                if not self.allow_to_many_replacement:
                    detail = 'Not allowed to replace a to-many relationship'
                    return error_response(403, detail=detail)
                # The provided data must be a list for a to-many relationship.
                if not isinstance(linkage, list):
                    detail = ('"data" element for the to-many relationship'
                              ' "{0}" on the instance of "{1}" with ID "{2}"'
                              ' must be a list; maybe you intended to provide'
                              ' an empty list?')
                    detail = detail.format(linkname, self.collection_name,
                                           resource_id)
                    return error_response(400, detail=detail)
                # If this is left empty, the relationship will be zeroed.
                newvalue = []
                not_found = []
                for rel in linkage:
                    expected_type = collection_name(related_model)
                    type_ = rel['type']
                    if type_ != expected_type:
                        detail = 'Type must be {0}, not {1}'
                        detail = detail.format(expected_type, type_)
                        return error_response(409, detail=detail)
                    id_ = rel['id']
                    inst = get_by(self.session, related_model, id_)
                    if inst is None:
                        not_found.append((id_, type_))
                    else:
                        newvalue.append(inst)
                # If any of the requested to-many linkage objects do not exist,
                # return an error response.
                if not_found:
                    detail = 'No object of type {0} found with ID {1}'
                    errors = [error(detail=detail.format(t, i))
                              for t, i in not_found]
                    return errors_response(404, errors)
            # Otherwise, it is a to-one relationship, so just get the single
            # related resource.
            else:
                # If the client provided "null" for this relation,
                # remove it by setting the attribute to ``None``.
                if linkage is None:
                    newvalue = None
                else:
                    expected_type = collection_name(related_model)
                    type_ = linkage['type']
                    if type_ != expected_type:
                        detail = 'Type must be {0}, not {1}'
                        detail = detail.format(expected_type, type_)
                        return error_response(409, detail=detail)
                    id_ = linkage['id']
                    inst = get_by(self.session, related_model, id_)
                    # If the to-one relationship resource does not
                    # exist, return an error response.
                    if inst is None:
                        detail = 'No object of type {0} found with ID {1}'
                        detail = detail.format(type_, id_)
                        return error_response(404, detail=detail)
                    newvalue = inst
            # Set the new value of the relationship.
            try:
                # TODO Here if there are any extra attributes in
                # newvalue[inst], (1) get the secondary association object for
                # that relation, then (2) set the extra attributes on that
                # object.
                setattr(instance, linkname, newvalue)
            except self.validation_exceptions as exception:
                return self._handle_validation_exception(exception)

        # Now consider only the attributes to update.
        data = data.pop('attributes', {})
        # Check for any request parameter naming a column which does not exist
        # on the current model.
        for field in data:
            if not has_field(self.model, field):
                detail = "Model does not have field '{0}'".format(field)
                return error_response(400, detail=detail)
        # Special case: if there are any dates, convert the string form of the
        # date into an instance of the Python ``datetime`` object.
        data = strings_to_datetimes(self.model, data)
        # Finally, update each attribute individually.
        try:
            if data:
                for field, value in data.items():
                    setattr(instance, field, value)
            self.session.commit()
        except self.validation_exceptions as exception:
            return self._handle_validation_exception(exception)

    def patch(self, resource_id):
        """Updates the resource with the specified ID according to the request
        data.

        The request documents, response documents, and status codes are in the
        format specified by the JSON API specification.

        """
        # try to load the fields/values to update from the body of the request
        try:
            data = json.loads(request.get_data()) or {}
        except (BadRequest, TypeError, ValueError, OverflowError) as exception:
            # this also happens when request.data is empty
            detail = 'Unable to decode data'
            return error_response(400, cause=exception, detail=detail)
        for preprocessor in self.preprocessors['PATCH_RESOURCE']:
            temp_result = preprocessor(resource_id=resource_id, data=data)
            # See the note under the preprocessor in the get() method.
            if temp_result is not None:
                resource_id = temp_result
        # Get the instance on which to set the new attributes.
        instance = get_by(self.session, self.model, resource_id,
                          self.primary_key)
        # If no instance of the model exists with the specified instance ID,
        # return a 404 response.
        if instance is None:
            detail = 'No instance with ID {0} in model {1}'.format(resource_id,
                                                                   self.model)
            return error_response(404, detail=detail)
        # Unwrap the data from the collection name key.
        data = data.pop('data', {})
        if 'type' not in data:
            message = 'Must specify correct data type'
            return error_response(400, detail=message)
        if 'id' not in data:
            message = 'Must specify resource ID'
            return error_response(400, detail=message)
        type_ = data.pop('type')
        id_ = data.pop('id')
        if type_ != self.collection_name:
            message = ('Type must be {0}, not'
                       ' {1}').format(self.collection_name, type_)
            return error_response(409, detail=message)
        if id_ != resource_id:
            message = 'ID must be {0}, not {1}'.format(resource_id, id_)
            return error_response(409, detail=message)
        result = self._update_instance(instance, data, resource_id)
        # If result is not None, that means there was an error updating the
        # resource.
        if result is not None:
            return result
        # If we believe that the resource changes in ways other than the
        # updates specified by the request, we must return 200 OK and a
        # representation of the modified resource.
        if self.changes_on_update:
            result = dict(data=self.serialize(instance))
            status = 200
        else:
            result = dict()
            status = 204
        # Perform any necessary postprocessing.
        for postprocessor in self.postprocessors['PATCH_RESOURCE']:
            postprocessor(result=result)
        return result, status
