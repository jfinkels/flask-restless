import flask
import flask.ext.restless
from sqlalchemy import create_engine
from sqlalchemy import Column, ForeignKey
from sqlalchemy import Date, DateTime, Integer, Unicode
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import relationship, backref

# Create the declarative base class for the SQLAlchemy models.
Base = declarative_base()


# Create your SQLALchemy models as usual but with the following two
# (reasonable) restrictions:
#   1. They must have an id column of type Integer.
#   2. They must have an __init__ method which accepts keyword arguments for
#      all columns (the constructor in Base supplies such a method, so you
#      don't need to declare a new one).
class Person(Base):
    __tablename__ = 'person'
    id = Column(Integer, primary_key=True)
    name = Column(Unicode, unique=True)
    birth_date = Column(Date)
    computers = relationship('Computer', backref=backref('owner',
                                                         lazy='dynamic'))


class Computer(Base):
    __tablename__ = 'computer'
    id = Column(Integer, primary_key=True)
    name = Column(Unicode, unique=True)
    vendor = Column(Unicode)
    owner_id = Column(Integer, ForeignKey('person.id'))
    purchase_time = Column(DateTime)


# Basic SQLAlchemy setup is the same.
engine = create_engine('sqlite:////tmp/mydatabase.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Create the Flask application and register it with the APIManager.
app = flask.Flask(__name__)
app.config['DEBUG'] = True
manager = flask.ext.restless.APIManager(app)

# Create API endpoints, which will be available at /api/<tablename> by
# default. Allowed HTTP methods can be specified as well. We create a different
# session for each API, but you could use the same session.
manager.create_api(Session(), Person, methods=['GET', 'POST', 'DELETE'])
manager.create_api(Session(), Computer, methods=['GET'])

# start the flask loop
app.run()
