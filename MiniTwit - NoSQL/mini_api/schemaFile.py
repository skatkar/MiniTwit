#! /usr/bin/env python
'''
This file is used to inject a full *.cql file into a Cassandra database.
To run this script, all three command line parameters are required:
    
    python cassandra-cql.py hostname port script_file

An example script file would be:

    USE keyspace;

    CREATE COLUMNFAMILY projects (
      KEY uuid PRIMARY KEY,
      project_id int,
      name text
    );

'''
import cql
import sys

#def execute_file():
connection = cql.connect(host='127.0.0.1', port='9042', cql_version='3.0.0')
#connection = cluster.connect()
cursor = connection.cursor()

cql_file = open('schema_cassandra.cql')
cql_command_list = ''.join(cql_file.readlines()).split(";")
print cql_command_list
for cql_command in cql_command_list:
    if cql_command.replace('\n', ''):
        print '\n{command}'.format(command=cql_command.strip('\n'))
            #cursor.execute('{command};'.format(command=cql_command.replace('\n', ' ')))