# -*- coding: utf-8 -*-
"""
    MiniTwit API
    ~~~~~~~~

    A microblogging REST API written with Flask and sqlite3.

"""

import time
import re
import os
import csv
import click
import ConfigParser
import uuid
from flask_basicauth import BasicAuth
from sqlite3 import dbapi2 as sqlite3
from hashlib import md5
from datetime import datetime
from flask import Flask, jsonify, request, session, url_for, redirect, make_response, \
    render_template, abort, g, flash, _app_ctx_stack
from werkzeug import check_password_hash, generate_password_hash


# HTTP status return messages for 404 and 400
NOT_FOUND = 'Not found'
BAD_REQUEST = 'Bad request'

# configuration
#DATABASE = '/tmp/mini_api.db'
DATABASES = 'DATABASE0','DATABASE1','DATABASE2'
DATABASE0 = '/tmp/mini_api00.db'
DATABASE1 = '/tmp/mini_api01.db'
DATABASE2 = '/tmp/mini_api02.db'
PER_PAGE = 30
DEBUG = True
SECRET_KEY = b'_5#y2L"F4Q8z\n\xec]/'

# create our little application :)
app = Flask('mini_api')
app.config.from_object(__name__)
app.config.from_envvar('MINITWIT_SETTINGS', silent=True)

sqlite3.register_converter('GUID', lambda b: uuid.UUID(bytes_le=b))
sqlite3.register_adapter(uuid.UUID, lambda u: buffer(u.bytes_le))



class FileParser(ConfigParser.ConfigParser):
    def as_dict(self):
        usermappings = {}
        with open('mini_api/mappings.ini', 'r') as f:
            for line in f:
                line = line.rstrip() #removes trailing whitespace and '\n' chars
                if "=" not in line: 
                    continue #skips blanks and comments w/o =
                if line.startswith("#"): 
                    continue #skips comments which contain =
                k, v = line.split("=", 1)
                usermappings[k] = v
        return usermappings


class TwitterAPIBasicAuth(BasicAuth):
    def __init__(self, app=None):
        if app is not None:
            self.app = app
            self.init_app(app)
        else:
            self.app = None

    def check_credentials(self, username, password):
        if username != None and password != None:
            userid = fetch_userid(username)
            user = query_db(uuid.UUID(userid),'select * from user where username = ?',[username], one=True)
            if user != None:
                print "User is None", user['username']
                if user['username'] == username and check_password_hash(user['pw_hash'], password):
                        return 'true'
                else:
                        return None
            else:
                return None
        else:
            return None

basic_auth = TwitterAPIBasicAuth(app)


def get_user_details():
    """Convenience method to look up the user."""
    rv = query_db('select * from user')
    return rv[0] if rv else None


def get_all_db():
    """Opens a new database connection to all the database shards."""
    connections = []
    for db in DATABASES:
        connect = sqlite3.connect(app.config[db], detect_types=sqlite3.PARSE_DECLTYPES)
        connect.row_factory = sqlite3.Row
        connections.append(connect)
    return connections

def get_db(userid):
    """Opens a new database connection to the correct shard if there is none yet for the
    current application context."""
    dbNumber = getdbNumber(userid)
    print "***Database bucket selected is:",dbNumber
    
    # Pick up the correct database bucket
    DATABASE = DATABASES[dbNumber]
    sqlite_db = 'sqlite_db' + str(dbNumber)
    top = _app_ctx_stack.top
    
    if not hasattr(top, sqlite_db):
        print "*******Going to create new instance"
        #top.sqlite_db = sqlite3.connect(app.config['DATABASE'+ str(dbNumber)], detect_types=sqlite3.PARSE_DECLTYPES)
        top.sqlite_db = sqlite3.connect(app.config[DATABASE], detect_types=sqlite3.PARSE_DECLTYPES)
        top.sqlite_db.row_factory = sqlite3.Row
    else:
        print "*******Instance is already created...."
    return top.sqlite_db

#def get_db():
    #"""Opens a new database connection if there is none yet for the
    #current application context.
    #"""
    #top = _app_ctx_stack.top
    #if not hasattr(top, 'sqlite_db'):
        #top.sqlite_db = sqlite3.connect(app.config['DATABASE'], detect_types=sqlite3.PARSE_DECLTYPES)
        #top.sqlite_db.row_factory = sqlite3.Row
    #return top.sqlite_db



@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': NOT_FOUND}), 404)


@app.errorhandler(400)
def bad_request(error):
    return make_response(jsonify({'error': BAD_REQUEST}), 400)

@app.teardown_appcontext
def close_database(exception):
    """Closes the database again at the end of the request."""
    top = _app_ctx_stack.top
    if hasattr(top, 'sqlite_db'):
        top.sqlite_db.close()


#def init_db():
    #"""Initializes the database."""
    #db = get_db()
    #with app.open_resource('schema.sql', mode='r') as f:
        #db.cursor().executescript(f.read())
    #db.commit()


@app.cli.command('initdb')
def initdb_command():
    """Creates the database tables."""
    
    # If the file exists then truncate that file
    if os.path.exists("mini_api/mappings.ini"):
        #os.remove("mini_api/mappings.ini")
        fo = open("mini_api/mappings.ini", "rw+")
        fo.truncate()
    init_db()
    print('Initialized the database.')

def init_db():
    """Initializes the database."""
    
    connections = get_all_db()
    for connect in connections:
        with app.open_resource('schema.sql', mode='r') as f:
            connect.cursor().executescript(f.read())




#def populate_db():
    #db = get_db()
    #with app.open_resource('population.sql', mode='r') as f:
        #db.cursor().executescript(f.read())
    #db.commit()

#def populate_db():
    """Populates the database."""
    # Using the regular expression,it fetches the user_id from the given query
    # Each line of the populate sql contains INSERT queries
    #with app.open_resource('populate.sql', mode='r') as f:
        #for query in f:
            #a = re.findall('\'(.+?)\'', query)
            #b = ",".join(a)
            #userid = re.match("[^,]+",b).group(0)
            #connections = get_all_db()
            
            #db_number = getdbNumber(uuid.UUID(userid))
            #db = connections[db_number]
            #db.execute(query)
            #db.commit()
            #db.close()


# Function to populate the database
def populate_db():
    """Initializes the database."""
    with app.open_resource('populate.sql','r') as csvDataFile:
        csvReader = csv.reader(csvDataFile,delimiter='|')
        for line in csvReader:
            db_number = getdbNumber(uuid.UUID(line[1]))
            
            dbs = get_all_db()
            db = dbs[db_number]

            # Check if the line contains the word 'user'. 
            # If it is there then that query will be executed on USER table
            if "user" in line[0]:
                print "Add user table entry"
                username = line[2]
                db.execute('''insert into user (user_id,username, email, pw_hash) values (?, ?, ?, ?)''',[uuid.UUID(line[1]), username, line[3],line[4]])
                db.commit()
                db.close()
                update_Local_Mappings(username,str(line[1]))
            
            # Parameters at this line will be used for message table INSERT queries
            elif "message" in line[0]:
                print "Add message table entry"
                db.execute('''insert into message (author_id, message_id, text, pub_date) values (?, ?, ?, ?)''', [uuid.UUID(line[1]),uuid.UUID(line[2]),str(line[3]), int(line[4])])
                db.commit()
                db.close()
            
            # Parameters at this line will be used for follower table INSERT queries
            elif "follower" in line[0]:
                print "Add follower table entry"
                db.execute('''insert into follower (who_id, whom_id) values (?, ?)''', [uuid.UUID(line[1]),uuid.UUID(line[2])])
                db.commit()
                db.close()
            else:
                print "None"

@app.cli.command('populatedb')
def populatedb_command():
    """Populates tables."""
    populate_db()
    print('populated the database.')

####### Database setup completes #######

def update_Local_Mappings(username,userid):
    """Convinient method to update the username-userid mapping."""
    with open('mini_api/mappings.ini', 'a') as the_file:
        the_file.write(username + '=' + str(userid) + '\n')



#def fetch_userid(username):
    #"""Convinient method to fetch userid from the file system for the specified username."""
    #f = FileParser()
    #f.read("mini_api/mappings.ini")
    #d = f.as_dict()
    #print "****Dictionary object is :",d
    #if username not in d['Users']:
        #return None
    #return d['Users'][username]


def fetch_userid(username):
    f = FileParser()
    d = f.as_dict()
    if username not in d:
        return None
    return d[username]


def getdbNumber(userid):
    """Convinient method to identify the database bucket based on the userid."""
    dbNumber = int(int(userid) % 3)
    #print userid,' target db is: ',dbNumber
    return dbNumber

#def query_db(query, args=(), one=False):
    #"""Queries the database and returns a list of dictionaries."""
    #cur = get_db().execute(query, args)
    #rv = cur.fetchall()
    #return (rv[0] if rv else None) if one else rv


def query_db(userid,query, args=(), one=False):
    """Queries the database and returns a list of dictionaries."""
    cur = get_db(userid).execute(query, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv


def get_user_id(username):
    """Convenience method to look up the id for a username."""
    rv = query_db('select user_id from user where username = ?',
                  [username], one=True)
    return rv[0] if rv else None



### REST Endpoints ###
@app.route('/api/v1.0/testing', methods=['GET'])
@basic_auth.required
def testing():
    #user_id = uuid.UUID("a36d3845-7919-4375-8f78-20025de8a670")
    #user = query_db('''select * from user where user_id = ?''', [user_id], one=True)
    #print user['username']
    
    #userid = fetch_userid("swapnil")
    #print userid
    #return jsonify({'message':'Successful'}),200
    
    connections = get_all_db()
    print connections
    return jsonify({'message':'Successful'}),200

@app.route('/api/v1.0/login', methods=['POST'])
def user_login():
    """User login."""
    userid = fetch_userid(request.json.get('username'))
    user = query_db(uuid.UUID(userid),'''select * from user where username = ?''', [request.json.get('username')], one=True)

    if user is None:
        return jsonify({'error':'Invalid username'}),401
    elif not check_password_hash(user['pw_hash'],request.json.get('password')):
        return jsonify({'error':'Invalid password'}),401
    else:
        flash('User logged in')
    return jsonify({'message':'Successfully logged in'}),200



# Posts the tweet
@app.route('/api/v1.0/message', methods=['POST'])
@basic_auth.required
def post_message():
    """Posts a new message for the user."""
    if not request.json or 'text' not in request.json:
        abort(400)


    message_id = uuid.uuid4()
    #author_id = request.json.get('author_id')
    username = request.authorization.username
    author_id = fetch_userid(username)
    
    text = request.json.get('text')
    pub_date = int(time.time())

    db = get_db(uuid.UUID(author_id))

    db.execute('''insert into message (message_id,author_id, text, pub_date) values (?,?, ?, ?)''',
               (message_id,uuid.UUID(author_id), text, pub_date))
    db.commit()
    flash('Your message was recorded')
    message = {"author_id": author_id, "text": text, "pub_date": pub_date}
    return jsonify({'message': message}), 201


# User registration
@app.route('/api/v1.0/user', methods=['POST'])
def register_user():
    if request.method == 'POST':

        if not request.json:
            abort(400)
        else:
            userid = uuid.uuid4()
            print "*** User id of the new user is:",userid
            db = get_db(userid)

            db.execute('''insert into user (
              user_id, username, email, pw_hash) values (?, ?, ?, ?)''',
                       [userid,request.json.get('username'), request.json.get('email'),
                        generate_password_hash(request.json.get('password'))])
            db.commit()
            print 'Successfully registered'
            update_Local_Mappings(request.json.get('username'),userid)
    return jsonify({'message': 'Successfully registered'}), 201


# Displays all the tweets irrespective of the user
@app.route('/api/v1.0/messages', methods=['GET'])
@basic_auth.required
def list_all_tweets():
    """Displays all the tweets."""
    messages = []

    connections = get_all_db()
    for connection in connections:
        db_items = connection.execute('select * from message')
        for db_item in db_items:
            if db_item is not None:
                message = {"message_id": db_item['message_id'], "author_id": db_item['author_id'],
                   "text": db_item['text'], "pub_date": db_item['pub_date']}
                messages.append(message)

    return jsonify({'messages': messages}), 200


# Displays all the tweets of the given user
@app.route('/api/v1.0/messages/<username>', methods=['GET'])
def list_user_tweets(username):
    """Displays a users tweets."""
    userid = fetch_userid(username)
    #profile_user = query_db(uuid.UUID(userid),'''select * from user where username = ?''',
                            #[username], one=True)

    user_messages = []

    db_items = query_db(uuid.UUID(userid),'''
            select message.*, user.* from message, user where
            user.user_id = message.author_id and user.user_id = ?
            order by message.pub_date desc limit ?''',
                        [uuid.UUID(userid), PER_PAGE])

    for db_item in db_items:
        user_message = {"message_id": db_item['message_id'], "author_id": db_item['author_id'],
                        "text": db_item['text'], "username": db_item['username']}
        user_messages.append(user_message)

    return jsonify({'user_messages': user_messages}), 200


# Displays all the tweets from the user and from the users being followed
@app.route('/api/v1.0/home', methods=['GET'])
@basic_auth.required
def list_following_users_tweets():
    """Displays a tweets of user being followed."""
    username = request.authorization.username
    userid = fetch_userid(username)
    timeline_messages = []


    """This part will fetch messages form the users being followed"""
    follower_users = query_db(uuid.UUID(userid),'''select whom_id from follower where who_id = ?''',[uuid.UUID(userid)])
    if follower_users is not None:
        for follower_user in follower_users:
            db_items = query_db(follower_user['whom_id'],'''select * from message where author_id = ?''',[follower_user['whom_id']])
            for db_item in db_items:
                timeline_message = {"message_id": db_item['message_id'], "author_id": db_item['author_id'],
                          "text": db_item['text'], "pub_date": db_item['pub_date']}
                timeline_messages.append(timeline_message)

    """This part will fetch the messages posted by the user"""
    db_items = query_db(uuid.UUID(userid),'''
            select message.*, user.* from message, user where
            user.user_id = message.author_id and user.user_id = ?
            order by message.pub_date desc limit ?''',
                        [uuid.UUID(userid), PER_PAGE])

    for db_item in db_items:
        timeline_message = {"message_id": db_item['message_id'], "author_id": db_item['author_id'],
                          "text": db_item['text'], "pub_date": db_item['pub_date']}
        timeline_messages.append(timeline_message)

    return jsonify({'timeline_messages': timeline_messages}), 200


# Displays all the tweets from the user and from the users being followed
def list_following_users_messages():
    """Displays a tweets of user being followed."""
    username = request.authorization.username
    
    profile_user = query_db('select * from user where username = ?',[username], one=True)

    timeline_messages = []

    if profile_user is None:
        abort(404)


    """This part will fetch the messages from the users being followed"""
    db_items = query_db('''select message.* from message, follower where
                           follower.whom_id = message.author_id and follower.who_id = ?
                           order by message.pub_date desc limit ?''', [profile_user['user_id'], PER_PAGE])

    for db_item in db_items:
        timeline_message = {"message_id": db_item['message_id'], "author_id": db_item['author_id'],
                          "text": db_item['text'], "pub_date": db_item['pub_date']}
        timeline_messages.append(timeline_message)



    """This part will fetch the messages posted by the user"""
    db_items = query_db('''
            select message.*, user.* from message, user where
            user.user_id = message.author_id and user.user_id = ?
            order by message.pub_date desc limit ?''',
                        [profile_user['user_id'], PER_PAGE])

    for db_item in db_items:
        timeline_message = {"message_id": db_item['message_id'], "author_id": db_item['author_id'],
                          "text": db_item['text'], "pub_date": db_item['pub_date']}
        timeline_messages.append(timeline_message)

    return jsonify({'timeline_messages': timeline_messages}), 200




#Follows the user specified in the URL. Username which wants to follow must be specified in the request JSON
@app.route('/api/v1.0/follower/<whomUserName>', methods=['POST'])
@basic_auth.required
def user_follow(whomUserName):
    """Adds the current user as follower of the given user."""
    who_user_name = request.authorization.username
    who_id = fetch_userid(who_user_name)

    #whom_profile_user = query_db('select * from user where username = ?',
                                 #[whomUserName], one=True)
    #who_profile_user = query_db('select * from user where username = ?',
                                #[who_user_name], one=True)
    whom_id = fetch_userid(whomUserName)

    followed = query_db(uuid.UUID(who_id),'''select 1 from follower where
            follower.who_id = ? and follower.whom_id = ?''',
                        [uuid.UUID(who_id), uuid.UUID(whom_id)], one=True) is not None

    if who_id is None:
        return jsonify({'message': 'User trying to follow another user does not exist'}), 404

    if whom_id is None:
        return jsonify({'message': 'User getting followed does not exist yet'}), 404

    if not followed:
        db = get_db(uuid.UUID(who_id))

        db.execute('''insert into follower (
              who_id, whom_id) values (?, ?)''',
                   [uuid.UUID(who_id), uuid.UUID(whom_id)])
        db.commit()
        flash('Operation successful')
        return jsonify({'message': 'Successfully added as a follower'}), 201
    else:
        return jsonify({'message': 'Specified user is already following another user'}), 403



#Unfollows the user specified in the URL. Username which wants to unfollow must be specified in the request JSON
@app.route('/api/v1.0/follower/<whomUserName>', methods=['DELETE'])
@basic_auth.required
def user_unfollow(whomUserName):
    """Unfollows the specified user"""
    who_user_name = request.authorization.username
    who_id = fetch_userid(who_user_name)

    #whom_profile_user = query_db('select * from user where username = ?',
                                 #[whomUserName], one=True)
    #who_profile_user = query_db('select * from user where username = ?',
                                #[who_user_name], one=True)
    whom_id = fetch_userid(whomUserName)

    followed = query_db(uuid.UUID(who_id),'''select 1 from follower where
            follower.who_id = ? and follower.whom_id = ?''',
                        [uuid.UUID(who_id), uuid.UUID(whom_id)], one=True) is not None

    if who_id is None:
        return jsonify({'message': 'User trying to unfollow another user does not exist'}), 404

    if whom_id is None:
        return jsonify({'message': 'User getting unfollowed does not exist yet'}), 404

    if followed:
        db = get_db(uuid.UUID(who_id))

        db.execute('delete from follower where who_id=? and whom_id=?',
                   [uuid.UUID(who_id), uuid.UUID(whom_id)])
        db.commit()
        flash('Operation successful')
        return jsonify({'message': 'Successfully unfollowed the specified user'}), 201
    else:
        return jsonify({'message': 'Specified user is not following another user'}), 403

