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
import sys
import os
from tempfile import mkstemp
from datetime import date, datetime

import flask
from simplejson import dumps, loads
from elixir import create_all, session, drop_all
from sqlalchemy import create_engine

sys.path.append('..')
import api
from testapp import models, validators

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

class RestfulTestCase(unittest.TestCase):
    """Test case class for the restful api itself
    """

    def setUp(self):
        """Sets up the database and the flask app
        """
        self.db_fd, self.db_file = mkstemp()
        models.setup(create_engine('sqlite:///%s' % self.db_file))
        create_all()

        app = flask.Flask(__name__)
        app.register_module(api.api, url_prefix="/api")
        api.setup(models, validators)
        self.app = app.test_client()

    def tearDown(self):
        """Destroying the sqlite database file
        """
        drop_all()
        session.commit()
        os.close(self.db_fd)
        os.unlink(self.db_file)

    def test_setup(self):
        """Just to make sure that everything worked while setting up api
        """
        assert api.CONFIG['models'] is models
        assert api.CONFIG['validators'] is validators

    def test_new_person(self):
        """Tests the creation of new persons
        """
        response = self.app.post(
            '/api/Person/',
            data=dumps({'name': 'Lincoln', 'age': 23}))
        assert response.status_code == 200
        assert loads(response.data)['status'] == 'ok'

        response = self.app.get('/api/Person/1/')
        assert response.status_code == 200

        deep = {'computers':[]}
        inst = models.Person.get_by(id=1).to_dict(deep)
        assert response.data == dumps(inst)

    def test_remove_person(self):
        """Adds a new person and tests its removal.
        """
        # Creating the person who's gonna be deleted
        response = self.app.post(
            '/api/Person/',
            data=dumps({'name': 'Lincoln', 'age': 23}))
        assert response.status_code == 200
        assert loads(response.data)['status'] == 'ok'

        # Making sure it has been created
        deep = {'computers':[]}
        inst = models.Person.get_by(id=1).to_dict(deep)
        response = self.app.get('/api/Person/1/')
        assert response.data == dumps(inst)

        # Deleting it
        response = self.app.delete('/api/Person/1/')
        assert loads(response.data)['status'] == 'ok'

        # Making sure it has been deleted
        assert models.Person.get_by(id=1) is None

    def test_remove_absent_person(self):
        """Tests the removal of someone that is not in the database

        This should give us an ok, since the DELETE method is an
        idempotent method.
        """
        response = self.app.delete('/api/Person/1/')
        assert loads(response.data)['status'] == 'ok'

    def test_update(self):
        """Tests the update (PUT) operation against a collection
        """
        # Creating some people
        self.app.post(
            '/api/Person/',
            data=dumps({'name': 'Lincoln', 'age': 23}))
        self.app.post(
            '/api/Person/',
            data=dumps({'name': 'Lucy', 'age': 25}))
        self.app.post(
            '/api/Person/',
            data=dumps({'name': 'Mary', 'age': 23}))

        # Changing the birth date field of the entire collection
        day, month, year = 15, 9, 1986
        birth_date = date(year, month, day).strftime('%d/%m/%Y') # iso8601
        form = {'birth_date': birth_date}
        self.app.put('/api/Person/', data=dumps({'form': form}))

        # Finally, testing if the change was made
        response = self.app.get('/api/Person/')
        loaded = loads(response.data)
        for i in loaded:
            assert i['birth_date'] == ('%s-%s-%s' % (
                    year, str(month).zfill(2), str(day).zfill(2)))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ModelTestCase))
    suite.addTest(unittest.makeSuite(RestfulTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
