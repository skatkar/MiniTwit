import uuid

userid = uuid.uuid4()
dbNumber = (int(userid) % 3)
print 'Get the DB number for ',userid,'DB number is ',dbNumber
