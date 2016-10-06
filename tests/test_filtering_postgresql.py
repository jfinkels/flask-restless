# test_filtering_postgresql.py - filtering tests for PostgreSQL
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
"""Unit tests for PostgreSQL-specific filtering operators."""

# The psycopg2cffi import is required for testing on PyPy. CPython can
# use psycopg2, but PyPy can only use psycopg2cffi.
try:
    import psycopg2  # noqa
except ImportError:
    from psycopg2cffi import compat
    compat.register()
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.exc import OperationalError

from .helpers import loads
from .test_filtering import SearchTestBase


class TestNetworkOperators(SearchTestBase):
    """Unit tests for the network address operators in PostgreSQL.

    For more information, see `Network Address Functions and Operators`_
    in the PostgreSQL documentation.

    .. _Network Address Functions and Operators:
       http://www.postgresql.org/docs/current/interactive/functions-net.html

    """

    def setUp(self):
        super(TestNetworkOperators, self).setUp()

        class Network(self.Base):
            __tablename__ = 'network'
            id = Column(Integer, primary_key=True)
            address = Column(INET)

        self.Network = Network
        # This try/except skips the tests if we are unable to create the
        # tables in the PostgreSQL database.
        try:
            self.Base.metadata.create_all()
        except OperationalError:
            self.skipTest('error creating tables in PostgreSQL database')
        self.manager.create_api(Network)

    def database_uri(self):
        """Return a PostgreSQL connection URI.

        Since this test case is for operators specific to PostgreSQL, we
        return a PostgreSQL connection URI. The particular
        Python-to-PostgreSQL adapter we are using is currently
        `Psycopg`_.

        .. _Psycopg: http://initd.org/psycopg/

        """
        return 'postgresql+psycopg2://postgres@localhost:5432/testdb'

    def test_is_not_equal(self):
        """Test for the ``<>`` ("is not equal") operator.

        For example:

        .. sourcecode:: postgresql

           inet '192.168.1.5' <> inet '192.168.1.4'

        """
        network1 = self.Network(id=1, address='192.168.1.5')
        network2 = self.Network(id=2, address='192.168.1.4')
        self.session.add_all([network1, network2])
        self.session.commit()
        filters = [dict(name='address', op='<>', val='192.168.1.4')]
        response = self.search('/api/network', filters)
        document = loads(response.data)
        networks = document['data']
        assert ['1'] == sorted(network['id'] for network in networks)

    def test_is_contained_by(self):
        """Test for the ``<<`` ("is contained by") operator.

        For example:

        .. sourcecode:: postgresql

           inet '192.168.1.5' << inet '192.168.1/24'

        """
        network1 = self.Network(id=1, address='192.168.1.5')
        network2 = self.Network(id=2, address='192.168.2.1')
        self.session.add_all([network1, network2])
        self.session.commit()
        filters = [dict(name='address', op='<<', val='192.168.1/24')]
        response = self.search('/api/network', filters)
        document = loads(response.data)
        networks = document['data']
        assert ['1'] == sorted(network['id'] for network in networks)

    def test_is_contained_by_or_equals(self):
        """Test for the ``<<=`` ("is contained by or equals") operator.

        For example:

        .. sourcecode:: postgresql

           inet '192.168.1/24' <<= inet '192.168.1/24'

        """
        network1 = self.Network(id=1, address='192.168.1/24')
        network2 = self.Network(id=2, address='192.168.1.5')
        network3 = self.Network(id=3, address='192.168.2.1')
        self.session.add_all([network1, network2, network3])
        self.session.commit()
        filters = [dict(name='address', op='<<=', val='192.168.1/24')]
        response = self.search('/api/network', filters)
        document = loads(response.data)
        networks = document['data']
        assert ['1', '2'] == sorted(network['id'] for network in networks)

    def test_contains(self):
        """Test for the ``>>`` ("contains") operator.

        For example:

        .. sourcecode:: postgresql

           inet '192.168.1/24' >> inet '192.168.1.5'

        """
        network1 = self.Network(id=1, address='192.168.1/24')
        network2 = self.Network(id=2, address='192.168.2/24')
        self.session.add_all([network1, network2])
        self.session.commit()
        filters = [dict(name='address', op='>>', val='192.168.1.5')]
        response = self.search('/api/network', filters)
        document = loads(response.data)
        networks = document['data']
        assert ['1'] == sorted(network['id'] for network in networks)

    def test_contains_or_equals(self):
        """Test for the ``>>=`` ("contains or equals") operator.

        For example:

        .. sourcecode:: postgresql

           inet '192.168.1/24' >>= inet '192.168.1/24'

        """
        network1 = self.Network(id=1, address='192.168.1/24')
        network2 = self.Network(id=2, address='192.168/16')
        network3 = self.Network(id=3, address='192.168.2/24')
        self.session.add_all([network1, network2, network3])
        self.session.commit()
        filters = [dict(name='address', op='>>=', val='192.168.1/24')]
        response = self.search('/api/network', filters)
        document = loads(response.data)
        networks = document['data']
        assert ['1', '2'] == sorted(network['id'] for network in networks)

    def test_contains_or_is_contained_by(self):
        """Test for the ``&&`` ("contains or is contained by") operator.

        .. warning::

           This operation is only available in PostgreSQL 9.4 or later.

        For example:

        .. sourcecode:: postgresql

           inet '192.168.1/24' && inet '192.168.1.80/28'

        """
        # network1 contains the queried subnet
        network1 = self.Network(id=1, address='192.168.1/24')
        # network2 is contained by the queried subnet
        network2 = self.Network(id=2, address='192.168.1.81/28')
        # network3 is neither
        network3 = self.Network(id=3, address='192.168.2.1')
        self.session.add_all([network1, network2, network3])
        self.session.commit()
        filters = [dict(name='address', op='&&', val='192.168.1.80/28')]
        response = self.search('/api/network', filters)
        document = loads(response.data)
        networks = document['data']
        assert ['1', '2'] == sorted(network['id'] for network in networks)
