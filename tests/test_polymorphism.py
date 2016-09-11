# test_polymorphism.py - unit tests for polymorphic models
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
"""Unit tests for interacting with polymorphic models.

The tests in this module use models defined using `single table
inheritance`_ and `joined table inheritance`_.

.. _single table inheritance:
   http://docs.sqlalchemy.org/en/latest/orm/inheritance.html#single-table-inheritance
.. _joined table inheritance:
   http://docs.sqlalchemy.org/en/latest/orm/inheritance.html#joined-table-inheritance

"""
from operator import itemgetter

from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Unicode

from flask_restless import DefaultSerializer

from .helpers import check_sole_error
from .helpers import dumps
from .helpers import loads
from .helpers import ManagerTestBase


class SingleTableInheritanceSetupMixin(object):
    """Mixin for setting up single table inheritance in test cases."""

    def setUp(self):
        """Creates polymorphic models using single table inheritance."""
        super(SingleTableInheritanceSetupMixin, self).setUp()

        class Employee(self.Base):
            __tablename__ = 'employee'
            id = Column(Integer, primary_key=True)
            type = Column(Enum('employee', 'manager'), nullable=False)
            name = Column(Unicode)
            __mapper_args__ = {
                'polymorphic_on': type,
                'polymorphic_identity': 'employee'
            }

        # This model inherits directly from the `Employee` class, so
        # there is only one table being used.
        class Manager(Employee):
            __mapper_args__ = {
                'polymorphic_identity': 'manager'
            }

        self.Employee = Employee
        self.Manager = Manager
        self.Base.metadata.create_all()


class JoinedTableInheritanceSetupMixin(object):
    """Mixin for setting up joined table inheritance in test cases."""

    def setUp(self):
        """Creates polymorphic models using joined table inheritance."""
        super(JoinedTableInheritanceSetupMixin, self).setUp()

        class Employee(self.Base):
            __tablename__ = 'employee'
            id = Column(Integer, primary_key=True)
            type = Column(Enum('employee', 'manager'), nullable=False)
            name = Column(Unicode)
            __mapper_args__ = {
                'polymorphic_on': type,
                'polymorphic_identity': 'employee'
            }

        # This model inherits directly from the `Employee` class, so
        # there is only one table being used.
        class Manager(Employee):
            __tablename__ = 'manager'
            id = Column(Integer, ForeignKey('employee.id'), primary_key=True)
            __mapper_args__ = {
                'polymorphic_identity': 'manager'
            }

        self.Employee = Employee
        self.Manager = Manager
        self.Base.metadata.create_all()


class FetchingTestMixinBase(object):
    """Base class for test cases for fetching resources."""

    def setUp(self):
        super(FetchingTestMixinBase, self).setUp()

        # Create the APIs for the Employee and Manager.
        self.apimanager = self.manager
        self.apimanager.create_api(self.Employee)
        self.apimanager.create_api(self.Manager)

        # Populate the database. Store a reference to the actual
        # instances so that test methods in subclasses can access them.
        self.employee = self.Employee(id=1)
        self.manager = self.Manager(id=2)
        self.session.add_all([self.employee, self.manager])
        self.session.commit()


class FetchCollectionTestMixin(FetchingTestMixinBase):
    """Tests for fetching a collection of resources defined using single
    table inheritance.

    """

    def test_subclass(self):
        """Tests that fetching a collection at the subclass endpoint
        yields only instance of the subclass.

        """
        response = self.app.get('/api/manager')
        assert response.status_code == 200
        document = loads(response.data)
        managers = document['data']
        assert len(managers) == 1
        manager = managers[0]
        assert 'manager' == manager['type']
        assert '2' == manager['id']

    def test_superclass(self):
        """Tests that fetching a collection at the superclass endpoint
        yields instances of both the subclass and the superclass.

        """
        response = self.app.get('/api/employee')
        assert response.status_code == 200
        document = loads(response.data)
        employees = document['data']
        employees = sorted(employees, key=itemgetter('id'))
        employee_types = list(map(itemgetter('type'), employees))
        employee_ids = list(map(itemgetter('id'), employees))
        assert ['employee', 'manager'] == employee_types
        assert ['1', '2'] == employee_ids

    def test_heterogeneous_serialization(self):
        """Tests that each object is serialized using the serializer
        specified in :meth:`APIManager.create_api`.

        """

        class EmployeeSerializer(DefaultSerializer):

            def serialize(self, instance, *args, **kw):
                superserialize = super(EmployeeSerializer, self).serialize
                result = superserialize(instance, *args, **kw)
                result['data']['attributes']['foo'] = 'bar'
                return result

        class ManagerSerializer(DefaultSerializer):

            def serialize(self, instance, *args, **kw):
                superserialize = super(ManagerSerializer, self).serialize
                result = superserialize(instance, *args, **kw)
                result['data']['attributes']['baz'] = 'xyzzy'
                return result

        self.apimanager.create_api(self.Employee, url_prefix='/api2',
                                   serializer_class=EmployeeSerializer)
        self.apimanager.create_api(self.Manager, url_prefix='/api2',
                                   serializer_class=ManagerSerializer)

        response = self.app.get('/api/employee')
        assert response.status_code == 200
        document = loads(response.data)
        employees = document['data']
        assert len(employees) == 2
        employees = sorted(employees, key=itemgetter('id'))
        assert employees[0]['attributes']['foo'] == 'bar'
        assert employees[1]['attributes']['baz'] == 'xyzzy'


class FetchResourceTestMixin(FetchingTestMixinBase):
    """Tests for fetching a single resource defined using single table
    inheritance.

    """

    def test_subclass_at_subclass(self):
        """Tests for fetching a resource of the subclass type at the URL
        for the subclass.

        """
        response = self.app.get('/api/employee/1')
        assert response.status_code == 200
        document = loads(response.data)
        resource = document['data']
        assert resource['type'] == 'employee'
        assert resource['id'] == str(self.employee.id)

    def superclass_at_superclass(self):
        """Tests for fetching a resource of the superclass type at the
        URL for the superclass.

        """
        response = self.app.get('/api/manager/2')
        assert response.status_code == 200
        document = loads(response.data)
        resource = document['data']
        assert resource['type'] == 'manager'
        assert resource['id'] == str(self.manager.id)

    def test_superclass_at_subclass(self):
        """Tests that attempting to fetch a resource of the superclass
        type at the subclass endpoint causes an exception.

        """
        response = self.app.get('/api/manager/1')
        assert response.status_code == 404

    def test_subclass_at_superclass(self):
        """Tests that attempting to fetch a resource of the subclass
        type at the superclass endpoint causes an exception.

        """
        response = self.app.get('/api/employee/2')
        assert response.status_code == 404


class CreatingTestMixin(object):
    """Tests for APIs created for polymorphic models defined using
    single table inheritance.

    """

    def setUp(self):
        super(CreatingTestMixin, self).setUp()
        self.manager.create_api(self.Employee, methods=['POST'])
        self.manager.create_api(self.Manager, methods=['POST'])

    def test_subclass_at_subclass(self):
        """Tests for creating a resource of the subclass type at the URL
        for the subclass.

        """
        data = {
            'data': {
                'type': 'manager'
            }
        }
        response = self.app.post('/api/manager', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        manager = document['data']
        manager_in_db = self.session.query(self.Manager).first()
        assert manager['id'] == str(manager_in_db.id)
        assert manager['type'] == 'manager'

    def test_superclass_at_superclass(self):
        """Tests for creating a resource of the superclass type at the
        URL for the superclass.

        """
        data = {
            'data': {
                'type': 'employee'
            }
        }
        response = self.app.post('/api/employee', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        employee = document['data']
        employee_in_db = self.session.query(self.Employee).first()
        assert employee['id'] == str(employee_in_db.id)
        assert employee['type'] == 'employee'

    def test_subclass_at_superclass(self):
        """Tests that attempting to create a resource of the subclass
        type at the URL for the superclass causes an error.

        """
        data = {
            'data': {
                'type': 'manager'
            }
        }
        response = self.app.post('/api/employee', data=dumps(data))
        check_sole_error(response, 409, ['Failed', 'deserialize', 'expected',
                                         'type', 'employee', 'manager'])

    def test_superclass_at_subclass(self):
        """Tests that attempting to create a resource of the superclass
        type at the URL for the subclass causes an error.

        """
        data = {
            'data': {
                'type': 'employee'
            }
        }
        response = self.app.post('/api/manager', data=dumps(data))
        check_sole_error(response, 409, ['Failed', 'deserialize', 'expected',
                                         'type', 'manager', 'employee'])


class DeletingTestMixin(object):
    """Tests for deleting resources."""

    def setUp(self):
        super(DeletingTestMixin, self).setUp()

        # Create the APIs for the Employee and Manager.
        self.manager.create_api(self.Employee, methods=['DELETE'])
        self.manager.create_api(self.Manager, methods=['DELETE'])

        # Populate the database. Store a reference to the actual
        # instances so that test methods in subclasses can access them.
        self.employee = self.Employee(id=1)
        self.manager = self.Manager(id=2)
        self.all_employees = [self.employee, self.manager]
        self.session.add_all(self.all_employees)
        self.session.commit()

    def test_subclass_at_subclass(self):
        """Tests for deleting a resource of the subclass type at the URL
        for the subclass.

        """
        response = self.app.delete('/api/manager/2')
        assert response.status_code == 204
        assert self.session.query(self.Manager).count() == 0
        assert self.session.query(self.Employee).all() == [self.employee]

    def test_superclass_at_superclass(self):
        """Tests for deleting a resource of the superclass type at the
        URL for the superclass.

        """
        response = self.app.delete('/api/employee/1')
        assert response.status_code == 204
        assert self.session.query(self.Manager).all() == [self.manager]
        assert self.session.query(self.Employee).all() == [self.manager]

    def test_subclass_at_superclass(self):
        """Tests that attempting to delete a resource of the subclass
        type at the URL for the superclass causes an error.

        """
        response = self.app.delete('/api/employee/2')
        check_sole_error(response, 404, ['No resource found', 'type',
                                         'employee', 'ID', '2'])
        assert self.session.query(self.Manager).all() == [self.manager]
        assert self.session.query(self.Employee).all() == self.all_employees

    def test_superclass_at_subclass(self):
        """Tests that attempting to delete a resource of the superclass
        type at the URL for the subclass causes an error.

        """
        response = self.app.delete('/api/manager/1')
        check_sole_error(response, 404, ['No resource found', 'type',
                                         'manager', 'ID', '1'])
        assert self.session.query(self.Manager).all() == [self.manager]
        assert self.session.query(self.Employee).all() == self.all_employees


class UpdatingTestMixin(object):
    """Tests for updating resources."""

    def setUp(self):
        super(UpdatingTestMixin, self).setUp()

        # Create the APIs for the Employee and Manager.
        self.manager.create_api(self.Employee, methods=['PATCH'])
        self.manager.create_api(self.Manager, methods=['PATCH'])

        # Populate the database. Store a reference to the actual
        # instances so that test methods in subclasses can access them.
        self.employee = self.Employee(id=1, name=u'foo')
        self.manager = self.Manager(id=2, name=u'foo')
        self.session.add_all([self.employee, self.manager])
        self.session.commit()

    def test_subclass_at_subclass(self):
        """Tests for updating a resource of the subclass type at the URL
        for the subclass.

        """
        data = {
            'data': {
                'type': 'manager',
                'id': '2',
                'attributes': {
                    'name': u'bar'
                }
            }
        }
        response = self.app.patch('/api/manager/2', data=dumps(data))
        assert response.status_code == 204
        assert self.manager.name == u'bar'

    def test_superclass_at_superclass(self):
        """Tests for updating a resource of the superclass type at the
        URL for the superclass.

        """
        data = {
            'data': {
                'type': 'employee',
                'id': '1',
                'attributes': {
                    'name': u'bar'
                }
            }
        }
        response = self.app.patch('/api/employee/1', data=dumps(data))
        assert response.status_code == 204
        assert self.employee.name == u'bar'

    def test_subclass_at_superclass(self):
        """Tests that attempting to update a resource of the subclass
        type at the URL for the superclass causes an error.

        """
        # In this test, the JSON document has the correct type and ID,
        # but the URL has the wrong type. Even though "manager" is a
        # subtype of "employee" Flask-Restless doesn't allow a mismatch
        # of types when updating.
        data = {
            'data': {
                'type': 'manager',
                'id': '2',
                'attributes': {
                    'name': u'bar'
                }
            }
        }
        response = self.app.patch('/api/employee/2', data=dumps(data))
        check_sole_error(response, 404, ['No resource found', 'type',
                                         'employee', 'ID', '2'])

    def test_superclass_at_subclass(self):
        """Tests that attempting to update a resource of the superclass
        type at the URL for the subclass causes an error.

        """
        # In this test, the JSON document has the correct type and ID,
        # but the URL has the wrong type.
        data = {
            'data': {
                'type': 'employee',
                'id': '1',
                'attributes': {
                    'name': u'bar'
                }
            }
        }
        response = self.app.patch('/api/manager/1', data=dumps(data))
        check_sole_error(response, 404, ['No resource found', 'type',
                                         'manager', 'ID', '1'])


class TestFetchCollectionSingle(FetchCollectionTestMixin,
                                SingleTableInheritanceSetupMixin,
                                ManagerTestBase):
    """Tests for fetching a collection of resources defined using single
    table inheritance.

    """


class TestFetchCollectionJoined(FetchCollectionTestMixin,
                                JoinedTableInheritanceSetupMixin,
                                ManagerTestBase):
    """Tests for fetching a collection of resources defined using joined
    table inheritance.

    """


class TestFetchResourceSingle(FetchResourceTestMixin,
                              SingleTableInheritanceSetupMixin,
                              ManagerTestBase):
    """Tests for fetching a single resource defined using single table
    inheritance.

    """


class TestFetchResourceJoined(FetchResourceTestMixin,
                              JoinedTableInheritanceSetupMixin,
                              ManagerTestBase):
    """Tests for fetching a single resource defined using joined table
    inheritance.

    """


class TestCreatingSingle(CreatingTestMixin, SingleTableInheritanceSetupMixin,
                         ManagerTestBase):
    """Tests for creating a resource defined using single table inheritance."""


class TestCreatingJoined(CreatingTestMixin, JoinedTableInheritanceSetupMixin,
                         ManagerTestBase):
    """Tests for creating a resource defined using joined table inheritance."""


class TestDeletingSingle(DeletingTestMixin, SingleTableInheritanceSetupMixin,
                         ManagerTestBase):
    """Tests for deleting a resource defined using single table inheritance."""


class TestDeletingJoined(DeletingTestMixin, JoinedTableInheritanceSetupMixin,
                         ManagerTestBase):
    """Tests for deleting a resource defined using joined table inheritance."""


class TestUpdatingSingle(UpdatingTestMixin, SingleTableInheritanceSetupMixin,
                         ManagerTestBase):
    """Tests for updating a resource defined using single table inheritance."""


class TestUpdatingJoined(UpdatingTestMixin, JoinedTableInheritanceSetupMixin,
                         ManagerTestBase):
    """Tests for updating a resource defined using joined table inheritance."""
