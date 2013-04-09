"""
    tests.test_manager
    ~~~~~~~~~~~~~~~~~~

    Provides unit tests for the :mod:`flask_restless.manager` module.

    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
import datetime
from unittest2 import skipUnless
from unittest2 import TestSuite

from flask import json
try:
    from flask.ext.sqlalchemy import SQLAlchemy
except:
    has_flask_sqlalchemy = False
else:
    has_flask_sqlalchemy = True

from flask.ext.restless import APIManager
from flask.ext.restless.helpers import get_columns

from .helpers import FlaskTestBase
from .helpers import TestSupport


__all__ = ['APIManagerTest']


dumps = json.dumps
loads = json.loads


class APIManagerTest(TestSupport):
    """Unit tests for the :class:`flask_restless.manager.APIManager` class.

    """

    def test_constructor(self):
        """Tests that no error occurs on instantiation without any arguments to
        the constructor.

        """
        APIManager()

    def test_init_app(self):
        """Tests for initializing the Flask application after instantiating the
        :class:`flask.ext.restless.APIManager` object.

        """
        # initialize the Flask application
        self.manager.init_app(self.flaskapp, self.session)

        # create an API
        self.manager.create_api(self.Person)

        # make a request on the API
        #client = app.test_client()
        response = self.app.get('/api/person')
        self.assertEqual(response.status_code, 200)

    def test_create_api(self):
        """Tests that the :meth:`flask_restless.manager.APIManager.create_api`
        method creates endpoints which are accessible by the client, only allow
        specified HTTP methods, and which provide a correct API to a database.

        """
        # create three different APIs for the same model
        self.manager.create_api(self.Person, methods=['GET', 'POST'])
        self.manager.create_api(self.Person, methods=['PATCH'],
                                url_prefix='/api2')
        self.manager.create_api(self.Person, methods=['GET'],
                                url_prefix='/readonly')

        # test that specified endpoints exist
        response = self.app.post('/api/person', data=dumps(dict(name='foo')))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(loads(response.data)['id'], 1)
        response = self.app.get('/api/person')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(loads(response.data)['objects']), 1)
        self.assertEqual(loads(response.data)['objects'][0]['id'], 1)

        # test that non-specified methods are not allowed
        response = self.app.delete('/api/person/1')
        self.assertEqual(response.status_code, 405)
        response = self.app.patch('/api/person/1',
                                  data=dumps(dict(name='bar')))
        self.assertEqual(response.status_code, 405)

        # test that specified endpoints exist
        response = self.app.patch('/api2/person/1',
                                  data=dumps(dict(name='bar')))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['id'], 1)
        self.assertEqual(loads(response.data)['name'], 'bar')

        # test that non-specified methods are not allowed
        response = self.app.get('/api2/person/1')
        self.assertEqual(response.status_code, 405)
        response = self.app.delete('/api2/person/1')
        self.assertEqual(response.status_code, 405)
        response = self.app.post('/api2/person',
                                 data=dumps(dict(name='baz')))
        self.assertEqual(response.status_code, 405)

        # test that the model is the same as before
        response = self.app.get('/readonly/person')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(loads(response.data)['objects']), 1)
        self.assertEqual(loads(response.data)['objects'][0]['id'], 1)
        self.assertEqual(loads(response.data)['objects'][0]['name'], 'bar')

    def test_different_collection_name(self):
        """Tests that providing a different collection name exposes the API at
        the corresponding URL.

        """
        self.manager.create_api(self.Person, methods=['POST', 'GET'],
                                collection_name='people')

        response = self.app.post('/api/people', data=dumps(dict(name='foo')))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(loads(response.data)['id'], 1)

        response = self.app.get('/api/people')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(loads(response.data)['objects']), 1)
        self.assertEqual(loads(response.data)['objects'][0]['id'], 1)

        response = self.app.get('/api/people/1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['id'], 1)

    def test_allow_functions(self):
        """Tests that the ``allow_functions`` keyword argument makes a
        :http:get:`/api/eval/...` endpoint available.

        """
        self.manager.create_api(self.Person, allow_functions=True)
        response = self.app.get('/api/eval/person?q={}')
        self.assertNotEqual(response.status_code, 400)
        self.assertEqual(response.status_code, 204)

    def test_disallow_functions(self):
        """Tests that if the ``allow_functions`` keyword argument if ``False``,
        no endpoint will be made available at :http:get:`/api/eval/...`.

        """
        self.manager.create_api(self.Person, allow_functions=False)
        response = self.app.get('/api/eval/person')
        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(response.status_code, 404)

    def test_include_related(self):
        """Test for specifying included columns on related models."""
        date = datetime.date(1999, 12, 31)
        person = self.Person(name='Test', age=10, other=20, birth_date=date)
        computer = self.Computer(name='foo', vendor='bar', buy_date=date)
        self.session.add(person)
        person.computers.append(computer)
        self.session.commit()

        include = frozenset(['name', 'age', 'computers', 'computers.id',
                             'computers.name'])
        self.manager.create_api(self.Person, include_columns=include)
        include = frozenset(['name', 'age', 'computers.id', 'computers.name'])
        self.manager.create_api(self.Person, url_prefix='/api2',
                                include_columns=include)

        response = self.app.get('/api/person/%s' % person.id)
        person_dict = loads(response.data)
        for column in 'name', 'age', 'computers':
            self.assertIn(column, person_dict)
        for column in 'id', 'other', 'birth_date':
            self.assertNotIn(column, person_dict)
        for column in 'id', 'name':
            self.assertIn(column, person_dict['computers'][0])
        for column in 'vendor', 'owner_id', 'buy_date':
            self.assertNotIn(column, person_dict['computers'][0])

        response = self.app.get('/api2/person/%s' % person.id)
        self.assertNotIn('computers', loads(response.data))

    def test_exclude_related(self):
        """Test for specifying excluded columns on related models."""
        date = datetime.date(1999, 12, 31)
        person = self.Person(name='Test', age=10, other=20, birth_date=date)
        computer = self.Computer(name='foo', vendor='bar', buy_date=date)
        self.session.add(person)
        person.computers.append(computer)
        self.session.commit()

        exclude = frozenset(['name', 'age', 'computers', 'computers.id',
                             'computers.name'])
        self.manager.create_api(self.Person, exclude_columns=exclude)
        exclude = frozenset(['name', 'age', 'computers.id', 'computers.name'])
        self.manager.create_api(self.Person, url_prefix='/api2',
                                exclude_columns=exclude)

        response = self.app.get('/api/person/%s' % person.id)
        person_dict = loads(response.data)
        for column in 'name', 'age', 'computers':
            self.assertNotIn(column, person_dict)
        for column in 'id', 'other', 'birth_date':
            self.assertIn(column, person_dict)

        response = self.app.get('/api2/person/%s' % person.id)
        person_dict = loads(response.data)
        self.assertIn('computers', person_dict)
        for column in 'id', 'name':
            self.assertNotIn(column, person_dict['computers'][0])
        for column in 'vendor', 'owner_id', 'buy_date':
            self.assertIn(column, person_dict['computers'][0])

    def test_include_columns(self):
        """Tests that the `include_columns` argument specifies which columns to
        return in the JSON representation of instances of the model.

        """
        all_columns = get_columns(self.Person)
        # allow all
        self.manager.create_api(self.Person, include_columns=None,
                                url_prefix='/all')
        self.manager.create_api(self.Person, include_columns=all_columns,
                                url_prefix='/all2')
        # allow some
        self.manager.create_api(self.Person, include_columns=('name', 'age'),
                                url_prefix='/some')
        # allow none
        self.manager.create_api(self.Person, include_columns=(),
                                url_prefix='/none')

        # create a test person
        self.manager.create_api(self.Person, methods=['POST'],
                                url_prefix='/add')
        d = dict(name=u'Test', age=10, other=20,
                 birth_date=datetime.date(1999, 12, 31).isoformat())
        response = self.app.post('/add/person', data=dumps(d))
        self.assertEqual(response.status_code, 201)
        personid = loads(response.data)['id']

        # get all
        response = self.app.get('/all/person/%s' % personid)
        for column in 'name', 'age', 'other', 'birth_date', 'computers':
            self.assertIn(column, loads(response.data))
        response = self.app.get('/all2/person/%s' % personid)
        for column in 'name', 'age', 'other', 'birth_date', 'computers':
            self.assertIn(column, loads(response.data))

        # get some
        response = self.app.get('/some/person/%s' % personid)
        for column in 'name', 'age':
            self.assertIn(column, loads(response.data))
        for column in 'other', 'birth_date', 'computers':
            self.assertNotIn(column, loads(response.data))

        # get none
        response = self.app.get('/none/person/%s' % personid)
        for column in 'name', 'age', 'other', 'birth_date', 'computers':
            self.assertNotIn(column, loads(response.data))

    def test_exclude_columns(self):
        """Tests that the ``exclude_columns`` argument specifies which columns
        to exclude in the JSON representation of instances of the model.

        """
        all_columns = get_columns(self.Person)
        # allow all
        self.manager.create_api(self.Person, exclude_columns=None,
                                url_prefix='/all')
        self.manager.create_api(self.Person, exclude_columns=(),
                                url_prefix='/all2')
        # allow some
        exclude = ('other', 'birth_date', 'computers')
        self.manager.create_api(self.Person, exclude_columns=exclude,
                                url_prefix='/some')
        # allow none
        self.manager.create_api(self.Person, exclude_columns=all_columns,
                                url_prefix='/none')

        # create a test person
        self.manager.create_api(self.Person, methods=['POST'],
                                url_prefix='/add')
        d = dict(name=u'Test', age=10, other=20,
                 birth_date=datetime.date(1999, 12, 31).isoformat())
        response = self.app.post('/add/person', data=dumps(d))
        self.assertEqual(response.status_code, 201)
        personid = loads(response.data)['id']

        # get all
        response = self.app.get('/all/person/%s' % personid)
        for column in 'name', 'age', 'other', 'birth_date', 'computers':
            self.assertIn(column, loads(response.data))
        response = self.app.get('/all2/person/%s' % personid)
        for column in 'name', 'age', 'other', 'birth_date', 'computers':
            self.assertIn(column, loads(response.data))

        # get some
        response = self.app.get('/some/person/%s' % personid)
        for column in 'name', 'age':
            self.assertIn(column, loads(response.data))
        for column in 'other', 'birth_date', 'computers':
            self.assertNotIn(column, loads(response.data))

        # get none
        response = self.app.get('/none/person/%s' % personid)
        for column in 'name', 'age', 'other', 'birth_date', 'computers':
            self.assertNotIn(column, loads(response.data))

    def test_different_urls(self):
        """Tests that establishing different URL endpoints for the same model
        affect the same database table.

        """
        methods = frozenset(('get', 'patch', 'post', 'delete'))
        # create a separate endpoint for each HTTP method
        for method in methods:
            url = '/%s' % method
            self.manager.create_api(self.Person, methods=[method.upper()],
                                    url_prefix=url)

        # test for correct requests
        response = self.app.get('/get/person')
        self.assertEqual(response.status_code, 200)
        response = self.app.post('/post/person', data=dumps(dict(name='Test')))
        self.assertEqual(response.status_code, 201)
        response = self.app.patch('/patch/person/1',
                                  data=dumps(dict(name='foo')))
        self.assertEqual(response.status_code, 200)
        response = self.app.delete('/delete/person/1')
        self.assertEqual(response.status_code, 204)

        # test for incorrect requests
        response = self.app.get('/post/person')
        self.assertEqual(response.status_code, 405)
        response = self.app.get('/patch/person/1')
        self.assertEqual(response.status_code, 405)
        response = self.app.get('/delete/person/1')
        self.assertEqual(response.status_code, 405)

        response = self.app.post('/get/person')
        self.assertEqual(response.status_code, 405)
        response = self.app.post('/patch/person/1')
        self.assertEqual(response.status_code, 405)
        response = self.app.post('/delete/person/1')
        self.assertEqual(response.status_code, 405)

        response = self.app.patch('/get/person')
        self.assertEqual(response.status_code, 405)
        response = self.app.patch('/post/person')
        self.assertEqual(response.status_code, 405)
        response = self.app.patch('/delete/person/1')
        self.assertEqual(response.status_code, 405)

        response = self.app.delete('/get/person')
        self.assertEqual(response.status_code, 405)
        response = self.app.delete('/post/person')
        self.assertEqual(response.status_code, 405)
        response = self.app.delete('/patch/person/1')
        self.assertEqual(response.status_code, 405)

        # test that the same model is updated on all URLs
        response = self.app.post('/post/person', data=dumps(dict(name='Test')))
        self.assertEqual(response.status_code, 201)
        response = self.app.get('/get/person/1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['name'], 'Test')
        response = self.app.patch('/patch/person/1',
                                  data=dumps(dict(name='Foo')))
        self.assertEqual(response.status_code, 200)
        response = self.app.get('/get/person/1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['name'], 'Foo')
        response = self.app.delete('/delete/person/1')
        self.assertEqual(response.status_code, 204)
        response = self.app.get('/get/person/1')
        self.assertEqual(response.status_code, 404)

    def test_max_results_per_page(self):
        """Test for specifying the ``max_results_per_page`` keyword argument.

        """
        self.manager.create_api(self.Person, methods=['GET', 'POST'],
                                max_results_per_page=15)
        for n in range(100):
            response = self.app.post('/api/person', data=dumps({}))
            self.assertEqual(201, response.status_code)
        response = self.app.get('/api/person?results_per_page=20')
        self.assertEqual(200, response.status_code)
        data = loads(response.data)
        self.assertEqual(15, len(data['objects']))

    def test_expose_relations(self):
        """Tests that relations are exposed at a URL which is a child of the
        instance URL.

        """
        date = datetime.date(1999, 12, 31)
        person = self.Person(name='Test', age=10, other=20, birth_date=date)
        computer = self.Computer(name='foo', vendor='bar', buy_date=date)
        self.session.add(person)
        person.computers.append(computer)
        self.session.commit()

        self.manager.create_api(self.Person)
        response = self.app.get('/api/person/1/computers')
        self.assertEqual(200, response.status_code)
        data = loads(response.data)
        self.assertIn('objects', data)
        self.assertEqual(1, len(data['objects']))
        self.assertEqual('foo', data['objects'][0]['name'])

    def test_expose_lazy_relations(self):
        """Tests that lazy relations are exposed at a URL which is a child of
        the instance URL.

        """
        person = self.LazyPerson(name='Test')
        computer = self.LazyComputer(name='foo')
        self.session.add(person)
        person.computers.append(computer)
        self.session.commit()

        self.manager.create_api(self.LazyPerson)
        response = self.app.get('/api/lazyperson/1/computers')
        self.assertEqual(200, response.status_code)
        data = loads(response.data)
        self.assertIn('objects', data)
        self.assertEqual(1, len(data['objects']))
        self.assertEqual('foo', data['objects'][0]['name'])


class FSATest(FlaskTestBase):
    """Tests which use models defined using Flask-SQLAlchemy instead of pure
    SQLAlchemy.

    """

    def setUp(self):
        """Creates the Flask application, the APIManager, the database, and the
        Flask-SQLAlchemy models.

        """
        super(FSATest, self).setUp()

        # initialize SQLAlchemy and Flask-Restless
        self.db = SQLAlchemy(self.flaskapp)
        self.manager = APIManager(self.flaskapp, flask_sqlalchemy_db=self.db)

        # for the sake of brevity...
        db = self.db

        # declare the models
        class Computer(db.Model):
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.Unicode, unique=True)
            vendor = db.Column(db.Unicode)
            buy_date = db.Column(db.DateTime)
            owner_id = db.Column(db.Integer, db.ForeignKey('person.id'))
            owner = db.relationship('Person',
                                    backref=db.backref('computers',
                                                       lazy='dynamic'))

        class Person(db.Model):
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.Unicode, unique=True)
            age = db.Column(db.Float)
            other = db.Column(db.Float)
            birth_date = db.Column(db.Date)

        self.Person = Person
        self.Computer = Computer

        # create all the tables required for the models
        self.db.create_all()

    def tearDown(self):
        """Drops all tables from the temporary database."""
        self.db.drop_all()

    def test_flask_sqlalchemy(self):
        """Tests that :class:`flask.ext.restless.APIManager` correctly exposes
        models defined using Flask-SQLAlchemy.

        """
        # create three different APIs for the same model
        self.manager.create_api(self.Person, methods=['GET', 'POST'])
        self.manager.create_api(self.Person, methods=['PATCH'],
                                url_prefix='/api2')
        self.manager.create_api(self.Person, methods=['GET'],
                                url_prefix='/readonly')

        # test that specified endpoints exist
        response = self.app.post('/api/person', data=dumps(dict(name='foo')))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(loads(response.data)['id'], 1)
        response = self.app.get('/api/person')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(loads(response.data)['objects']), 1)
        self.assertEqual(loads(response.data)['objects'][0]['id'], 1)
        response = self.app.patch('/api2/person/1',
                                  data=dumps(dict(name='bar')))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(loads(response.data)['id'], 1)
        self.assertEqual(loads(response.data)['name'], 'bar')

        # test that the model is the same as before
        response = self.app.get('/readonly/person')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(loads(response.data)['objects']), 1)
        self.assertEqual(loads(response.data)['objects'][0]['id'], 1)
        self.assertEqual(loads(response.data)['objects'][0]['name'], 'bar')


# skipUnless should be used as a decorator, but Python 2.5 doesn't have
# decorators.
FSATest = skipUnless(has_flask_sqlalchemy,
                     'Flask-SQLAlchemy not found.')(FSATest)


def load_tests(loader, standard_tests, pattern):
    """Returns the test suite for this module."""
    suite = TestSuite()
    suite.addTest(loader.loadTestsFromTestCase(APIManagerTest))
    suite.addTest(loader.loadTestsFromTestCase(FSATest))
    return suite
