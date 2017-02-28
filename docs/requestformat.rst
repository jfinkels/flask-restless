Requests and responses
======================

Requests and responses are all in the JSON API format, so each request must
include an :http:header:`Accept` header whose value is
:mimetype:`application/vnd.api+json` and any request that contains content must
include a :http:header:`Content-Type` header whose value is
:mimetype:`application/vnd.api+json`. If they do not, the client will receive
an error response.

This section of the documentation assumes some familiarity with the JSON API
specification.

.. toctree::
   :maxdepth: 2

   fetching
   creating
   deleting
   updating
   updatingrelationships

Schema at root endpoint
-----------------------

A :http:method:`GET` request to the root endpoint responds with a valid JSON
API document whose ``meta`` element contains a ``modelinfo`` object, which
itself contains one member for each resource object exposed by the API. Each
element in ``modelinfo`` contains information about that resource. For example,
a request like

.. sourcecode:: http

   GET /api HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields the response

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/vnd.api+json

   {
     "data": null,
     "jsonapi": {
       "version": "1.0"
     },
     "included": [],
     "links": {},
     "meta": {
       "modelinfo": {
         "article": {
           "primarykey": "id",
           "url": "http://example.com/api/article"
         },
         "person": {
           "primarykey": "id",
           "url": "http://example.com/api/person"
         }
       }
     }
   }

.. _idstring:

Resource ID must be a string
----------------------------

As required by the JSON API, the ID (and type) of a resource must be a string
in request and response documents. This does *not* mean that the primary key in
the database must be a string, only that it will appear as a string in
communications between the client and the server. For more information, see the
`Identification`_ section of the JSON API specification.

.. _Identification: http://jsonapi.org/format/#document-resource-object-identification

.. _slashes:

Trailing slashes in URLs
------------------------

API endpoints do not have trailing slashes. A :http:method:`get` request to,
for example, ``/api/person/`` will result in a :http:statuscode:`404` response.

.. _dateandtime:

Date and time fields
--------------------

Flask-Restless will automatically parse and convert date and time strings into
the corresponding Python objects. Flask-Restless also understands intervals
(also known as *durations*), if you specify the interval as an integer
representing the number of units that the interval spans.

If you want the server to set the value of a date or time field of a model as
the current time (as measured at the server), use one of the special strings
``"CURRENT_TIMESTAMP"``, ``"CURRENT_DATE"``, or ``"LOCALTIMESTAMP"``. When the
server receives one of these strings in a request, it will use the
corresponding SQL function to set the date or time of the field in the model.

.. _errors:

Errors and error messages
-------------------------

Flask-Restless returns the error responses required by the JSON API
specification, and most other server errors yield a
:http:statuscode:`400`. Errors are included in the ``errors`` element in the
top-level JSON document in the response body.

If a request triggers a :exc:`sqlalchemy.exc.SQLAlchemyError` (or any subclass
of that exception, including :exc:`~sqlalchemy.exc.DataError`,
:exc:`~sqlalchemy.exc.IntegrityError`, :exc:`~sqlalchemy.exc.ProgrammingError`,
etc.), the session will be rolled back

.. _jsonp:

JSONP callbacks
---------------

Flask-Restless responds to JavaScript clients that request JSONP responses. Add
a ``callback=myfunc`` query parameter to the request URL on any request that
yields a response that contains content (including endpoints for function
evaluation; see :doc:`functionevaluation`) to have the JSON data of the
response wrapped in the Javascript function ``myfunc``. This can be used to
circumvent some cross domain scripting security issues.

The :http:header:`Content-Type` of a JSONP response is
:mimetype:`application/javascript` instead of
:mimetype:`application/vnd.api+json` because the payload of such a response is
not valid JSON API.

For example, a request like this:

.. sourcecode:: http

   GET /api/person/1?callback=foo HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

will produce a response like this:

.. sourcecode:: http

   HTTP/1.1 200 OK
   Content-Type: application/javascript

   foo({"meta": {/*...*/}, "data": {/*...*/}})

Then in your Javascript client code, write the function ``foo`` like this:

.. sourcecode:: javascript

   function foo(response) {
     var meta, data;
     meta = response.meta;
     data = response.data;
     // Do something cool here...
   }

.. COMMENT

   The metadata includes the status code and the values of the HTTP headers,
   including the `Link headers <https://tools.ietf.org/html/rfc5988>`_ parsed
   in JSON format. For example, a link that looks like this:

   .. This is adapted from the GitHub API documentation; see
   .. <http://developer.github.com/v3/#json-p-callbacks> for more information.

   .. sourcecode:: http

      Link: <url1>; rel="next", <url2>; rel="foo"; bar="baz"

   will look like this in the JSON metadata:

   .. sourcecode:: javascript

      [
        {"url": "url1", "rel": "next"},
        {"url": "url2", "rel": "foo", "bar": "baz"}
      ]


JSON API extensions
-------------------

Flask-Restless does not yet support the in-development `JSON API extension
system`_.

.. _JSON API extension system: http://jsonapi.org/extensions/


Cross-Origin Resource Sharing (CORS)
------------------------------------

`Cross-Origin Resource Sharing (CORS)`_ is a protocol that allows JavaScript
HTTP clients to make HTTP requests across Internet domain boundaries while
still protecting against cross-site scripting (XSS) attacks. If you have access
to the HTTP server that serves your Flask application, I recommend configuring
CORS there, since such concerns are beyond the scope of Flask-Restless.
However, in case you need to support CORS at the application level, you should
create a function that adds the necessary HTTP headers after the request has
been processed by Flask-Restless (that is, just before the HTTP response is
sent from the server to the client) using the
:meth:`flask.Blueprint.after_request` method::

    from flask import Flask
    from flask_restless import APIManager

    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = 'example.com'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        # Set whatever other headers you like...
        return response

    app = Flask(__name__)
    manager = APIManager(app)
    blueprint = manager.create_api_blueprint('mypersonapi', Person)
    blueprint.after_request(add_cors_headers)
    app.register_blueprint(blueprint)

.. _Cross-Origin Resource Sharing (CORS): http://enable-cors.org
