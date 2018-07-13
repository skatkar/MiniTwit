use minitwit;
CREATE TABLE users (user_id uuid,username text,email text,pw_hash text,PRIMARY KEY (username));
CREATE INDEX on users(user_id);
CREATE TABLE user_messages (message_id uuid,username text,email text,text text,pub_date bigint,PRIMARY KEY(message_id,pub_date)) with clustering order by (pub_date desc);
CREATE INDEX on user_messages(username);
CREATE TABLE user_follows(username text,follows_usernames list<text>,PRIMARY KEY(username));