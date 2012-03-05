# -*- coding: utf-8; Mode: Python -*-
#
# Copyright (C) 2011 Lincoln de Sousa <lincoln@comum.org>
# Copyright 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
    flaskext.restless.views
    ~~~~~~~~~~~~~~~~~~~~~~~

    Provides :class:`API`, a subclass of :class:`flask.MethodView` which
    provides generic endpoints for HTTP requests for information about a given
    model from the database.

    :copyright:2011 by Lincoln de Sousa <lincoln@comum.org>
    :copyright:2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3, see COPYING for more details

"""

import json

from dateutil.parser import parse as parse_datetime
from elixir import session
from flask import abort
from flask import jsonify
from flask import make_response
from flask import request
from flask.views import MethodView
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import MultipleResultsFound
from sqlalchemy.orm.exc import NoResultFound

from .search import create_query
from .search import evaluate_functions
from .search import search


def jsonify_status_code(status_code, *args, **kw):
    """Returns a jsonified response with the specified HTTP status code.

    The positional and keyword arguments are passed directly to the
    :func:`flask.jsonify` function which creates the response.

    """
    response = jsonify(*args, **kw)
    response.status_code = status_code
    return response


class API(MethodView):
    """Provides method-based dispatching for :http:request:`get`,
    :http:request:`post`, :http:request:`patch`, :http:request:`put`, and
    :http:request:`delete` requests, for both collections of models and
    individual models.

    """

    def __init__(self, model, allow_patch_many=False, *args, **kw):
        """Calls the constructor of the superclass and specifies the model for
        which this class provides a ReSTful API.

        ``model`` is the :class:`elixir.entity.Entity` class of the database
        model for which this instance of the class is an API.

        The `allow_patch_many` keyword argument specifies whether
        :http:method:`patch` requests can be made which update multiple
        instances of the model, as specified in the search query parameter
        ``q``. It is described in the documentation for the
        :meth:`~flask.ext.restless.manager.APIManager.create_api`; see the
        documentation there for more information.

        .. versionadded:: 0.4

           Added the `allow_patch_many` keyword argument.

        """
        super(API, self).__init__(*args, **kw)
        self.model = model
        self.allow_patch_many = allow_patch_many

    def _add_to_relation(self, query, relationname, toadd=None):
        """Adds a new or existing related model to each model specified by
        `query`.

        `query` is a SQLAlchemy query instance that evaluates to all instances
        of the model specified in the constructor of this class that should be
        updated.

        `relationname` is the name of a one-to-many relationship which exists
        on each model specified in `query`.

        `toadd` is a list of dictionaries, each representing the attributes of
        an existing or new related model to add. If a dictionary contains the
        key ``'id'``, that instance of the related model will be
        added. Otherwise, the :classmethod:`~flask.ext.model.get_or_create`
        class method will be used to get or create a model to add.

        """
        submodel = self.model.get_related_model(relationname)
        for dictionary in toadd or []:
            if 'id' in dictionary:
                subinst = submodel.get_by(id=dictionary['id'])
            else:
                subinst = submodel.get_or_create(**dictionary)[0]
            for instance in query:
                getattr(instance, relationname).append(subinst)

    def _remove_from_relation(self, query, relationname, toremove=None):
        """Removes a related model from each model specified by `query`.

        `query` is a SQLAlchemy query instance that evaluates to all instances
        of the model specified in the constructor of this class that should be
        updated.

        `relationname` is the name of a one-to-many relationship which exists
        on each model specified in `query`.

        `toremove` is a list of dictionaries, each representing the attributes
        of an existing model to remove. If a dictionary contains the key
        ``'id'``, that instance of the related model will be
        removed. Otherwise, the instance to remove will be retrieved using the
        other attributes specified in the dictionary.

        If one of the dictionaries contains a mapping from ``'__delete__'`` to
        ``True``, then the removed object will be deleted after being removed
        from each instance of the model in the specified query.

        """
        submodel = self.model.get_related_model(relationname)
        for dictionary in toremove or []:
            remove = dictionary.pop('__delete__', False)
            if 'id' in dictionary:
                subinst = submodel.get_by(id=dictionary['id'])
            else:
                subinst = submodel.get_by(**dictionary)
            for instance in query:
                getattr(instance, relationname).remove(subinst)
            if remove:
                subinst.delete()

    # TODO change this to have more sensible arguments
    def _update_relations(self, query, params):
        """Adds or removes models which are related to the model specified in
        the constructor of this class.

        If one of the dictionaries specified in ``add`` or ``remove`` includes
        an ``id`` key, the object with that ``id`` will be attempt to be added
        or removed. Otherwise, an existing object with the specified attribute
        values will be attempted to be added or removed. If adding, a new
        object will be created if a matching object could not be found in the
        database.

        This function does not commit the changes made to the database. The
        calling function has that responsibility.

        This method returns a :class:`frozenset` of strings representing the
        names of relations which were modified.

        `query` is a SQLAlchemy query instance that evaluates to all instances
        of the model specified in the constructor of this class that should be
        updated.

        `params` is a dictionary containing a mapping from name of the relation
        to modify (as a string) to a second dictionary. The inner dictionary
        contains at most two mappings, one with the key ``'add'`` and one with
        the key ``'remove'``. Each of these is a mapping to a list of
        dictionaries which represent the attributes of the object to add to or
        remove from the relation.

        If a dictionary in one of the ``'remove'`` lists contains a mapping
        from ``'__delete__'`` to ``True``, then the removed object will be
        deleted after being removed from each instance of the model in the
        specified query.

        """
        relations = self.model.get_relations()
        tochange = frozenset(relations) & frozenset(params)
        for columnname in tochange:
            toadd = params[columnname].get('add', [])
            toremove = params[columnname].get('remove', [])
            self._add_to_relation(query, columnname, toadd=toadd)
            self._remove_from_relation(query, columnname, toremove=toremove)
        return tochange

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
            if self.model.is_date_or_datetime(fieldname):
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
        filters and/or functions. In a filter, the client specifies the name of
        the field by which to filter, the operation to perform on the field,
        and the value which is the argument to that operation. In a function,
        the client specifies the name of a SQL function which is executed on
        the search results; the result of executing the function is returned to
        the client.

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

        For more information SQLAlchemy functions and operators for use in
        filters, see the `SQLAlchemy SQL expression tutorial
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
               ],
             "functions":
               [
                 {"name": "sum", "field": "age"},
                 ...
               ]
           }

        For a complete description of all possible search parameters and
        responses, see :ref:`search`.

        """
        # try to get search query from the request query parameters
        try:
            data = json.loads(request.args.get('q', '{}'))
        except (TypeError, ValueError, OverflowError):
            return jsonify_status_code(400, message='Unable to decode data')

        # TODO the functions should be applied to the result of the query...
        # If the query parameters specify that at least one function should be
        # executed, return the result of executing that function. If no
        # functions are specified, perform a search and return the instances
        # which match that search.
        if 'functions' in data:
            try:
                result = evaluate_functions(self.model, data['functions'])
            except (AttributeError, OperationalError) as exception:
                return jsonify_status_code(400, message=exception.message)
            return jsonify(result)

        # there were no functions specified, so perform a filtered search
        try:
            result = search(self.model, data)
        except NoResultFound:
            return jsonify(message='No result found')
        except MultipleResultsFound:
            return jsonify(message='Multiple results found')

        # create a placeholder for relations of the returned models
        relations = self.model.get_relations()
        deep = dict(zip(relations, [{}] * len(relations)))

        # for security purposes, don't transmit list as top-level JSON
        if isinstance(result, list):
            result = [x.to_dict(deep) for x in result]
            return jsonify(objects=result)
        else:
            return jsonify(result.to_dict(deep))

    def get(self, instid):
        """Returns a JSON representation of an instance of model with the
        specified name.

        If ``instid`` is ``None``, this method returns the result of a search
        with parameters specified in the query string of the request. If no
        search parameters are specified, this method returns all instances of
        the specified model.

        If ``instid`` is an integer, this method returns the instance of the
        model with that identifying integer. (Implementation note: the
        underlying implementation uses the :func:`elixir.entity.Entity.get_by`
        method.) If no such instance exists, this method responds with
        :http:status:`404`.

        """
        if instid is None:
            return self._search()
        inst = self.model.get_by(id=instid)
        if inst is None:
            abort(404)
        relations = self.model.get_relations()
        deep = dict(zip(relations, [{} for n in range(len(relations))]))
        return jsonify(inst.to_dict(deep))

    def delete(self, instid):
        """Removes the specified instance of the model with the specified name
        from the database.

        Since :http:method:`delete` is an idempotent method according to the
        :rfc:`2616`, this method responds with :http:status:`204` regardless of
        whether an object was deleted.

        """
        inst = self.model.get_by(id=instid)
        if inst is not None:
            inst.delete()
            session.commit()
        return make_response(None, 204)

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
        # try to read the parameters for the model from the body of the request
        try:
            params = json.loads(request.data)
        except (TypeError, ValueError, OverflowError):
            return jsonify_status_code(400, message='Unable to decode data')

        # Getting the list of relations that will be added later
        cols = self.model.get_columns()
        relations = self.model.get_relations()

        # Looking for what we're going to set on the model right now
        colkeys = cols.keys()
        paramkeys = params.keys()
        props = set(colkeys).intersection(paramkeys).difference(relations)

        # Instantiate the model with the parameters
        instance = self.model(**dict([(i, params[i]) for i in props]))

        # Handling relations, a single level is allowed
        for col in set(relations).intersection(paramkeys):
            submodel = cols[col].property.mapper.class_
            for subparams in params[col]:
                subinst = submodel.get_or_create(**subparams)[0]
                getattr(instance, col).append(subinst)

        # add the created model to the session
        session.add(instance)
        session.commit()

        return jsonify_status_code(201, id=instance.id)

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
        patchmany = instid is None

        # if this was configured not to allow patching many, return HTTP 405
        if patchmany and not self.allow_patch_many:
            return make_response(None, 405)

        # try to load the fields/values to update from the body of the request
        try:
            data = json.loads(request.data)
        except (TypeError, ValueError, OverflowError):
            return jsonify_status_code(400, message='Unable to decode data')

        # If there is no data to update, just return HTTP 204 No Content.
        if len(data) == 0:
            return make_response(None, 204)

        if patchmany:
            # create a SQLALchemy Query from the query parameter `q`
            query = create_query(self.model, data)
        else:
            # create a SQLAlchemy Query which has exactly the specified row
            query = self.model.query.filter_by(id=instid)
            assert query.count() == 1, 'Multiple rows with same ID'

        relations = self._update_relations(query, data)
        field_list = frozenset(data) ^ relations
        params = dict((field, data[field]) for field in field_list)

        # Special case: if there are any dates, convert the string form of the
        # date into an instance of the Python ``datetime`` object.
        params = self._strings_to_dates(params)

        # Let's update all instances present in the query
        num_modified = 0
        if params:
            num_modified = query.update(params, False)
        session.commit()

        if patchmany:
            return jsonify(num_modified=num_modified)
        else:
            return self.get(instid)

    def put(self, instid):
        """Alias for :meth:`patch`."""
        return self.patch(instid)
