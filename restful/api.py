# -*- coding: utf-8; Mode: Python -*-
#
# Copyright (C) 2011  Lincoln de Sousa <lincoln@comum.org>
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
    restful.api
    ~~~~~~~~~~~

    Defines a flask model that provides a generic model API to be
    exposed using REST spec.

    This module is intended to be a generic way for creating, updating,
    searching and deleting entries of an sqlalchemy model (declared with
    elixir) through a generic HTTP API.

    All models being exposed by this API are going to be validated using
    formencode validators that should be declared by the user of this
    library.

    :copyright:2011 by Lincoln de Sousa <lincoln@comum.org>
    :license: AGPLv3, see COPYTING for more details
"""

from flask import Blueprint, request, abort
from flask import jsonify
from flask import make_response
from flask.views import MethodView
from json import dumps, loads
from formencode import Invalid, validators as fvalidators
from elixir import session
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.sql import func

from model import get_or_create


__all__ = 'blueprint',

blueprint = Blueprint('api', __name__)

CONFIG = {
    'models': None,
    'validators': None,
}


def setup(models, validators):
    """Sets up models and validators to be exposed by the REST API

    This function should be called only once after executing your web
    app. It's intended to setup the global configuration dictionary of
    this module that holds references to the models and validators
    modules of the user app.
    """
    CONFIG['models'] = models
    CONFIG['validators'] = validators


def build_search_param(model, fname, relation, operation, value):
    """Translates an operation described as a string to a valid
    sqlalchemy query parameter.

    This takes, for example, the operation ``gt`` and converts it to
    something like this: ``field > value``.

    `model`

        An instance of an entity being searched

    `fname`

        The name of the field being searched

    `relation`

        Name of the relationship attribute. This field should be
        ``None`` to fields that does not refer to relationships.

    `operation`

        Describes which operation should be done between the field and
        the value received. For example: equals_to, gt, lt, like, in
        etc. Read the source code of this function to see a complete
        list of possible operators.

    `value`

        The value to be compared in the search
    """
    if relation is not None:
        field = getattr(model, relation)
    else:
        field = getattr(model, fname)

    ops = {
        'equals_to': lambda: field == value,
        'not_equals_to': lambda: field != value,
        'gt': lambda: field > value,
        'lt': lambda: field < value,
        'gte': lambda: field >= value,
        'lte': lambda: field <= value,
        'like': lambda: field.like(value),
        'in': lambda: field.in_(value),
        'not_in': lambda: ~field.in_(value),
        'is_null': lambda: field == None,
        'is_not_null': lambda: field != None,
        'desc': field.desc,
        'asc': field.asc,
        'has': lambda: field.has(**{fname: value}),
        'any': lambda: field.any(**{fname: value}),
    }

    return ops.get(operation)()


def _evaluate_functions(model, functions):
    """Evaluates a query that executes functions

    If you pass a model and a list of functions to this func, it will
    execute them in the database and return a JSON string containing an
    object with all results evaluated.

    `model`

        An elixir model that functions are going to be executed agains.

    `functions`

        A list of functions in the following syntas: ``func:field``. For
        example, if you want the sum and the average of a field, you can
        pass something like this: ['sum:amount', 'avg:amount'].
    """
    processed = []
    funcnames = []
    for val in functions:
        funcname = val['name']
        fname = val['field']

        # So, now is the time to use a bit of dynamic blackmagic of
        # python. with the function name, we retrieve its object from
        # the sqlalchemy ``func`` func module. And with the field name,
        # we retrieve ti from the model class.
        funcobj = getattr(func, funcname)
        field = getattr(model, fname)

        # Time to store things to be executed. The processed list stores
        # functions that will be executed in the database and funcnames
        # contains names of the entries that will be returned to the
        # caller.
        processed.append(funcobj(field))
        funcnames.append('%s__%s' % (funcname, fname))

    # Ok, now is the time to execute it, pack in a JSON string and
    # return to the user.
    evaluated = session.query(*processed).one()
    return dict(zip(funcnames, evaluated))


class AggregateException(Exception):
    """A validation exception which aggregates error messages for multiple
    fields.

    This class contains a list of dictionaries, :attr:`messages`, in which each
    dictionary contains a single mapping, which maps an error location
    identifier (for example, field name in an aggregation of validation errors)
    to an error message which corresponds to that location (for example, ``'Age
    must be a positive integer'``). For example, the :attr:`messages` list
    might looks like this::

        [{'age': 'Must be a positive integer', 'name': 'Must be specified'}]

    The error messages are aggregated in this way so that they can be easily
    translated to a JSON string using the :func:`json.dumps` function.

    Code which will raise this exception should append singleton dictionaries
    to the list of error messages using the :func:`append` function, which
    simply delegates to the corresponding function on the list of
    messages. Code which will catch this exception can access the list of
    singleton dictionaries by accessing the :attr:`messages` attribute.

    """

    def __init__(self, *args, **kw):
        """Passes the positional and keyword arguments to the constructor of
        the superclass and creates an empty :attr:`messages` list.

        """
        super(AggregateException, self).__init__(*args, **kw)
        self.messages = []

    def __str__(self):
        """Returns the string representation of the underlying list of error
        messages.

        """
        return self.messages.__str__()

    def __len__(self): return len(self.messages)
    def __iter__(self): return self.messages.__iter__()
    def append(self, mapping): return self.messages.append(mapping)
    def extend(self, mappings): return self.messages.extend(mappings)


def _extract_operators(model, search_params):
    """Extracts operators from the search_params."""
    validator = getattr(CONFIG['validators'], model.__name__)

    # Where processed operations will be stored
    operations = []
    exception = AggregateException()

    # Evaluating and validating field contents
    for i in search_params.get('filters', ()):
        fname = i['name']
        val = i.get('val')

        relation = None
        if '__' in fname:
            relation, fname = fname.split('__')
            cls = model.get_columns()[relation].property.mapper.class_
            field = getattr(CONFIG['validators'], cls.__name__).fields[fname]
        else:
            # Here we handle fields that does not defines relations with
            # other entities and the ID field is a special case, since
            # it's not defined in the validator but must be searchable
            # as well as the other fields.
            if fname == 'id':
                field = fvalidators.Int()
            else:
                field = validator.fields[fname]

        # We are going to compare a field with another one, so there's
        # no reason to parse
        if 'field' in i:
            param = build_search_param(
                model, fname, relation, i['op'], getattr(model, i['field']))
            operations.append(param)
            continue

        # Here is another special case. There are some operations, like
        # IN that can receive a list. This way, we need to be prepared
        # to pass it to the next level, validated of course.
        try:
            if isinstance(val, list):
                converted_value = []
                for subval in val:
                    converted_value.append(field.to_python(subval))
            else:
                converted_value = field.to_python(val)
        except Invalid as exc:
            exception.append({fname: exc.msg})
            continue

        # Collecting the query
        param = build_search_param(
            model, fname, relation, i['op'], converted_value)
        operations.append(param)

    if len(exception) > 0:
        raise exception

    return operations


def _build_query(model, search_params):
    """Builds an sqlalchemy.Query instance based on the params present
    in ``search_params``.

    This function raises :exc:`AggregateException` if the operators specified
    in ``search_params`` are invalid.

    """
    # Adding field filters
    query = model.query
    extracted_operators = _extract_operators(model, search_params)
    for i in extracted_operators:
        query = query.filter(i)

    # Order the search
    for val in search_params.get('order_by', ()):
        field = getattr(model, val['field'])
        query = query.order_by(getattr(field, val.get('direction', 'asc'))())

    # Limit it
    if search_params.get('limit'):
        query = query.limit(search_params.get('limit'))
    if search_params.get('offset'):
        query = query.offset(search_params.get('offset'))
    return query


def _perform_search(model, search_params):
    """This function is the one that actually feeds the ``query`` object
    and performs the search.

    If there is an error while building the query, this function will raise an
    :exc:`AggregateException`.

    `model`

        The model which search will be made

    `search_params`

        A dictionary containing all available search parameters. The
        real job of this function is to look for all search parameters
        of this dict and evaluate a query built with these args.
    """
    # Building the query
    query = _build_query(model, search_params)

    # Aplying functions
    if search_params.get('functions'):
        return _evaluate_functions(model, search_params.get('functions'))

    relations = model.get_relations()
    deep = dict(zip(relations, [{}] * len(relations)))
    if search_params.get('type') == 'one':
        # may raise NoResultFound or MultipleResultsFound
        return query.one().to_dict(deep)
    else:
        return [x.to_dict(deep) for x in query.all()]


def _validate_field_list(model, data, field_list):
    """Returns a list of fields validated by :mod:`formencode`.

    If :mod:`formencode` discovers invalid form input, this function raises
    :exc:`AggregateException`. The :attr:`AggregateException.messages`
    dictionary on the raised exception maps field name to a list of validation
    error messages for that field.

    `model`
        The name of the model

    """
    params = {}
    exception = AggregateException()
    for key in field_list:
        try:
            validator = getattr(CONFIG['validators'], model)().fields[key]
            params[key] = validator.to_python(data[key])
        except Invalid as exc:
            exception.append({key: exc.msg})
        except KeyError:
            exception.append({key: 'No such key exists'})

    if len(exception) > 0:
        raise exception
    return params


def update_relations(model, query, params):
    """Updates related fields of a model that are present in ``params``.

    `model`

        An elixir model instance that will have its relations updated.

    `query`

        An sqlalchemy Query instance that evaluates to all instances that
        should be updated.

    `params`

        A dictionary with two keys ``add`` and ``remove``. Both of them
        contains a list of items that should be added or removed from
        such a relation.
    """
    fields = []
    cols = model.get_columns()
    relations = model.get_relations()
    for col in set(relations).intersection(params.keys()):
        submodel = cols[col].property.mapper.class_
        from_request = params[col]

        # Let's add new columns to the relation being managed.
        for subparams in from_request.get('add', ()):
            if 'id' in subparams:
                subinst = submodel.get_by(id=subparams.pop('id'))
            else:
                vssubparams = _validate_field_list(
                    submodel.__name__, subparams, subparams.keys())
                subinst = get_or_create(submodel, **vssubparams)[0]
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
                vssubparams = _validate_field_list(
                    submodel.__name__, subparams, subparams.keys())
                subinst = submodel.get_by(**vssubparams)
            for instance in query:
                field = getattr(instance, col)
                field.remove(subinst)
            if remove:
                subinst.delete()

        fields.append(col)
    return fields


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
    :http:request:`post`, :http:request:`put`, and :http:request:`delete`
    requests, for both collections of models and individual models.

    """

    def post(self, modelname):
        """Creates a new instance of a given model based on request data.

        This function parses the string contained in ``Flask.request.data`` as
        a JSON object and then validates it with a validator accessed from
        ``CONFIG['validators'].<modelname>``.

        After that, it separates all columns that defines relationships with
        other entities, creates a model with the simple columns and then
        creates instances of these submodules and associates to the related
        fiels. This happens only in the first level.

        `modelname`

            Model name which the new instance will be created. To retrieve
            the model, we do a ``getattr(CONFIG['models'], <modelname>)``.
        """
        model = getattr(CONFIG['models'], modelname)

        try:
            validator = getattr(CONFIG['validators'], modelname)()
            params = validator.to_python(loads(request.data))
        except (TypeError, ValueError, OverflowError):
            return jsonify_status_code(400, message='Unable to decode data')
        except Invalid as exc:
            return jsonify_status_code(400, message='Validation error',
                                       error_list=exc.unpack_errors())

        # Getting the list of relations that will be added later
        cols = model.get_columns()
        relations = model.get_relations()

        # Looking for what we're going to set to the model right now
        colkeys = cols.keys()
        paramkeys = params.keys()
        props = set(colkeys).intersection(paramkeys).difference(relations)
        instance = model(**dict([(i, params[i]) for i in props]))

        # Handling relations, a single level is allowed
        for col in set(relations).intersection(params.keys()):
            submodel = cols[col].property.mapper.class_
            subvalidator = getattr(CONFIG['validators'], submodel.__name__)
            for subparams in params[col]:
                subparams = subvalidator.to_python(subparams)
                subinst = get_or_create(submodel, **subparams)[0]
                getattr(instance, col).append(subinst)

        session.add(instance)
        session.commit()

        return jsonify_status_code(201, id=instance.id)

    def search(self, modelname):
        """Defines a generic search function

        As the other functions of our backend, this function should work for
        all entities declared in the ``CONFIG['models']`` module. It
        provides a way to execute a query received from the query string and
        serialize its results in JSON.

        This function currently understands two kinds of commands: Simple
        fields and order_by fields.

        `modelname`

            Name of the model that the search will be performed.
        """
        try:
            data = loads(request.args.get('q', '{}'))
        except (TypeError, ValueError, OverflowError):
            return jsonify_status_code(400, message='Unable to decode data')

        model = getattr(CONFIG['models'], modelname)
        try:
            result = _perform_search(model, data)
        except AggregateException as exception:
            message = 'Validation of search query failed'
            return jsonify_status_code(400, message=message,
                                       error_list=exception.messages)
        except NoResultFound:
            return jsonify(message='No result found')
        except MultipleResultsFound:
            return jsonify(message='Multiple results found')
        # for security purposes, don't transmit list as top-level JSON
        if isinstance(result, list):
            return jsonify(objects=result)
        else:
            return jsonify(result)

    def put_many(self, modelname):
        """Calls the .update() method in a set of results.

        The ``request.data`` field should be filled with a JSON string that
        contains an object with two fields: query and form. The first one
        should have an object that looks the same as the one passed to the
        ``search`` method. The second field (form) should contain an object
        with all fields that will be passed to the ``update()`` method.

        `modelname`

            The name of the model that the update will be done.
        """
        model = getattr(CONFIG['models'], modelname)
        try:
            data = loads(request.data)
        except (TypeError, ValueError, OverflowError):
            return jsonify_status_code(400, message='Unable to decode data')
        query = _build_query(model, request.args)

        if len(data) == 0:
            return make_response(None, 204)

        relations = set(update_relations(model, query, data))
        field_list = set(data.keys()) ^ relations
        try:
            params = _validate_field_list(modelname, data, field_list)
        except AggregateException as exception:
            return jsonify_status_code(400, message='Validation error',
                                       error_list=exception.messages)

        # Let's update all instances present in the query
        num_modified = 0
        if params:
            num_modified = query.update(params, False)

        session.commit()
        return jsonify(num_modified=num_modified)

    def put(self, modelname, instid):
        """Updates the instance specified by ``instid`` of the named model, or
        updates multiple instances if ``instid`` is ``None``.

        The :attr:`flask.request.data` attribute will be parsed as a JSON
        object containing the mapping from field name to value to which to
        update the specified instance or instances.

        If ``instid`` is ``None``, the query string will be used to search for
        instances (using the :func:`search` function), and all matching
        instances will be updated according to the content of the request data.

        """
        if instid is None:
            return self.put_many(modelname)
        model = getattr(CONFIG['models'], modelname)
        try:
            data = loads(request.data)
        except (TypeError, ValueError, OverflowError):
            return jsonify_status_code(400, message='Unable to decode data')

        # If there is no data to update, just return HTTP 204 No Content.
        if len(data) == 0:
            return make_response(None, 204)

        inst = model.get_by(id=instid)
        relations = set(update_relations(model, [inst], data))
        field_list = set(data.keys()) ^ relations
        try:
            params = _validate_field_list(modelname, data, field_list)
        except AggregateException as exception:
            return jsonify_status_code(400, message='Validation error',
                                       error_list=exception.messages)

        # Let's update field by field
        for field in field_list:
            setattr(inst, field, params[field])
        session.commit()

        # return the updated object
        return self.get(modelname, instid)

    def get(self, modelname, instid):
        """Returns a json representation of an instance of a model.

        It's an http binding to the ``get_by`` method of a model that
        returns data of an instance of a given model.

        ``modelname``

            The model that get_by is going to be called

        `instid`

            Instance id
        """
        if instid is None:
            return self.search(modelname)
        model = getattr(CONFIG['models'], modelname)
        inst = model.get_by(id=instid)
        if inst is None:
            abort(404)

        relations = model.get_relations()
        deep = dict(zip(relations, [{}] * len(relations)))
        return jsonify(inst.to_dict(deep))

    def delete(self, modelname, instid):
        """Removes an instance from the database based on its id
        """
        model = getattr(CONFIG['models'], modelname)
        inst = model.get_by(id=instid)
        if inst is not None:
            inst.delete()
            session.commit()
        return make_response(None, 204)


api_view = API.as_view('api')
blueprint.add_url_rule('/<modelname>/', view_func=api_view, methods=['POST', ])
blueprint.add_url_rule('/<modelname>/', defaults={'instid': None},
                       view_func=api_view, methods=['GET', 'PUT'])
blueprint.add_url_rule('/<modelname>/<int:instid>/', view_func=api_view,
                       methods=['GET', 'PUT', 'DELETE'])
