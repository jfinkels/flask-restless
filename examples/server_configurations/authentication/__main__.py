"""
    Authentication example using Flask-Login
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This provides a simple example of using Flask-Login as the authentication
    framework which can guard access to certain API endpoints.

    This requires the following Python libraries to be installed:

    * Flask
    * Flask-Login
    * Flask-Restless
    * Flask-SQLAlchemy
    * Flask-WTF

    To install them using ``pip``, do::

        pip install Flask Flask-SQLAlchemy Flask-Restless Flask-Login Flask-WTF

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
    :license: GNU AGPLv3+ or BSD

"""
import os
import os.path

from flask import flash, Flask, render_template, redirect, url_for
from flask_login import current_user, login_user, LoginManager, UserMixin
from flask_restless import APIManager, ProcessingException
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import PasswordField, SubmitField, TextField, Form

# Step 0: the database in this example is at './test.sqlite'.
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'test.sqlite')
if os.path.exists(DATABASE):
    os.unlink(DATABASE)

# Step 1: setup the Flask application.
app = Flask(__name__)
app.config['DEBUG'] = True
app.config['TESTING'] = True
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///%s' % DATABASE

# Step 2: initialize extensions.
db = SQLAlchemy(app)
api_manager = APIManager(app, flask_sqlalchemy_db=db)
login_manager = LoginManager()
login_manager.setup_app(app)


# Step 3: create the user database model.
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.Unicode)
    password = db.Column(db.Unicode)


# Step 4: create the database and add a test user.
db.create_all()
user1 = User(username=u'example', password=u'example')
db.session.add(user1)
db.session.commit()


# Step 5: this is required for Flask-Login.
@login_manager.user_loader
def load_user(userid):
    return User.query.get(userid)


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
        matches = User.query.filter_by(username=username,
                                       password=password).all()
        if len(matches) > 0:
            login_user(matches[0])
            return redirect(url_for('index'))
        flash('Username and password pair not found')
    return render_template('login.html', form=form)


# Step 8: create the API for User with the authentication guard.
def auth_func(**kw):
    if not current_user.is_authenticated():
        raise ProcessingException(description='Not Authorized', code=401)


api_manager.create_api(User, preprocessors=dict(GET_SINGLE=[auth_func],
                                                GET_MANY=[auth_func]))

# Step 9: configure and run the application
app.run()

# Step 10: visit http://localhost:5000/api/user in a Web browser. You will
# receive a "Not Authorized" response.
#
# Step 11: visit http://localhost:5000/login and enter username "example" and
# password "example". You will then be logged in.
#
# Step 12: visit http://localhost:5000/api/user again. This time you will get a
# response showing the objects in the User table of the database.
