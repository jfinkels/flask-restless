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
from sqlalchemy.orm.exc import MultipleResultsFound
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.types import Date
from sqlalchemy.types import DateTime

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
    :http:request:`post`, :http:request:`patch`, and :http:request:`delete`
    requests, for both collections of models and individual models.

    """

    def __init__(self, model, *args, **kw):
        """Calls the constructor of the superclass and specifies the model for
        which this class provides a ReSTful API.

        ``model`` is the :class:`elixir.entity.Entity` class of the database
        model for which this instance of the class is an API.

        """
        super(API, self).__init__(*args, **kw)
        self.model = model

    # TODO change this to have more sensible arguments
    # TODO document the __delete__ flag
    def _update_relations(self, query, params):
        """Adds or removes models which are related to the model specified in
        the constructor of this class.

        ``query`` is a SQLAlchemy query instance that evaluates to all
        instances of the model specified in the constructor of this class that
        should be updated.

        `params`

            A dictionary with two keys ``add`` and ``remove``. Both of them
            contains a list of items that should be added or removed from
            such a relation.
        """
        fields = []
        cols = self.model.get_columns()
        relations = self.model.get_relations()
        for col in set(relations).intersection(params.keys()):
            submodel = cols[col].property.mapper.class_
            from_request = params[col]

            # Let's add new columns to the relation being managed.
            for subparams in from_request.get('add', ()):
                if 'id' in subparams:
                    subinst = submodel.get_by(id=subparams.pop('id'))
                else:
                    vssubparams = subparams
                    subinst = submodel.get_or_create(**vssubparams)[0]
                for instance in query:
                    getattr(instance, col).append(subinst)

            # Now is the time to handle relations being removed from a field
            # of the instance. We'll do nothing here if there's no id param
            for subparams in from_request.get('remove', ()):
                try:
                    remove = subparams.pop('__delete__')
                except KeyError:
                    remove = False
                if 'id' in subparams:
                    subinst = submodel.get_by(id=subparams['id'])
                else:
                    vssubparams = subparams
                    subinst = submodel.get_by(**vssubparams)
                for instance in query:
                    field = getattr(instance, col)
                    field.remove(subinst)
                if remove:
                    subinst.delete()

            fields.append(col)
        return fields

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

            {"objects": [{"name": "Mary"}, {"name": "Byron"}, ...]}

        If the result of the search is a single instance of the model, the JSON
        representation of that instance would be the top-level object in the
        content of the response::

            {"name": "Mary", ...}

        For more information SQLAlchemy functions and operators for use in
        filters, see the `SQLAlchemy SQL expression tutorial
        <http://docs.sqlalchemy.org/en/latest/core/tutorial.html>`_.

        The general structure of request data as a JSON string is as follows::

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

        For a complete description of all possible search parameters, see
        :ref:`search`.

        """
        # try to get search query from the request query parameters
        try:
            data = json.loads(request.args.get('q', '{}'))
        except (TypeError, ValueError, OverflowError):
            return jsonify_status_code(400, message='Unable to decode data')

        # If the query parameters specify that at least one function should be
        # executed, return the result of executing that function. If no
        # functions are specified, perform a search and return the instances
        # which match that search.
        if 'functions' in data:
            # TODO data['functions'] may be poorly defined here...
            result = evaluate_functions(self.model, data['functions'])
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

    # TODO should this exist?
    def _patch_many(self):
        """Updates each of the instances of the model which match the query
        string.

        The ``request.data`` field should be filled with a JSON string that
        contains an object with two fields: query and form. The first one
        should have an object that looks the same as the one passed to the
        ``search`` method. The second field (form) should contain an object
        with all fields that will be passed to the ``update()`` method.

        """
        # TODO this code is common to patch
        try:
            data = json.loads(request.data)
        except (TypeError, ValueError, OverflowError):
            return jsonify_status_code(400, message='Unable to decode data')
        # build the query dictionary from the request query string
        query = create_query(self.model, data)

        # TODO this code is common to patch
        if len(data) == 0:
            return make_response(None, 204)

        # TODO this code is common to patch
        relations = set(self._update_relations(query, data))
        field_list = set(data.keys()) ^ relations
        originalparams = dict((field, data[field]) for field in field_list)

        # Special case: if there are any dates, convert the string form of the
        # date into an instance of the Python ``datetime`` object.
        params = {}
        for key, val in originalparams.iteritems():
            fieldtype = getattr(self.model, key).property.columns[0].type
            if isinstance(fieldtype, Date) or isinstance(fieldtype, DateTime):
                params[key] = parse_datetime(val)
            else:
                params[key] = val

        # Let's update all instances present in the query
        num_modified = 0
        if params:
            num_modified = query.update(params, False)
        session.commit()

        return jsonify(num_modified=num_modified)

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
        # TODO this code is common to _patch_many
        # if no instance is specified, try to patch many using a search
        if instid is None:
            return self._patch_many()
        
        # try to load the fields/values to update from the body of the request
        try:
            data = json.loads(request.data)
        except (TypeError, ValueError, OverflowError):
            return jsonify_status_code(400, message='Unable to decode data')

        # TODO this code is common to _patch_many
        # If there is no data to update, just return HTTP 204 No Content.
        if len(data) == 0:
            return make_response(None, 204)

        # TODO this code is common to _patch_many
        relations = set(self._update_relations([self.model.get_by(id=instid)],
                                               data))
        field_list = set(data.keys()) ^ relations
        originalparams = dict((field, data[field]) for field in field_list)

        # Special case: if there are any dates, convert the string form of the
        # date into an instance of the Python ``datetime`` object.
        params = {}
        for key, val in originalparams.iteritems():
            fieldtype = getattr(self.model, key).property.columns[0].type
            if isinstance(fieldtype, Date) or isinstance(fieldtype, DateTime):
                params[key] = parse_datetime(val)
            else:
                params[key] = val

        # Let's update field by field
        # TODO can this be made the same as in _patch_many?
        inst = self.model.get_by(id=instid)
        for field in field_list:
            setattr(inst, field, params[field])
        session.commit()

        # return the updated object
        return self.get(instid)
