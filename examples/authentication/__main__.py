# -*- coding: utf-8; Mode: Python -*-
#
# Copyright 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
#
# This file is part of Flask-Restless.
#
# Flask-Restless is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# Flask-Restless is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Flask-Restless. If not, see <http://www.gnu.org/licenses/>.
"""
    Authentication example using Flask-Login
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This provides a simple example of using Flask-Login as the authentication
    framework which can guard access to certain API endpoints.

    This requires the following Python libraries to be installed:

    * Flask
    * Flask-Restless
    * Flask-Login
    * Flask-WTF
    * SQLAlchemy

    To install them using ``pip``, do::

        pip install Flask Flask-Restless Flask-Login Flask-WTF SQLAlchemy

    To use this example, run this package from the command-line. If you are
    using Python 2.7 or later::

        python -m authentication

    If you are using Python 2.6 or earlier::

        python -m authentication.__main__

    Attempts to access the URL of the API for the :class:`User` class at
    ``http://localhost:5000/api/user`` will fail with an :http:statuscode:`401`
    because you have not yet logged in. To log in, visit
    ``http://localhost:5000/login`` and login with username ``example`` and
    password ``example``. Once you have successfully logged in, you may now
    make :http:get:`http://localhost:5000/api/user` requests.

    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3, see COPYING for more details

"""
import os
import os.path

from flask import Flask, render_template, redirect, url_for
from flask.ext.restless import APIManager
from flask.ext.login import current_user, login_user, LoginManager, UserMixin
from flask.ext.wtf import PasswordField, SubmitField, TextField, Form
from sqlalchemy import create_engine, Column, Integer, Unicode
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Create the declarative base class for the SQLAlchemy models.
Base = declarative_base()


# Step 1: create the user database model.
class User(Base, UserMixin):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    username = Column(Unicode)
    password = Column(Unicode)

# Step 2: setup the database and the SQLAlchemy session.
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'test.sqlite')
if os.path.exists(DATABASE):
    os.unlink(DATABASE)
engine = create_engine('sqlite:///%s' % DATABASE)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# Step 3: create a test user in the database.
user1 = User(username=u'example', password=u'example')
session.add(user1)
session.commit()

# Step 4: create the Flask application and its login manager.
app = Flask(__name__)
login_manager = LoginManager()
login_manager.setup_app(app)


# Step 5: this is required for Flask-Login.
@login_manager.user_loader
def load_user(userid):
    return session.query(User).filter_by(id=userid).first()


# Step 6: create the login form.
class LoginForm(Form):
    username = TextField('username')
    password = PasswordField('password')
    submit = SubmitField('Login')


# Step 7: create endpoints for the application, one for index and one for login
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        #
        # you would check username and password here...
        #
        username, password = form.username.data, form.password.data
        user = session.query(User).filter_by(username=username,
                                             password=password).one()
        login_user(user)
        return redirect(url_for('index'))
    return render_template('login.html', form=form)

# Step 8: create the API for User.
api_manager = APIManager(app)
auth_func = lambda: current_user.is_authenticated()
api_manager.create_api(session, User, authentication_required_for=['GET'],
                       authentication_function=auth_func)

# Step 9: configure and run the application
app.config['DEBUG'] = True
app.config['TESTING'] = True
app.config['SECRET_KEY'] = os.urandom(24)
app.run()
