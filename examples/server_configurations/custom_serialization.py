"""
    Using Marshmallow for serialization
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This provides an example of using `Marshmallow
    <https://marshmallow.readthedocs.org>`_ schema to provide custom
    serialization from SQLAlchemy models to Python dictionaries and the
    converse deserialization.

    :copyright: 2015 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.restless import APIManager
from marshmallow import Schema
from marshmallow import fields

app = Flask(__name__)
app.config['DEBUG'] = True
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
db = SQLAlchemy(app)


class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode)
    #birth_date = db.Column(db.Date)


class PersonSchema(Schema):
    id = fields.Integer()
    name = fields.String()

    def make_object(self, data):
        return Person(**data)

person_schema = PersonSchema()

def person_serializer(instance):
    return person_schema.dump(instance).data

def person_deserializer(data):
    return person_schema.load(data).data

db.create_all()
manager = APIManager(app, flask_sqlalchemy_db=db)
manager.create_api(Person, methods=['GET', 'POST'],
                   serializer=person_serializer,
                   deserializer=person_deserializer)

app.run()
