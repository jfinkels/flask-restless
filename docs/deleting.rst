Deleting resources
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

    db.create_all()
    manager = APIManager(app, flask_sqlalchemy_db=db)
    manager.create_api(Person, methods=['DELETE'])

To delete a resource, the request

.. sourcecode:: http

   DELETE /api/person/1 HTTP/1.1
   Host: example.com
   Accept: application/vnd.api+json

yields a :http:statuscode:`204` response.
