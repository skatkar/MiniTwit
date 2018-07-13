def init_schema(session):
    print 'Inside init schema'
    print session
    #session.execute("CREATE TABLE users (user_id uuid,username text,email text,pw_hash text,PRIMARY KEY (username));")
    #session.execute("CREATE INDEX on users(user_id);")
    #session.execute("CREATE TABLE user_messages (message_id uuid,username text,email text,text text,pub_date bigint,PRIMARY KEY (message_id));")
    #session.execute("CREATE INDEX on user_messages(username);")
    #session.execute("CREATE TABLE user_follows(username text,follows_usernames list<text>,PRIMARY KEY(username));")
    with open('mini_api/schema_cassandra.cql') as f:
        for line in f:
            session.execute(line)