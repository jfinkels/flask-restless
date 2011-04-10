# -*- coding: utf-8; Mode: Python -*-
#
# Copyright (C) 2011  Lincoln de Sousa <lincoln@comum.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import unittest
import os
from tempfile import mkstemp
from datetime import date, datetime

from elixir import create_all, session, drop_all
from sqlalchemy import create_engine

from testapp import models

class ModelTestCase(unittest.TestCase):
    """Tests focused on `restful.model` module
    """

    def setUp(self):
        self.db_fd, self.db_file = mkstemp()
        models.setup(create_engine('sqlite:///%s' % self.db_file))
        create_all()
        session.commit()

        self.model = models.Person

    def tearDown(self):
        """Destroying the sqlite database file
        """
        drop_all()
        session.commit()
        os.close(self.db_fd)
        os.unlink(self.db_file)

    def test_column_introspection(self):
        """Makes sure that the column list works properly
        """
        columns = self.model.get_columns()
        assert sorted(columns.keys()) == sorted([
                'age', 'birth_date', 'computers', 'id', 'name'])
        relations = models.Person.get_relations()
        assert relations == ['computers']

    def test_instance_introspection(self):
        """Testing the instance introspection
        """
        me = self.model()
        me.name = u'Lincoln'
        me.age = 24
        me.birth_date = date(1986, 9, 15)
        session.commit()

        me_dict = me.to_dict()
        assert sorted(me_dict.keys()) == sorted([
                'birth_date', 'age', 'id', 'name'])
        assert me_dict['name'] == u'Lincoln'
        assert me_dict['age'] == 24

    def test_deep_instrospection(self):
        """Testing the introspection of related fields
        """
        someone = self.model()
        someone.name = u'John'
        someone.age = 25
        computer1 = models.Computer()
        computer1.name = u'lixeiro'
        computer1.vendor = u'Lemote'
        computer1.owner = someone
        computer1.buy_date = datetime.now()
        session.commit()

        relations = models.Person.get_relations()
        deep = dict(zip(relations, [{}]*len(relations)))

        computers = someone.to_dict(deep)['computers']
        assert len(computers) == 1
        assert computers[0]['name'] == u'lixeiro'
        assert computers[0]['vendor'] == u'Lemote'

def suite():
    test_suite = unittest.TestSuite()
    test_suite.addTest(unittest.makeSuite(ModelTestCase))
    return test_suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
