.. _creating:

Creating resources
==================

For the purposes of concreteness in this section, suppose we have executed the
following code on the server::

    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy
    from flask_restless import APIManager

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
    db = SQLAlchemy(app)

    class Person(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.Unicode)

    db.create_all()
    manager = APIManager(app, flask_sqlalchemy_db=db)
    manager.create_api(Person, methods=['POST'])

To create a new resource, the request

.. sourcecode:: http

   POST /api/person HTTP/1.1
   Host: example.com
   Content-Type: application/vnd.api+json
   Accept: application/vnd.api+json

   {
     "data": {
       "type": "person",
       "attributes": {
         "name": "foo"
       }
     }
   }

yields the response

.. sourcecode:: http

   HTTP/1.1 201 Created
   Location: http://example.com/api/person/1
   Content-Type: application/vnd.api+json

   {
     "data": {
       "attributes": {
         "name": "foo"
       },
       "id": "1",
       "jsonapi": {
         "version": "1.0"
       },
       "links": {
         "self": "http://example.com/api/person/bd34b544-ad39-11e5-a2aa-4cbb58b9ee34"
       },
       "meta": {},
       "type": "person"
     }
   }

To create a new resource with a client-generated ID (if enabled by setting
``allow_client_generated_ids`` to ``True`` in :meth:`.APIManager.create_api`),
the request

.. sourcecode:: http

   POST /api/person HTTP/1.1
   Host: example.com
   Content-Type: application/vnd.api+json
   Accept: application/vnd.api+json

   {
     "data": {
       "type": "person",
       "id": "bd34b544-ad39-11e5-a2aa-4cbb58b9ee34",
       "attributes": {
         "name": "foo"
       }
     }
   }

yields the response

.. sourcecode:: http

   HTTP/1.1 201 Created
   Location: http://example.com/api/person/bd34b544-ad39-11e5-a2aa-4cbb58b9ee34
   Content-Type: application/vnd.api+json

   {
     "data": {
       "attributes": {
         "name": "foo"
       },
       "id": "bd34b544-ad39-11e5-a2aa-4cbb58b9ee34",
       "links": {
         "self": "http://example.com/api/person/bd34b544-ad39-11e5-a2aa-4cbb58b9ee34"
       },
       "meta": {},
       "jsonapi": {
         "version": "1.0"
       },
       "type": "person"
     }
   }

The server always responds with :http:statuscode:`201` and a complete resource
object on a request with a client-generated ID.

The server will respond with :http:statuscode:`400` if the request specifies a
field that does not exist on the model.
