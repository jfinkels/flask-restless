Quickstart
==========

For the restless::

    import flask.ext.restless
    from elixir import Date, DateTime, Field, Unicode
    from elixir import ManyToOne, OneToMany
    from elixir import create_all, metadata, setup_all

    # Entity classes must inherit from flaskext.restless.Entity. Other than
    # that, the definition of the model is exactly the same.
    class Person(flask.ext.restless.Entity):
        name = Field(Unicode, unique=True)
        birth_date = Field(Date)
        computers = OneToMany('Computer')

    class Computer(flask.ext.restless.Entity):
        name = Field(Unicode, unique=True)
        vendor = Field(Unicode)
        owner = ManyToOne('Person')
        purchase_time = Field(DateTime)

    # Basic Elixir setup is the same.
    metadata.bind = create_engine('sqlite:////tmp/test.db')
    metadata.bind.echo = False
    setup_all()
    create_all()    

    # Create the Flask application and register it with the APIManager.
    app = flask.Flask(__name__)
    manager = flask.ext.restless.APIManager(app)

    # Create API endpoints, which will be available at /api/<modelname> by
    # default (with the lowercase form of the model name). Allowed HTTP methods
    # can be specified as well.
    manager.create_api(Person, methods=['GET', 'PATCH', 'POST', 'DELETE'])
    manager.create_api(Computer, methods=['GET'])
