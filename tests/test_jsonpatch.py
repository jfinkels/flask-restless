# test_jsonpatch.py - unit tests for the JSON API JSON Patch extension
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
"""Unit tests for the JSON API JSON Patch extension."""

# class TestJsonPatch(TestSupport):

#     def setup(self):
#         """Creates the database, the :class:`~flask.Flask` object, the
#         :class:`~flask_restless.manager.APIManager` for that application, and
#         creates the ReSTful API endpoints for the :class:`testapp.Person` and
#         :class:`testapp.Computer` models.

#         """
#         # create the database
#         super(TestJsonAPI, self).setup()

#         # setup the URLs for the Person and Computer API
#         self.manager.create_api(self.Person, methods=['PATCH'])
#         self.manager.create_api(self.Computer, methods=['PATCH'])

#     def test_json_patch_header(self):
#         self.session.add(self.Person())
#         self.session.commit()

#         # Requests must have the appropriate JSON Patch headers.
#         response = self.app.patch('/api/person/1',
#                                   content_type='application/vnd.api+json')
#         assert response.status_code == 400
#         response = self.app.patch('/api/person/1',
#                                   content_type='application/json')
#         assert response.status_code == 400

#     # TODO test bulk JSON Patch operations at the root level of the API.
#     def test_json_patch_create(self):
#         data = list(dict(op='add', path='/-', value=dict(name='foo')))
#         response = self.app.patch('/api/person', data=dumps(data))
#         assert response.status_code == 201
#         person = loads(response.data)
#         assert person['name'] == 'foo'

#     def test_json_patch_update(self):
#         person = self.Person(id=1, name='foo')
#         self.session.add(person)
#         self.session.commit()
#         data = list(dict(op='replace', path='/name', value='bar'))
#         response = self.app.patch('/api/person/1', data=dumps(data))
#         assert response.status_code == 204
#         assert person.name == 'bar'

#     def test_json_patch_to_one_relationship(self):
#         person1 = self.Person(id=1)
#         person2 = self.Person(id=2)
#         computer = self.Computer(id=1)
#         computer.owner = person1
#         self.session.add_all([person1, person2, computer])
#         self.session.commit()

#         # Change the owner of the computer from person 1 to person 2.
#         data = list(dict(op='replace', path='', value='2'))
#         response = self.app.patch('/api/computer/1/owner', data=dumps(data))
#         assert response.status_code == 204
#         assert computer.owner == person2

#     def test_json_patch_remove_to_one_relationship(self):
#         person = self.Person(id=1)
#         computer = self.Computer(id=1)
#         computer.owner = person
#         self.session.add_all([person, computer])
#         self.session.commit()

#         # Change the owner of the computer from person 1 to person 2.
#         data = list(dict(op='remove', path=''))
#         response = self.app.patch('/api/computer/1/owner', data=dumps(data))
#         assert response.status_code == 204
#         assert person.computers == []

#     def test_json_patch_to_many_relationship(self):
#         person = self.Person(id=1)
#         computer = self.Computer(id=1)
#         self.session.add_all([person, computer])
#         self.session.commit()

#         # Add computer 1 to the list of computers owned by person 1.
#         data = list(dict(op='add', path='/-', value='1'))
#         response = self.app.patch('/api/person/1/computers', data=dumps(data))
#         assert response.status_code == 204
#         assert person.computers == [computer]

#     def test_json_patch_remove_to_many_relationship(self):
#         person = self.Person(id=1)
#         computer = self.Computer(id=1)
#         person.computers = [computer]
#         self.session.add_all([person, computer])
#         self.session.commit()

#         # Remove computer 1 to the list of computers owned by person 1.
#         data = list(dict(op='remove', path='/1'))
#         response = self.app.patch('/api/person/1/computers', data=dumps(data))
#         assert response.status_code == 204
#         assert person.computers == []

#     def test_json_patch_delete(self):
#         person = self.Person(id=1)
#         self.session.add(person)
#         self.session.commit()

#         # Remove the person.
#         data = list(dict(op='remove', path=''))
#         response = self.app.patch('/api/person/1', data=dumps(data))
#         assert response.status_code == 204
#         assert self.Person.query.count() == 0

#     def test_json_patch_multiple(self):
#         # Create multiple person instances with a single request.
#         data = list(dict(op='add', path='/-', value=dict(name='foo')),
#                     dict(op='add', path='/-', value=dict(name='bar')))
#         response = self.app.patch('/api/person', data=dumps(data))
#         assert response.status_code == 200
#         assert response.content_type == 'application/json'
#         data = loads(response.data)
#         assert data[0]['person'][0]['name'] == 'foo'
#         assert data[1]['person'][0]['name'] == 'bar'
