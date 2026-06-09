import psycopg2

def get_db():
    conn = psycopg2.connect(
        dbname="homero_db",
        user="brunopontes",
        host="localhost"
    )
    return conn