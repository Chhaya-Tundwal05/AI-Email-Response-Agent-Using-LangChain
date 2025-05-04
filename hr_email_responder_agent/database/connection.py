# db/connection.py

import psycopg2

class DBConnection:
    def __init__(self, dbname, user, host, password, port=5432):
        self.dbname = dbname
        self.user = user
        self.host = host
        self.password = password
        self.port = port
        self.conn = None

    def connect(self):
        try:
            self.conn = psycopg2.connect(
                dbname=self.dbname,
                user=self.user,
                host=self.host,
                password=self.password,
                port=self.port
            )
            print("✅ Connected to PostgreSQL")
            return self.conn
        except Exception as e:
            print("🚨 Connection Error:", e)
            return None