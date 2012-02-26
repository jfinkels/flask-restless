from formencode import Schema, validators

class Computer(Schema):
    name = validators.UnicodeString(not_empty=True)
    vendor = validators.UnicodeString(not_empty=True)
    buy_date = validators.DateConverter(
        if_missing=None, month_style='dd/mm/yyyy')

class Person(Schema):
    name = validators.UnicodeString(not_empty=True)
    age = validators.Number(not_empty=True)
    other = validators.Number(not_empty=False, if_missing=0)
    birth_date = validators.DateConverter(
        if_missing=None, month_style='dd/mm/yyyy')
    computers = validators.Set()

allvalidators = dict(Computer=Computer, Person=Person)
