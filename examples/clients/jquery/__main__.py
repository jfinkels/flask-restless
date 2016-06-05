"""
    Using Flask-Restless with jQuery
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This provides a simple example of using Flask-Restless on the server to
    create ReSTful API endpoints and [jQuery][0] on the client to make API
    requests.

    This requires the following Python libraries to be installed:

    * Flask
    * Flask-Restless
    * Flask-SQLAlchemy

    To install them using ``pip``, do::

        pip install Flask Flask-SQLAlchemy Flask-Restless

    To use this example, run this package from the command-line. If you are
    using Python 2.7 or later::

        python -m jquery

    If you are using Python 2.6 or earlier::

        python -m jquery.__main__

    To view the example in action, direct your web browser to
    ``http://localhost:5000``. For this example to work, you must have
    an Internet connection (in order to access jQuery from a CDN) and
    you must enable JavaScript in your web browser (in order to make
    requests to the Flask application).

    :copyright: 2012 Jeffrey Finkelstein <jeffrey.finkelstein@gmail.com>
    :license: GNU AGPLv3+ or BSD

"""
import os
import os.path

from flask import Flask, render_template
from flask_restless import APIManager
from flask_sqlalchemy import SQLAlchemy


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


# Step 3: create the database model.
class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode)


# Step 4: create the database and add some test people.
db.create_all()
for i in range(1, 10):
    name = u'person{0}'.format(i)
    person = Person(name=name)
    db.session.add(person)
db.session.commit()
print(Person.query.all())


# Step 5: create endpoints for the application.
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

# Step 6: create the API endpoints.
api_manager.create_api(Person, methods=['GET', 'POST'])

# Step 7: run the application.
app.run()
