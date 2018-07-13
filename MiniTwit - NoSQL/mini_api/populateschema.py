def populate_schema(session):
    print 'Inside populate schema'
    batchQuery = "BEGIN BATCH "
    with open('mini_api/data_cassandra.cql') as f:
        for line in f:
            batchQuery = batchQuery + line
    batchQuery = batchQuery + " APPLY BATCH;"
    prepared_stmt = session.prepare(batchQuery)
    session.execute(prepared_stmt)