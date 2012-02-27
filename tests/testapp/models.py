from restful.model import Entity
from elixir import metadata, setup_all, session, Field, Float, Unicode, \
    ManyToOne, OneToMany, Date, DateTime

class Computer(Entity):
    name = Field(Unicode, unique=True)
    vendor = Field(Unicode)
    owner = ManyToOne('Person')
    buy_date = Field(DateTime)

class Person(Entity):
    name = Field(Unicode, unique=True)
    age = Field(Float)
    other = Field(Float)
    computers = OneToMany('Computer')
    birth_date = Field(Date)

def setup(uri):
    metadata.bind = uri
    metadata.bind.echo = False
    setup_all()
