Request preprocessors and postprocessors
========================================

To apply a function to the request parameters and/or body before the request is
processed, use the ``preprocessors`` keyword argument. To apply a function to
the response data after the request is processed (immediately before the
response is sent), use the ``postprocessors`` keyword argument. Both
``preprocessors`` and ``postprocessors`` must be a dictionary which maps HTTP
method names as strings (with exceptions as described below) to a list of
functions. The specified functions will be applied in the order given in the
list.

There are many different routes on which you can apply preprocessors and
postprocessors, depending on HTTP method type, whether the client is accessing
a resource or a relationship, whether the client is accessing a collection or a
single resource, etc.

This table states the preprocessors that apply to each type of endpoint.

    ======================== ========================================
    preprocessor name        applies to URLs like…
    ======================== ========================================
    ``GET_COLLECTION``       ``/api/person``
    ``GET_RESOURCE``         ``/api/person/1``
    ``GET_RELATION``         ``/api/person/1/articles``
    ``GET_RELATED_RESOURCE`` ``/api/person/1/articles/2``

    ``DELETE_RESOURCE``      ``/api/person/1``

    ``POST_RESOURCE``        ``/api/person``

    ``PATCH_RESOURCE``       ``/api/person/1``

    ``GET_RELATIONSHIP``     ``/api/person/1/relationships/articles``
    ``DELETE_RELATIONSHIP``  ``/api/person/1/relationships/articles``
    ``POST_RELATIONSHIP``    ``/api/person/1/relationships/articles``
    ``PATCH_RELATIONSHIP``   ``/api/person/1/relationships/articles``
    ======================== ========================================

This table states the postprocessors that apply to each type of endpoint.

    ============================ ========================================
    postprocessor name           applies to URLs like…
    ============================ ========================================
    ``GET_COLLECTION``           ``/api/person``
    ``GET_RESOURCE``             ``/api/person/1``
    ``GET_TO_MANY_RELATION``     ``/api/person/1/articles``
    ``GET_TO_ONE_RELATION``      ``/api/articles/1/author``
    ``GET_RELATED_RESOURCE``     ``/api/person/1/articles/2``

    ``DELETE_RESOURCE``          ``/api/person/1``

    ``POST_RESOURCE``            ``/api/person``

    ``PATCH_RESOURCE``           ``/api/person/1``

    ``GET_TO_MANY_RELATIONSHIP`` ``/api/person/1/relationships/articles``
    ``GET_TO_ONE_RELATIONSHIP``  ``/api/articles/1/relationships/author``
    ``GET_RELATIONSHIP``         ``/api/person/1/relationships/articles``
    ``DELETE_RELATIONSHIP``      ``/api/person/1/relationships/articles``
    ``POST_RELATIONSHIP``        ``/api/person/1/relationships/articles``
    ``PATCH_RELATIONSHIP``       ``/api/person/1/relationships/articles``
    ============================ ========================================

Each type of preprocessor or postprocessor requires different
arguments. For preprocessors:

    ======================== ===================================================================================
    preprocessor name        keyword arguments
    ======================== ===================================================================================
    ``GET_COLLECTION``       ``filters``, ``sort``, ``group_by``, ``single``
    ``GET_RESOURCE``         ``resource_id``
    ``GET_RELATION``         ``resource_id``, ``relation_name``, ``filters``, ``sort``, ``group_by``, ``single``
    ``GET_RELATED_RESOURCE`` ``resource_id``, ``relation_name``, ``related_resource_id``

    ``DELETE_RESOURCE``      ``resource_id``

    ``POST_RESOURCE``        ``data``

    ``PATCH_RESOURCE``       ``resource_id``, ``data``

    ``GET_RELATIONSHIP``     ``resource_id``, ``relation_name``
    ``DELETE_RELATIONSHIP``  ``resource_id``, ``relation_name``
    ``POST_RELATIONSHIP``    ``resource_id``, ``relation_name``, ``data``
    ``PATCH_RELATIONSHIP``   ``resource_id``, ``relation_name``, ``data``
    ======================== ===================================================================================

For postprocessors:

    ============================ ===========================================================
    postprocessor name            keyword arguments
    ============================ ===========================================================
    ``GET_COLLECTION``           ``result``, ``filters``, ``sort``, ``group_by``, ``single``
    ``GET_RESOURCE``             ``result``
    ``GET_TO_MANY_RELATION``     ``result``, ``filters``, ``sort``, ``group_by``, ``single``
    ``GET_TO_ONE_RELATION``      ``result``
    ``GET_RELATED_RESOURCE``     ``result``

    ``DELETE_RESOURCE``          ``was_deleted``

    ``POST_RESOURCE``            ``result``

    ``PATCH_RESOURCE``           ``result``

    ``GET_TO_MANY_RELATIONSHIP`` ``result``, ``filters``, ``sort``, ``group_by``, ``single``
    ``GET_TO_ONE_RELATIONSHIP``  ``result``
    ``DELETE_RELATIONSHIP``      ``was_deleted``
    ``POST_RELATIONSHIP``        none
    ``PATCH_RELATIONSHIP``       none
    ============================ ===========================================================

How can one use these tables to create a preprocessor or postprocessor? If you
want to create a preprocessor that will be applied on :http:method:`get`
requests to ``/api/person``, first define a function that accepts the keyword
arguments you need, and has a ``**kw`` argument for any additional keyword
arguments (and any new arguments that may appear in future versions of
Flask-Restless)::

    def fetch_preprocessor(filters=None, sort=None, group_by=None, single=None,
                           **kw):
        # Here perform any application-specific code...

Next, instruct these preprocessors to be applied by Flask-Restless by using the
``preprocessors`` keyword argument to :meth:`.APIManager.create_api`. The value
of this argument must be a dictionary in which each key is a string containing
a processor name and each value is a list of functions to be applied for that
request::

    preprocessors = {'GET_COLLECTION': [fetch_preprocessor]}
    manager.create_api(Person, preprocessors=preprocessors)

For preprocessors for endpoints of the form ``/api/person/1``, a returned value
will be interpreted as the resource ID for the request. (Remember, as described
in :ref:`idstring`, the returned ID must be a string.) For example, if a
preprocessor for a :http:method:`get` request to ``/api/person/1`` returns the
string ``'foo'``, then Flask-Restless will behave as if the request were
originally for the URL ``/api/person/foo``.  For preprocessors for endpoints of
the form ``/api/person/1/articles`` or
``/api/person/1/relationships/articles``, the function can return either one
value, in which case the resource ID will be replaced with the return value, or
a two-tuple, in which case both the resource ID and the relationship name will
be replaced. Finally, for preprocessors for endpoints of the form
``/api/person/1/articles/2``, the function can return one, two, or three
values; if three values are returned, the resource ID, the relationship name,
and the related resource ID are all replaced. (If multiple preprocessors are
specified for a single HTTP method and each one has a return value,
Flask-Restless will only remember the value returned by the last preprocessor
function.)

Those preprocessors and postprocessors that accept dictionaries as parameters
can (and should) modify their arguments *in-place*. That means the changes made
to, for example, the ``result`` dictionary will be seen by the Flask-Restless
view functions and ultimately returned to the client.

.. note::

   For more information about the ``filters`` and ``single`` keyword arguments,
   see :doc:`filtering`. For more information about ``sort`` and ``group_by``
   keyword arguments, see :doc:`sorting`.

In order to halt the preprocessing or postprocessing and return an error
response directly to the client, your preprocessor or postprocessor functions
can raise a :exc:`.ProcessingException`. If a function raises this exception,
no preprocessing or postprocessing functions that appear later in the list
specified when the API was created will be invoked. For example, an
authentication function can be implemented like this::

    def check_auth(resource_id=None, **kw):
        # Here, get the current user from the session.
        current_user = ...
        # Next, check if the user is authorized to modify the specified
        # instance of the model.
        if not is_authorized_to_modify(current_user, instance_id):
            raise ProcessingException(detail='Not Authorized', status=401)
    manager.create_api(Person, preprocessors=dict(GET_SINGLE=[check_auth]))

The :exc:`.ProcessingException` allows you to specify as keyword arguments to
the constructor the elements of the JSON API `error object`_. If no arguments
are provided, the error is assumed to have status code :http:statuscode:`400`.

.. _error object: https://jsonapi.org/format/#error-objects

.. _universal:

Universal preprocessors and postprocessors
------------------------------------------

.. versionadded:: 0.13.0

The previous section describes how to specify a preprocessor or postprocessor
on a per-API (that is, a per-model) basis. If you want a function to be
executed for *all* APIs created by a :class:`.APIManager`, you can use the
``preprocessors`` or ``postprocessors`` keyword arguments in the constructor of
the :class:`.APIManager` class. These keyword arguments have the same format as
the corresponding ones in the :meth:`.APIManager.create_api` method as
described above. Functions specified in this way are prepended to the list of
preprocessors or postprocessors specified in the :meth:`.APIManager.create_api`
method.

This may be used, for example, if all :http:method:`post` requests require
authentication::

    from flask import Flask
    from flask_restless import APIManager
    from flask_restless import ProcessingException
    from flask_login import current_user
    from mymodels import User
    from mymodels import session

    def auth_func(*args, **kw):
        if not current_user.is_authenticated():
            raise ProcessingException(detail='Not authenticated', status=401)

    app = Flask(__name__)
    preprocessors = {'POST_RESOURCE': [auth_func]}
    api_manager = APIManager(app, session=session, preprocessors=preprocessors)
    api_manager.create_api(User)

Preprocessors for collections
-----------------------------

When the server receives, for example, a :http:method:`get` request for
``/api/person``, Flask-Restless interprets this request as a search with no
filters (that is, a search for all instances of ``Person`` without
exception). In other words, a :http:method:`get` request to ``/api/person`` is
roughly equivalent to the same request to
``/api/person?filter[objects]=[]``. Therefore, if you want to filter the set of
``Person`` instances returned by such a request, you can create a
``GET_COLLECTION`` preprocessor that *appends filters* to the ``filters``
keyword argument. For example::

    def preprocessor(filters=None, **kw):
        # This checks if the preprocessor function is being called before a
        # request that does not have search parameters.
        if filters is None:
            return
        # Create the filter you wish to add; in this case, we include only
        # instances with ``id`` not equal to 1.
        filt = dict(name='id', op='neq', val=1)
        # *Append* your filter to the list of filters.
        filters.append(filt)

    preprocessors = {'GET_COLLECTION': [preprocessor]}
    manager.create_api(Person, preprocessors=preprocessors)


When does the session get committed?
------------------------------------

For requests to create a resource, update a resource, or delete a resource, the
session is flushed *before* the postprocessor is executed and committed
*after*. Therefore, if a postprocessor raises a :exc:`.ProcessingException`,
then the session has *not* been committed, so your code can then decide to, for
example, roll back the session or commit it.


.. _authentication:

Requiring authentication for some methods
-----------------------------------------

If you want certain HTTP methods to require authentication, use preprocessors::

    from flask import Flask
    from flask_restless import APIManager
    from flask_restless import ProcessingException
    from flask_login import current_user
    from mymodels import User

    def auth_func(*args, **kwargs):
        if not current_user.is_authenticated():
            raise ProcessingException(detail='Not authenticated', status=401)

    app = Flask(__name__)
    api_manager = APIManager(app)
    # Set `auth_func` to be a preprocessor for any type of endpoint you want to
    # be guarded by authentication.
    preprocessors = {'GET_RESOURCE': [auth_func], ...}
    api_manager.create_api(User, preprocessors=preprocessors)

For a more complete example using `Flask-Login`_, see the
:file:`examples/server_configurations/authentication` directory in the source
distribution, or `view the authentication example online`_.

.. _Flask-Login: https://packages.python.org/Flask-Login
.. _view the authentication example online: https://github.com/jfinkels/flask-restless/tree/master/examples/server_configurations/authentication
