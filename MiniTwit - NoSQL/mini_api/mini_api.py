# -*- coding: utf-8 -*-
"""
    MiniTwit API
    ~~~~~~~~

    A microblogging REST API written with Flask and Cassandra.

"""

import time
import click
import uuid
from flask_basicauth import BasicAuth
from hashlib import md5
from datetime import datetime
from flask import Flask, jsonify, request, session, url_for, redirect, make_response, \
    render_template, abort, g, flash, _app_ctx_stack
from werkzeug import check_password_hash, generate_password_hash
from flask import Flask
from initschema import init_schema
from populateschema import populate_schema
from cassandra.cluster import Cluster



# HTTP status return messages for 404 and 400
NOT_FOUND = 'Not found'
BAD_REQUEST = 'Bad request'

# configuration

PER_PAGE = 30
DEBUG = True
SECRET_KEY = b'_5#y2L"F4Q8z\n\xec]/'

# create our little application :)
app = Flask('mini_api')
app.config.from_object(__name__)
app.config.from_envvar('MINITWIT_SETTINGS', silent=True)
cluster = Cluster()


class TwitterAPIBasicAuth(BasicAuth):
    def __init__(self, app=None):
        if app is not None:
            self.app = app
            self.init_app(app)
        else:
            self.app = None

    def check_credentials(self, username, password):
        if username != None and password != None:
            
            user = cql_query_db('select * from users where username = ?',[username], one=True)
            print "User Details in Auth", user
            if user != None:
                print "User is None", user.username
                if user.username == username and check_password_hash(user.pw_hash, password):
                        return 'true'
                else:
                        return None
            else:
                return None
        else:
            return None

basic_auth = TwitterAPIBasicAuth(app)



@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': NOT_FOUND}), 404)


@app.errorhandler(400)
def bad_request(error):
    return make_response(jsonify({'error': BAD_REQUEST}), 400)

@app.teardown_appcontext
def close_database(exception):
    """Closes the database again at the end of the request."""
    print "Closing the connection"
    top = _app_ctx_stack.top
    print top
    if hasattr(top, 'cassandra_cluster'):
        print 'I am closing the session'
        top.cassandra_cluster.shutdown()


def init_db():
    """Initializes the database."""
    db = get_db()
    init_schema(db)

@app.cli.command('initdb')
def initdb_command():
    """Creates the database tables."""
    init_db()
    print('Initialized the database.')


def populate_db():
    db = get_db()
    populate_schema(db)

@app.cli.command('populatedb')
def populatedb_command():
    """Populates tables."""
    populate_db()
    print('populated the database.')

####### Database setup completes #######

def get_user_details(username):
    """Convenience method to look up the user."""
    rv = cql_query_db('select * from users where username = ?',[username], one=True)
    #return rv[0] if rv else None
    return rv


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    top = _app_ctx_stack.top
    if not hasattr(top, 'cassandra_cluster'):
        print '****Existing context not found for cassandra cluster*****'
        top.cassandra_cluster = cluster.connect('minitwit')
    return top.cassandra_cluster



def get_user_id(username):
    """Convenience method to look up the id for a username."""
    rv = cql_query_db('select user_id from user where username = ?',
                  [username], one=True)
    return rv[0] if rv else None

def cql_query_db(query, args=(), one=False):
    """Queries the database and returns a list of dictionaries."""
    prepared_stmt = get_db().prepare(query)
    rv = get_db().execute(prepared_stmt,args)
    return (rv[0] if rv else None) if one else rv
    

### REST Endpoints ###

@app.route('/api/v1.0/userinfo/<user_id>', methods=['GET'])
def user_info(user_id):
    uuid_user_id = uuid.UUID(user_id)
    print uuid_user_id
    user = cql_query_db('select * from users where user_id = ? ALLOW FILTERING',[uuid_user_id], one=True)
    if user is None:
        abort(404)
    else:
        user_info = {"user_id": user.user_id,"username":user.username,"email":user.email}
        return jsonify({'user_info': user_info}), 200


@app.route('/api/v1.0/login', methods=['POST'])
def user_login():
    """User login."""
    user = cql_query_db('''select * from users where username = ?''', [request.json.get('username')], one=True)

    if user is None:
        return jsonify({'error':'Invalid username'}),401
    elif not check_password_hash(user.pw_hash,request.json.get('password')):
        return jsonify({'error':'Invalid password'}),401
    else:
        print 'User logged in'
    return jsonify({'user_id':user.user_id}),200



# Posts the tweet
@app.route('/api/v1.0/message', methods=['POST'])
@basic_auth.required
def post_message():
    """Posts a new message for the user."""
    if not request.json or 'text' not in request.json:
        abort(400)

    db = get_db()

    username = request.authorization.username
    message_id = uuid.uuid1()
    text = request.json.get('text')
    pub_date = int(time.time())
    email = get_user_details(username).email

    db.execute('''insert into user_messages (
              message_id, username, text, pub_date,email) values (%s, %s, %s, %s, %s)''',
                       [message_id, username, text, pub_date, email])
    
    #message = "{" + text + "," + pub_date + "}"
    
    #print message
    #cql_query_db('''insert into user_messages (username, messages) values (%s, %s)''',
               #[username, message])
    #db.commit()

    #flash('Your message was recorded')
    #stmt = db.execute("insert into user_messages (username, messages) values (?, ?)")
    #db.execute(stmt,[username,message])
    #print '''update user_messages set messages = {txt :'''+ '\"'+request.json.get('text') +'\"'+''',pub_date:'''+ '\"'+str(int(time.time()))+'\"' +'''} where username=''' + '\"' + username +'\"'
    #db.execute('''update user_messages set messages = {txt :'''+ "'"+request.json.get('text') +"'"+''',pub_date:'''+ "'"+str(int(time.time()))+"'" +'''} where username=''' + "'" + username +"'")
    #db.execute("INSERT INTO user_messages (username, messages) VALUES (%s, %s)",
                #(username, Message("This is new tweet", "78723")))
    #message = {"username": username, "text": text, "pub_date": pub_date}
    message = {"username": username, "text": text, "pub_date": pub_date}
    return jsonify({'message': message}), 201


# User registration
@app.route('/api/v1.0/user', methods=['POST'])
def register_user():
    if request.method == 'POST':

        if not request.json:
            abort(400)
        else:
            db = get_db()

            db.execute('''insert into users (
              username, user_id, email, pw_hash) values (%s, %s, %s, %s)''',
                       [request.json.get('username'), uuid.uuid1(), request.json.get('email'),
                        generate_password_hash(request.json.get('password'))])
            #db.commit()
            flash('You are successfully registered and can login now')
    return jsonify({'message': 'Successfully registered'}), 201


# Displays all the tweets irrespective of the user
@app.route('/api/v1.0/messages', methods=['GET'])
#@basic_auth.required
def list_all_tweets():
    """Displays the latest messages of all users."""
    messages = []

    db_items = cql_query_db('''SELECT * from user_messages''')

    for db_item in db_items:
        message = {"username": db_item.username, "email": db_item.email, "text": db_item.text, "pub_date": db_item.pub_date}
        messages.append(message)

    return jsonify({'messages': messages}), 200



# Displays all the tweets from the user and from the users being followed
@app.route('/api/v1.0/home', methods=['GET'])
@basic_auth.required
def list_following_users_tweets():
    """Displays a tweets of user being followed."""
    username = request.authorization.username
    timeline_messages = []
    
    db_items = cql_query_db('''select * from user_messages where username = ? ALLOW FILTERING''',[username])
    for db_item in db_items:

        user_message = {"email" : db_item.email, "pub_date" : db_item.pub_date, "text" : db_item.text,"username" : db_item.username}
        timeline_messages.append(user_message)
    
    follows_usernames_row = cql_query_db('''select follows_usernames from user_follows where username = ? ''',[username],one=True)
    for follow_username in follows_usernames_row.follows_usernames:
        db_items = cql_query_db('''select * from user_messages where username =?''', [follow_username])
        for db_item in db_items:
            follow_user_message = {"email" : db_item.email, "pub_date" : db_item.pub_date, "text" : db_item.text,"username" : db_item.username}
            timeline_messages.append(follow_user_message)

    return jsonify({'timeline_messages': timeline_messages}), 200


@app.route('/api/v1.0/timeline/<username>', methods=['POST'])
def user_timeline(username):
    user_info = get_user_details(username)
    if user_info is None:
        abort(404)
    else:
        profile_user= {"username": user_info.username,"user_id":user_info.user_id}
    
    followed = False
    if request.json.get('user_id') is not None:
        uuid_user_id = uuid.UUID(request.json.get('user_id'))
        row = cql_query_db('select username from users where user_id = ? ALLOW FILTERING',[uuid_user_id],one=True)
        
        follows_usernames_row = cql_query_db('''select follows_usernames from user_follows where username = ?''',[row.username],one=True)
        
        if username in follows_usernames_row.follows_usernames:
            followed = True
    
    
    messages = []
    db_items = cql_query_db('''select * from user_messages where username = ?''',[username])
    for db_item in db_items:
        message = {"username": db_item.username, "email": db_item.email, "text": db_item.text, "pub_date": db_item.pub_date}
        messages.append(message)

    return jsonify({'messages': messages,'followed' : followed, 'profile_user':profile_user}), 200    

#Follows the user specified in the URL. Username which wants to follow must be specified in the request JSON
@app.route('/api/v1.0/follower/<whomUserName>', methods=['POST'])
@basic_auth.required
def user_follow(whomUserName):
    whom_profile_user = get_user_details(whomUserName)
    if whom_profile_user is None:
        return jsonify({'message': 'User getting followed does not exist'}), 404
    
    who_user_name = request.authorization.username
    follows_usernames_row = cql_query_db('select * from user_follows where username = ?',[who_user_name], one=True)
    if whomUserName not in follows_usernames_row.follows_usernames:
        get_db().execute("""update user_follows set follows_usernames = follows_usernames + [%s] where username = %s""",(whomUserName,who_user_name))
        return jsonify({'message': 'Successfully added as a follower'}), 201
    else:
        return jsonify({'message': 'Logged in user is already following the specified user'}), 403
    

#Unfollows the user specified in the URL. Username which wants to unfollow must be specified in the request JSON
@app.route('/api/v1.0/follower/<whomUserName>', methods=['DELETE'])
@basic_auth.required
def user_unfollow(whomUserName):
    whom_profile_user = get_user_details(whomUserName)
    if whom_profile_user is None:
        return jsonify({'message': 'User getting unfollowed does not exist'}), 404
    
    who_user_name = request.authorization.username
    follows_usernames_row = cql_query_db('select * from user_follows where username = ?',[who_user_name], one=True)
    if whomUserName in follows_usernames_row.follows_usernames:
        get_db().execute("""update user_follows set follows_usernames = follows_usernames - [%s] where username = %s""",(whomUserName,who_user_name))
        return jsonify({'message': 'Successfully unfollowd'}), 201
    else:
        return jsonify({'message': 'Logged in user is not following the specified user'}), 403
   