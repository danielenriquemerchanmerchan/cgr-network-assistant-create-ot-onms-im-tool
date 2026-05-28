import cx_Oracle as ora
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv() 

#Carga de Variables de entorno
DB_MAXIMO_USER=os.getenv('DB_MAXIMO_USER')
DB_MAXIMO_PASSWORD=os.getenv('DB_MAXIMO_PASSWORD')
DB_MAXIMO_DSN=os.getenv('DB_MAXIMO_DSN')
DB_PTM_USER=os.getenv('DB_PTM_USER')
DB_PTM_PASSWORD=os.getenv('DB_PTM_PASSWORD')
DB_PTM_DSN=os.getenv('DB_PTM_DSN')
DB_ROSE_USER=os.getenv('DB_ROSE_USER')
DB_ROSE_PSW=os.getenv('DB_ROSE_PASSWORD')
DB_ROSE_HOST=os.getenv('DB_ROSE_HOST')
DB_ROSE_DB=os.getenv('DB_ROSE_DATABASE')


def maximo():
	connection=ora.connect(user=DB_MAXIMO_USER, password=DB_MAXIMO_PASSWORD, dsn=DB_MAXIMO_DSN, encoding= 'UTF-8')
	return connection


def ptm():
	connection=ora.connect(user=DB_PTM_USER, password=DB_PTM_PASSWORD, dsn=DB_PTM_DSN, encoding= 'UTF-8')
	return connection


def rose():
	connection = psycopg2.connect(host=DB_ROSE_HOST, database=DB_ROSE_DB,user=DB_ROSE_USER, password=DB_ROSE_PSW)
	return connection
