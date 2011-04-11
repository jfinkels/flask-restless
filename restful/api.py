# -*- coding: utf-8; Mode: Python -*-
#
# Copyright (C) 2011  Lincoln de Sousa <lincoln@comum.org>
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

    Defines a flask model called `api` that provides a generic model API
    to be exposed using REST spec.

    This module is intended to be a generic way for creating, updating,
    searching and deleting entries of an sqlalchemy model (declared with
    elixir) through a generic HTTP API.

    All models being exposed by this API are going to be validated using
    formencode validators that should be declared by the user of this
    library.

    :copyright:2011 by Lincoln de Sousa <lincoln@comum.org>
    :license: AGPLv3, see COPYTING for more details
"""

from flask import Module, request, abort
from simplejson import dumps, loads, JSONDecodeError
from formencode import Invalid, validators as fvalidators
from elixir import session
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.sql import func

from model import get_or_create

__all__ = 'api',

api = Module(__name__, name='api')

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


@api.route('/<modelname>/', methods=('POST',))
def create(modelname):
    """Creates a new instance of a given model based on request data

    This function parses the string contained in ``Flask.request.data``
    as a JSON object and then validates it with a validator placed in
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
        params = getattr(CONFIG['validators'],
                         modelname)().to_python(loads(request.data))
    except JSONDecodeError:
        return dumps({'status': 'error', 'message': 'Unable to decode data'})
    except Invalid, exc:
        return dumps({'status': 'error', 'message': 'Validation error',
                      'error_list': exc.unpack_errors()})

    # Getting the list of relations that will be added later
    cols = model.get_columns()
    relations = model.get_relations()

    # Looking for what we're going to set to the model right now
    props = set(cols.keys()).intersection(params.keys()).difference(relations)
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

    # We return a ok message and the just created instance id
    return dumps({'status': 'ok', 'message': 'You rock!', 'id': instance.id})


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


def _evalute_functions(model, functions):
    """Evalutes a query that executes functions

    If you pass a model and a list of functions to this func, it will
    execute them in the database and return a JSON string containing an
    object with all results evaluted.

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
    evaluted = session.query(*processed).one()
    return dumps(dict(zip(funcnames, evaluted)))


class ExceptionFound(Exception):
    """Exception raised if there's something wrong in the validation of
    fields."""
    def __init__(self, msg):
        super(ExceptionFound, self).__init__()
        self.msg = msg

def _extract_operators(model, search_params):
    """Extracts operators from the search_params."""
    validator = getattr(CONFIG['validators'], model.__name__)

    # Where processed operations will be stored
    operations = []
    exceptions = []

    # Evaluting and validating field contents
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
        if i.has_key('field'):
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
        except Invalid, exc:
            exceptions.extend({fname: exc.msg})
            continue

        # Collecting the query
        param = build_search_param(
            model, fname, relation, i['op'], converted_value)
        operations.append(param)

    if exceptions:
        raise ExceptionFound(
            dumps({'status': 'error', 'message': 'Invalid data',
                   'error_list': exceptions})
            )

    return operations

def _build_query(model, search_params):
    """Builds an sqlalchemy.Query instance based on the params present
    in ``search_params``.
    """
    # Adding field filters
    query = model.query
    for i in _extract_operators(model, search_params):
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

    `model`

        The model which search will be made

    `search_params`

        A dictionary containing all available search parameters. The
        real job of this function is to look for all search parameters
        of this dict and evalute a query built with these args.
    """
    # Building the query
    try:
        query = _build_query(model, search_params)
    except ExceptionFound, exc:
        return exc.msg

    # Aplying functions
    if search_params.get('functions'):
        return _evalute_functions(model, search_params.get('functions'))

    relations = model.get_relations()
    deep = dict(zip(relations, [{}]*len(relations)))
    if search_params.get('type') == 'one':
        try:
            return dumps(query.one().to_dict(deep))
        except NoResultFound:
            return dumps({
                    'status':'error',
                    'message': 'No result found',
                    })
        except MultipleResultsFound:
            return dumps({
                    'status': 'error',
                    'message': 'Multiple results found',
                    })
    else:
        return dumps([x.to_dict(deep) for x in query.all()])


@api.route('/<modelname>/', methods=('GET',))
def search(modelname):
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
        data = loads(request.values.get('q', '{}'))
    except JSONDecodeError:
        return dumps({'status': 'error', 'message': 'Unable to decode data'})

    model = getattr(CONFIG['models'], modelname)
    return _perform_search(model, data)


def _validate_field_list(model, data, field_list):
    """Returns a list of fields validated by formencode

    This function may raise the ``formencode.Invalid`` exception.

    `model`
        The name of the model
    """
    params = {}
    exceptions = []
    for key in field_list:
        try:
            validator = getattr(CONFIG['validators'], model)().fields[key]
            params[key] = validator.to_python(data[key])
        except Invalid, exc:
            exceptions.append({key: exc.msg})

    if exceptions:
        return dumps({'status': 'error', 'message': 'Validation error',
                      'error_list': exceptions})
    return params


def update_relations(model, query, params):
    """Updates related fields of a model that are present in ``params``.

    `model`

        An elixir model instance that will have its relations updated.

    `query`

        An sqlalchemy Query instance that evalutes to all instances that
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


@api.route('/<modelname>/', methods=('PUT',))
def update(modelname):
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
    except JSONDecodeError:
        return dumps({'status': 'error', 'message': 'Unable to decode data'})
    query = _build_query(model, data.get('query', {}))

    relations = set(update_relations(model, query, data['form']))
    field_list = set(data['form'].keys()) ^ relations
    params = _validate_field_list(modelname, data['form'], field_list)

    # We got an error :(
    if isinstance(params, basestring):
        return params

    # Let's update all instances present in the query
    if params:
        query.update(params, False)

    session.commit()
    return dumps({'status': 'ok', 'message': 'You rock!'})


@api.route('/<modelname>/<int:instid>/', methods=('PUT',))
def update_instance(modelname, instid):
    """Calls the update method in a single instance

    The ``request.data`` var will be loaded as a JSON and all of the
    fields are going to be passed to the .update() method.
    """
    model = getattr(CONFIG['models'], modelname)
    try:
        data = loads(request.data)
    except JSONDecodeError:
        return dumps({'status': 'error', 'message': 'Unable to decode data'})

    inst = model.get_by(id=instid)
    relations = set(update_relations(model, [inst], data))
    field_list = set(data.keys()) ^ relations
    params = _validate_field_list(modelname, data, field_list)

    # We got an error :(
    if isinstance(params, basestring):
        return params

    # Let's update field by field
    for field in field_list:
        setattr(inst, field, params[field])
    session.commit()
    return dumps({'status': 'ok', 'message': 'You rock!'})


@api.route('/<modelname>/<int:instid>/')
def get(modelname, instid):
    """Returns a json representation of an instance of a model.

    It's an http binding to the ``get_by`` method of a model that
    returns data of an instance of a given model.

    ``modelname``

        The model that get_by is going to be called

    `instid`

        Instance id
    """
    model = getattr(CONFIG['models'], modelname)
    inst = model.get_by(id=instid)
    if inst is None:
        abort(404)

    relations = model.get_relations()
    deep = dict(zip(relations, [{}]*len(relations)))
    return dumps(inst.to_dict(deep))


@api.route('/<modelname>/<int:instid>/', methods=('DELETE',))
def delete(modelname, instid):
    """Removes an instance from the database based on its id
    """
    model = getattr(CONFIG['models'], modelname)
    inst = model.get_by(id=instid)
    if inst is not None:
        inst.delete()
    return dumps({'status': 'ok'})
