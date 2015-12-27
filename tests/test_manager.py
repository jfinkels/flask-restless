# test_manager.py - unit tests for the manager module
#
# Copyright 2011 Lincoln de Sousa <lincoln@comum.org>.
# Copyright 2012, 2013, 2014, 2015 Jeffrey Finkelstein
#           <jeffrey.finkelstein@gmail.com> and contributors.
#
# This file is part of Flask-Restless.
#
# Flask-Restless is distributed under both the GNU Affero General Public
# License version 3 and under the 3-clause BSD license. For more
# information, see LICENSE.AGPL and LICENSE.BSD.
"""Unit tests for the :mod:`flask_restless.manager` module."""
from flask import Flask
try:
    from flask.ext.sqlalchemy import SQLAlchemy
except ImportError:
    has_flask_sqlalchemy = False
else:
    has_flask_sqlalchemy = True
from nose.tools import raises
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Unicode
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship

from flask.ext.restless import APIManager
from flask.ext.restless import collection_name
from flask.ext.restless import IllegalArgumentError
from flask.ext.restless import model_for
from flask.ext.restless import url_for

from .helpers import DatabaseTestBase
from .helpers import ManagerTestBase
from .helpers import FlaskTestBase
from .helpers import force_json_contenttype
from .helpers import skip
from .helpers import skip_unless
from .helpers import unregister_fsa_session_signals


class TestLocalAPIManager(DatabaseTestBase):
    """Provides tests for :class:`flask.ext.restless.APIManager` when the tests
    require that the instance of :class:`flask.ext.restless.APIManager` has not
    yet been instantiated.

    """

    def setUp(self):
        super(TestLocalAPIManager, self).setUp()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)

        self.Person = Person
        self.Article = Article
        self.Base.metadata.create_all()

    def test_init_app(self):
        """Tests for initializing the Flask application after instantiating the
        :class:`flask.ext.restless.APIManager` object.

        """
        manager = APIManager()
        manager.init_app(self.flaskapp, session=self.session)
        manager.create_api(self.Person, app=self.flaskapp)
        response = self.app.get('/api/person')
        assert response.status_code == 200

    def test_init_app_split_initialization(self):
        manager = APIManager(session=self.session)
        manager.init_app(self.flaskapp)
        manager.create_api(self.Person, app=self.flaskapp)
        response = self.app.get('/api/person')
        assert response.status_code == 200

    def test_init_multiple(self):
        manager = APIManager(session=self.session)
        flaskapp1 = self.flaskapp
        flaskapp2 = Flask(__name__)
        testclient1 = self.app
        testclient2 = flaskapp2.test_client()
        force_json_contenttype(testclient2)
        manager.init_app(flaskapp1)
        manager.init_app(flaskapp2)
        manager.create_api(self.Person, app=flaskapp1)
        manager.create_api(self.Article, app=flaskapp2)
        response = testclient1.get('/api/person')
        assert response.status_code == 200
        response = testclient1.get('/api/article')
        assert response.status_code == 404
        response = testclient2.get('/api/person')
        assert response.status_code == 404
        response = testclient2.get('/api/article')
        assert response.status_code == 200

    def test_creation_api_without_app_dependency(self):
        """Tests that api can be added before app will be passed to manager."""
        manager = APIManager()
        manager.create_api(self.Person)
        manager.init_app(self.flaskapp, self.session)
        response = self.app.get('/api/person')
        assert response.status_code == 200

    def test_multiple_app_delayed_init(self):
        manager = APIManager(session=self.session)

        # Create the Flask applications and the test clients.
        flaskapp1 = self.flaskapp
        flaskapp2 = Flask(__name__)
        testclient1 = self.app
        testclient2 = flaskapp2.test_client()
        force_json_contenttype(testclient2)

        # First create the API, then initialize the Flask applications after.
        manager.create_api(self.Person, app=flaskapp1)
        manager.create_api(self.Article, app=flaskapp2)
        manager.init_app(flaskapp1)
        manager.init_app(flaskapp2)

        # Tests that only the first Flask application gets requests for
        # /api/person and only the second gets requests for /api/article.
        response = testclient1.get('/api/person')
        assert response.status_code == 200
        response = testclient1.get('/api/article')
        assert response.status_code == 404
        response = testclient2.get('/api/person')
        assert response.status_code == 404
        response = testclient2.get('/api/article')
        assert response.status_code == 200

    def test_universal_preprocessor(self):
        """Tests universal preprocessor and postprocessor applied to all
        methods created with the API manager.

        """
        class Counter:
            """An object that increments a counter on each invocation."""

            def __init__(self):
                self._counter = 0

            def __call__(self, *args, **kw):
                self._counter += 1

            def __eq__(self, other):
                if isinstance(other, Counter):
                    return self._counter == other._counter
                if isinstance(other, int):
                    return self._counter == other
                return False

        increment1 = Counter()
        increment2 = Counter()

        preprocessors = dict(GET_COLLECTION=[increment1])
        postprocessors = dict(GET_COLLECTION=[increment2])
        manager = APIManager(self.flaskapp, session=self.session,
                             preprocessors=preprocessors,
                             postprocessors=postprocessors)
        manager.create_api(self.Person)
        manager.create_api(self.Article)
        # After each request, regardless of API endpoint, both counters should
        # be incremented.
        self.app.get('/api/person')
        self.app.get('/api/article')
        self.app.get('/api/person')
        assert increment1 == increment2 == 3


class TestAPIManager(ManagerTestBase):
    """Unit tests for the :class:`flask_restless.manager.APIManager` class."""

    def setUp(self):
        super(TestAPIManager, self).setUp()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            title = Column(Unicode)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship(Person, backref=backref('articles'))

        class Tag(self.Base):
            __tablename__ = 'tag'
            name = Column(Unicode, primary_key=True)

        self.Article = Article
        self.Person = Person
        self.Tag = Tag
        self.Base.metadata.create_all()

    # HACK If we don't include this, there seems to be an issue with the
    # globally known APIManager objects not being cleared after every test.
    def tearDown(self):
        """Clear the :class:`flask.ext.restless.APIManager` objects known by
        the global functions :data:`model_for`, :data:`url_for`, and
        :data:`collection_name`.

        """
        super(TestAPIManager, self).tearDown()
        model_for.created_managers.clear()
        url_for.created_managers.clear()
        collection_name.created_managers.clear()

    def test_url_for(self):
        """Tests the global :func:`flask.ext.restless.url_for` function."""
        self.manager.create_api(self.Person, collection_name='people')
        self.manager.create_api(self.Article, collection_name='articles')
        with self.flaskapp.test_request_context():
            url1 = url_for(self.Person)
            url2 = url_for(self.Person, resource_id=1)
            url3 = url_for(self.Person, resource_id=1,
                           relation_name='articles')
            url4 = url_for(self.Person, resource_id=1,
                           relation_name='articles', related_resource_id=2)
            assert url1.endswith('/api/people')
            assert url2.endswith('/api/people/1')
            assert url3.endswith('/api/people/1/articles')
            assert url4.endswith('/api/people/1/articles/2')

    @raises(ValueError)
    def test_url_for_nonexistent(self):
        """Tests that attempting to get the URL for an unknown model yields an
        error.

        """
        url_for(self.Person)

    def test_collection_name(self):
        """Tests the global :func:`flask.ext.restless.collection_name`
        function.

        """
        self.manager.create_api(self.Person, collection_name='people')
        assert collection_name(self.Person) == 'people'

    @raises(ValueError)
    def test_collection_name_nonexistent(self):
        """Tests that attempting to get the collection name for an unknown
        model yields an error.

        """
        collection_name(self.Person)

    def test_model_for(self):
        """Tests the global :func:`flask.ext.restless.model_for` function."""
        self.manager.create_api(self.Person, collection_name='people')
        assert model_for('people') is self.Person

    @raises(ValueError)
    def test_model_for_nonexistent(self):
        """Tests that attempting to get the model for a nonexistent collection
        yields an error.

        """
        model_for('people')

    def test_model_for_collection_name(self):
        """Tests that :func:`flask.ext.restless.model_for` is the inverse of
        :func:`flask.ext.restless.collection_name`.

        """
        self.manager.create_api(self.Person, collection_name='people')
        assert collection_name(model_for('people')) == 'people'
        assert model_for(collection_name(self.Person)) is self.Person

    def test_disallowed_methods(self):
        """Tests that disallowed methods respond with :http:status:`405`."""
        self.manager.create_api(self.Person, methods=[])
        for method in 'get', 'post', 'patch', 'delete':
            func = getattr(self.app, method)
            response = func('/api/person')
            assert response.status_code == 405

    @raises(IllegalArgumentError)
    def test_missing_id(self):
        """Tests that calling :meth:`APIManager.create_api` on a model without
        an ``id`` column raises an exception.

        """
        self.manager.create_api(self.Tag)

    @raises(IllegalArgumentError)
    def test_empty_collection_name(self):
        """Tests that calling :meth:`APIManager.create_api` with an empty
        collection name raises an exception.

        """
        self.manager.create_api(self.Person, collection_name='')

    def test_disallow_functions(self):
        """Tests that if the ``allow_functions`` keyword argument is ``False``,
        no endpoint will be made available at :http:get:`/api/eval/:type`.

        """
        self.manager.create_api(self.Person, allow_functions=False)
        response = self.app.get('/api/eval/person')
        assert response.status_code == 404

    @skip('This test does not make sense anymore with JSON API')
    @raises(IllegalArgumentError)
    def test_exclude_primary_key_column(self):
        """Tests that trying to create a writable API while excluding the
        primary key field raises an error.

        """
        self.manager.create_api(self.Person, exclude=['id'], methods=['POST'])


@skip_unless(has_flask_sqlalchemy, 'Flask-SQLAlchemy not found.')
class TestFSA(FlaskTestBase):
    """Tests which use models defined using Flask-SQLAlchemy instead of pure
    SQLAlchemy.

    """

    def setUp(self):
        """Creates the Flask application, the APIManager, the database, and the
        Flask-SQLAlchemy models.

        """
        super(TestFSA, self).setUp()
        self.db = SQLAlchemy(self.flaskapp)

        class Person(self.db.Model):
            id = self.db.Column(self.db.Integer, primary_key=True)

        self.Person = Person
        self.db.create_all()

    def tearDown(self):
        """Drops all tables from the temporary database."""
        self.db.drop_all()
        unregister_fsa_session_signals()

    def test_init_app(self):
        manager = APIManager()
        manager.init_app(self.flaskapp, flask_sqlalchemy_db=self.db)
        manager.create_api(self.Person, app=self.flaskapp)
        response = self.app.get('/api/person')
        assert response.status_code == 200

    def test_init_app_split_initialization(self):
        manager = APIManager(flask_sqlalchemy_db=self.db)
        manager.init_app(self.flaskapp)
        manager.create_api(self.Person, app=self.flaskapp)
        response = self.app.get('/api/person')
        assert response.status_code == 200
