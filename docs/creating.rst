.. _creating:

Creating resources
==================

For the purposes of concreteness in this section, suppose we have executed the
following code on the server::

    from flask import Flask
    from flask.ext.sqlalchemy import SQLAlchemy
    from flask.ext.restless import APIManager

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
       "name": "foo"
     }
   }

yields the response

.. sourcecode:: http

   HTTP/1.1 201 Created
   Content-Type: application/vnd.api+json

   {
     "data": {
       "id": "1",
       "name": "foo",
       "type": "person"
     }
   }

The server will respond with :http:statuscode:`400` if the request specifies a
field that does not exist on the model.
