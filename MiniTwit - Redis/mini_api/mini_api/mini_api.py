# -*- coding: utf-8 -*-
"""
    MiniTwit API
    ~~~~~~~~

    A microblogging REST API written with Flask and sqlite3.

"""

import time
import click
import redis
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
DATABASE = '/tmp/mini_api.db'
PER_PAGE = 30
DEBUG = True
SECRET_KEY = b'_5#y2L"F4Q8z\n\xec]/'

# create our little application :)
app = Flask('mini_api')
app.config.from_object(__name__)
app.config.from_envvar('MINITWIT_SETTINGS', silent=True)


# Redis server sorted sets
viewedUsers = "viewedUsersSet"
followedUsers = "followedUsersSet"


class TwitterAPIBasicAuth(BasicAuth):
    def __init__(self, app=None):
        if app is not None:
            self.app = app
            self.init_app(app)
        else:
            self.app = None

    def check_credentials(self, username, password):
        if username != None and password != None:
            
            user = query_db('select * from user where username = ?',[username], one=True)
            print "User Details in Auth", user
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


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    top = _app_ctx_stack.top
    if not hasattr(top, 'sqlite_db'):
        top.sqlite_db = sqlite3.connect(app.config['DATABASE'])
        top.sqlite_db.row_factory = sqlite3.Row
    return top.sqlite_db

def get_redis():
    """Opens connectivity to REDIS"""
    try:
        conn = redis.StrictRedis(
            host='127.0.0.1',
            port=6379)
        #print conn
        conn.ping()
        print 'Connected to Redis!'
        return conn
    except Exception as ex:
        print 'Error:', ex
        exit('Failed to connect, terminating.')


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
    if hasattr(top, 'sqlite_db'):
        top.sqlite_db.close()


def init_db():
    """Initializes the database."""
    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()


@app.cli.command('initdb')
def initdb_command():
    """Creates the database tables."""
    init_db()
    print('Initialized the database.')
    get_redis().delete(viewedUsers)
    get_redis().delete(followedUsers)
    print('Redis server cache cleared')


def populate_db():
    db = get_db()
    with app.open_resource('population.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()


def populate_redis():
    with app.open_resource('populate_redis.txt', mode='r') as f:
        for line in f:
            username = line.split(",")[0]
            score = line.split(",")[1]
            get_redis().zadd(followedUsers,int(score),username)

@app.cli.command('populatedb')
def populatedb_command():
    """Populates tables."""
    populate_db()
    print('populated the database.')
    populate_redis()
    print('populated the redis.')


####### Initial setup completes #######

def get_user_details():
    """Convenience method to look up the user."""
    rv = query_db('select * from user')
    return rv[0] if rv else None


def query_db(query, args=(), one=False):
    """Queries the database and returns a list of dictionaries."""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv



def get_user_id(username):
    """Convenience method to look up the id for a username."""
    rv = query_db('select user_id from user where username = ?',
                  [username], one=True)
    return rv[0] if rv else None

def viewed_users(username):
    """Function to store the user's profile view counter"""
    # ZINCRBY key increment member
    print "Setting the viewed users count"
    get_redis().zincrby(viewedUsers,username,1)

def followed_users(username,delete=False):
    """Function to store the user's profile view counter"""
    # ZINCRBY key increment member
    print "Setting the followed users count"
    if delete and get_redis().zscore(followedUsers,username) > 0:
        get_redis().zincrby(followedUsers,username,-1)
    else:
        get_redis().zincrby(followedUsers,username,1)


### REST Endpoints ###

# To get the top PER_PAGE viewed users
@app.route('/api/v1.0/topViewedUsers/<count>', methods=['GET'])
def top_viewed_users(count):
    top_viewed_users = get_redis().zrevrange(viewedUsers, 0, int(count)-1,"withscores")
    
    if get_redis().zcard(viewedUsers) > 0:
        return jsonify({'top_viewed_users': top_viewed_users}), 200
    else:
        return jsonify({'top_viewed_users': top_viewed_users}), 404




# To get the top PER_PAGE followed users
@app.route('/api/v1.0/topFollowedUsers/<count>', methods=['GET'])
def top_followed_users(count):
    top_followed_users = get_redis().zrevrange(followedUsers, 0, int(count)-1,"withscores")
    
    if get_redis().zcard(followedUsers) > 0:
        return jsonify({'top_followed_users': top_followed_users}), 200
    else:
        return jsonify({'top_followed_users': top_followed_users}), 404




# To get the most viewed user
@app.route('/api/v1.0/mostViewedUser', methods=['GET'])
def most_viewed_user():
    most_viewed_user = get_redis().zrevrange(viewedUsers,0,0)
    top_user_score = get_redis().zscore(viewedUsers,most_viewed_user[0])
    
    # This check is necessary if all of the users has the counter value as 0 then it the set is sorted alphebetically
    if top_user_score == 0.0:
        most_viewed_user = []
    return jsonify({'most_viewd_user': most_viewed_user}), 200




# To get the user's view count from Redis server
@app.route('/api/v1.0/mostViewedUser/<username>', methods=['GET'])
def userprofile_view_count(username):
    count = get_redis().zscore(viewedUsers,username)
    
    if count is not None:
        return jsonify({'userprofile_view_count': count}), 200
    else:
        return jsonify({'userprofile_view_count': count}), 404


# To get the most followed user
@app.route('/api/v1.0/mostFollowedUser', methods=['GET'])
def most_followed_user():
    most_followed_user = get_redis().zrevrange(followedUsers,0,0)
    popular_user_score = get_redis().zscore(followedUsers,most_followed_user[0])
    
    # This check is necessary if all of the users has the counter value as 0 then it the set is sorted alphebetically
    if popular_user_score == 0.0:
        most_followed_user = []
    return jsonify({'most_followed_user': most_followed_user}), 200



# To get the user's follow count from Redis server
@app.route('/api/v1.0/mostFollowedUser/<username>', methods=['GET'])
def user_follow_count(username):
    count = get_redis().zscore(followedUsers,username)
	
    if count is not None:
        return jsonify({'user_follow_count': count}), 200
    else:
        return jsonify({'user_follow_count': count}), 404



@app.route('/api/v1.0/userinfo/<user_id>', methods=['GET'])
def user_info(user_id):
    user = query_db('select * from user where user_id = ?',
                          [user_id], one=True)
    if user is None:
        abort(404)
    else:
        user_info = {"user_id": user['user_id'],"username":user['username'],"email":user['email']}
        return jsonify({'user_info': user_info}), 200



@app.route('/api/v1.0/timeline/<username>', methods=['POST'])
def user_timeline(username):
    user_info = query_db('select * from user where username = ?',
                            [username], one=True)
    if user_info is None:
        abort(404)
    else:
        profile_user= {"username": user_info['username'],"user_id":user_info['user_id']}
    
    followed = False
    if request.json.get('user_id') is not None:
        followed = query_db('''select 1 from follower where
            follower.who_id = ? and follower.whom_id = ?''',
            [request.json.get('user_id'), profile_user.get('user_id')],
            one=True) is not None
    
    messages = []
    db_items = query_db('''
            select message.*, user.* from message, user where
            user.user_id = message.author_id and user.user_id = ?
            order by message.pub_date desc limit ?''',
            [profile_user['user_id'], PER_PAGE])

    for db_item in db_items:
        message = {"username": db_item['username'], "email": db_item['email'], "text": db_item['text'], "pub_date": db_item['pub_date']}
        messages.append(message)
    
    viewed_users(username)
    return jsonify({'messages': messages,'followed' : followed, 'profile_user':profile_user}), 200    


@app.route('/api/v1.0/login', methods=['POST'])
def user_login():
    """User login."""
    user = query_db('''select * from user where username = ?''', [request.json.get('username')], one=True)

    if user is None:
        return jsonify({'error':'Invalid username'}),401
    elif not check_password_hash(user['pw_hash'],request.json.get('password')):
        return jsonify({'error':'Invalid password'}),401
    else:
        print 'User logged in'
    return jsonify({'user_id':user['user_id']}),200



# Posts the tweet
@app.route('/api/v1.0/message', methods=['POST'])
@basic_auth.required
def post_message():
    """Posts a new message for the user."""
    if not request.json or 'author_id' not in request.json or 'text' not in request.json:
        abort(400)

    db = get_db()

    author_id = request.json.get('author_id')
    text = request.json.get('text')
    pub_date = int(time.time())

    db.execute('''insert into message (author_id, text, pub_date) values (?, ?, ?)''',
               (author_id, text, pub_date))
    db.commit()
    #flash('Your message was recorded')
    message = {"author_id": author_id, "text": text, "pub_date": pub_date}
    return jsonify({'message': message}), 201


# User registration
@app.route('/api/v1.0/user', methods=['POST'])
def register_user():
    if request.method == 'POST':

        if not request.json:
            abort(400)
        else:
            db = get_db()

            db.execute('''insert into user (
              username, email, pw_hash) values (?, ?, ?)''',
                       [request.json.get('username'), request.json.get('email'),
                        generate_password_hash(request.json.get('password'))])
            db.commit()
            flash('You are successfully registered and can login now')
    return jsonify({'message': 'Successfully registered'}), 201


# Displays all the tweets irrespective of the user
@app.route('/api/v1.0/messages', methods=['GET'])
#@basic_auth.required
def list_all_tweets():
    """Displays the latest messages of all users."""
    messages = []

    db_items = query_db('''
        select message.*, user.* from message, user
        where message.author_id = user.user_id
        order by message.pub_date desc limit ?''', [PER_PAGE])

    for db_item in db_items:
        #message = {"message_id": db_item['message_id'], "author_id": db_item['author_id'],
                   #"text": db_item['text'], "pub_date": db_item['pub_date']}
        message = {"username": db_item['username'], "email": db_item['email'], "text": db_item['text'], "pub_date": db_item['pub_date']}
        messages.append(message)

    return jsonify({'messages': messages}), 200


# Displays all the tweets from the user and from the users being followed
@app.route('/api/v1.0/home', methods=['GET'])
@basic_auth.required
def list_following_users_tweets():
    """Displays a tweets of user being followed."""
    username = request.authorization.username
    timeline_messages = []
    
    user_id = get_user_id(username);
    db_items=query_db('''
        select message.*, user.* from message, user
        where message.author_id = user.user_id and (
            user.user_id = ? or
            user.user_id in (select whom_id from follower
                                    where who_id = ?))
        order by message.pub_date desc limit ?''',
        [user_id, user_id, PER_PAGE])

    for db_item in db_items:
        timeline_message = {"message_id": db_item['message_id'], "author_id": db_item['author_id'],
                         "text": db_item['text'], "pub_date": db_item['pub_date'], "username":db_item['username'], "email":db_item['email']}
        timeline_messages.append(timeline_message)

    return jsonify({'timeline_messages': timeline_messages}), 200




#Follows the user specified in the URL. Username which wants to follow must be specified in the request JSON
@app.route('/api/v1.0/follower/<whomUserName>', methods=['POST'])
@basic_auth.required
def user_follow(whomUserName):
    """Adds the current user as follower of the given user."""
    who_user_name = request.authorization.username
    print "****** Who user name in service : " + who_user_name
    whom_profile_user = query_db('select * from user where username = ?',
                                 [whomUserName], one=True)
    who_profile_user = query_db('select * from user where username = ?',
                                [who_user_name], one=True)

    followed = query_db('''select 1 from follower where
            follower.who_id = ? and follower.whom_id = ?''',
                        [who_profile_user['user_id'], whom_profile_user['user_id']], one=True) is not None

    if who_profile_user is None:
        return jsonify({'message': 'User trying to follow another user does not exist'}), 404

    if whom_profile_user is None:
        return jsonify({'message': 'User getting followed does not exist yet'}), 404

    if not followed:
        db = get_db()

        db.execute('''insert into follower (
              who_id, whom_id) values (?, ?)''',
                   [who_profile_user['user_id'], whom_profile_user['user_id']])
        db.commit()
        flash('Operation successful')
        
        # Update the cache to increase the counter
        followed_users(whomUserName)
        return jsonify({'message': 'Successfully added as a follower'}), 201
    else:
        return jsonify({'message': 'Specified user is already following another user'}), 403


#Unfollows the user specified in the URL. Username which wants to unfollow must be specified in the request JSON
@app.route('/api/v1.0/follower/<whomUserName>', methods=['DELETE'])
@basic_auth.required
def user_unfollow(whomUserName):
    """Unfollows the specified user"""
    who_user_name = request.authorization.username

    whom_profile_user = query_db('select * from user where username = ?',
                                 [whomUserName], one=True)
        
    who_profile_user = query_db('select * from user where username = ?',
                                [who_user_name], one=True)
    
    followed = query_db('''select 1 from follower where
            follower.who_id = ? and follower.whom_id = ?''',
                        [who_profile_user['user_id'], whom_profile_user['user_id']], one=True) is not None

    if who_profile_user is None:
        return jsonify({'message': 'User trying to unfollow another user does not exist'}), 404

    if whom_profile_user is None:
        return jsonify({'message': 'User getting unfollowed does not exist yet'}), 404

    if followed:
        db = get_db()

        db.execute('delete from follower where who_id=? and whom_id=?',
                   [who_profile_user['user_id'], whom_profile_user['user_id']])
        db.commit()
        flash('Operation successful')

        # Update the cache to decrease the counter
        followed_users(whomUserName,True)
        return jsonify({'message': 'Successfully unfollowed the specified user'}), 201
    else:
        return jsonify({'message': 'Specified user is not following another user'}), 404

