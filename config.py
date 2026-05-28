import cx_Oracle

# config.py
ORACLE_DSN = cx_Oracle.makedsn('ptmscan.nh.inet', 1521, service_name='ORCLDB_SVC')
ORACLE_USER = 'cgestion'
ORACLE_PASSWORD = 'T3l3f0n1c4'
