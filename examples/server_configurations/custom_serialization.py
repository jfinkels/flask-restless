# custom_serialization.py - using Marshmallow serialization with Flask-Restless
#
# Copyright 2011 Lincoln de Sousa <lincoln@comum.org>.
# Copyright 2012, 2013, 2014, 2015, 2016 Jeffrey Finkelstein
#           <jeffrey.finkelstein@gmail.com> and contributors.
#
# This file is part of Flask-Restless.
#
# Flask-Restless is distributed under both the GNU Affero General Public
# License version 3 and under the 3-clause BSD license. For more
# information, see LICENSE.AGPL and LICENSE.BSD.
"""Using Marshmallow for serialization in Flask-Restless.

This script is an example of using `Marshmallow`_ to provide custom
serialization (and the corresponding deserialization) from SQLAlchemy
models to Python dictionaries that will eventually become JSON API
responses to the client. Specifically, this example uses the
`marshmallow-jsonapi`_ library to create serialization/deserialization
functions for use with Flask-Restless.

There are some problems with this approach. You will need to specify
some configuration twice, once for marshmallow-jsonapi and once for
Flask-Restless. For example, you must provide a custom "collection name"
as both the class-level attribute :attr:`Meta.type_` and as the
*collection_name* keyword argument to :meth:`APIManager.create_api`. For
another example, you must specify the URLs for relationships and related
resources directly in the schema definition, and thus these must match
EXACTLY the URLs created by Flask-Restless. The URLs created by
Flask-Restless are fairly predictable, so this requirement, although not
ideal, should not be too challenging.

(This example might have used the `marshmallow-sqlalchemy`_ model to
mitigate some of these issues, but there does not seem to be an easy way
to combine these two Marshmallow layers together.)

To install the necessary requirements for this example, run::

    pip install flask-restless flask-sqlalchemy marshmallow-jsonapi

To run this script from the current directory::

    python -m custom_serialization

This will run a Flask server at ``http://localhost:5000``. You can then
make requests using any web client.

.. _Marshmallow: https://marshmallow.readthedocs.org
.. _marshmallow-sqlalchemy: https://marshmallow-sqlalchemy.readthedocs.org
.. _marshmallow-jsonapi: https://marshmallow-jsonapi.readthedocs.org

"""
from functools import partial

from flask import Flask
from flask.ext.restless import APIManager
from flask.ext.sqlalchemy import SQLAlchemy
from marshmallow import post_load
from marshmallow_jsonapi import fields
from marshmallow_jsonapi import Schema

## Flask application and database configuration ##

app = Flask(__name__)
app.config['DEBUG'] = True
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
db = SQLAlchemy(app)

## Flask-SQLAlchemy model definitions ##


class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode)


class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Unicode)
    author_id = db.Column(db.Unicode, db.ForeignKey(Person.id))
    author = db.relationship(Person, backref=db.backref('articles'))


## Marshmallow schema definitions ##

class PersonSchema(Schema):

    class Meta:
        model = Person
        type_ = 'person'
        sqla_session = db.session
        strict = True

    id = fields.Integer(dump_only=True)
    name = fields.Str()

    articles = fields.Relationship(
        self_url='/api/person/{personid}/relationships/articles',
        self_url_kwargs={'personid': '<id>'},
        related_url='/api/article/{articleid}',
        related_url_kwargs={'articleid': '<id>'}
    )

    @post_load
    def make_person(self, data):
        return Person(**data)


class ArticleSchema(Schema):

    class Meta:
        model = Article
        type_ = 'article'
        sqla_session = db.session
        strict = True

    id = fields.Integer(dump_only=True)
    title = fields.Str()

    author = fields.Relationship(
        self_url='/api/article/{articleid}/relationships/author',
        self_url_kwargs={'articleid': '<id>'},
        related_url='/api/person/{personid}',
        related_url_kwargs={'personid': '<id>'}
    )

    @post_load
    def make_article(self, data):
        return Article(**data)

person_schema = PersonSchema()
article_schema = ArticleSchema()


## Serializer and deserializer functions ##

def _dump(schema, instance, only=None):
    # In this example, we will ignore the `only` keyword argument, which
    # is the client's request for which fields to include in the response.
    return schema.dump(instance).data


def _load(schema, document):
    return schema.load(document).data


person_serializer = partial(_dump, person_schema)
person_deserializer = partial(_load, person_schema)

article_serializer = partial(_dump, article_schema)
article_deserializer = partial(_load, article_schema)

db.create_all()
manager = APIManager(app, flask_sqlalchemy_db=db)
manager.create_api(Person, methods=['GET', 'POST'],
                   serializer=person_serializer,
                   deserializer=person_deserializer)
manager.create_api(Article, methods=['GET', 'POST'],
                   serializer=article_serializer,
                   deserializer=article_deserializer)

app.run()
