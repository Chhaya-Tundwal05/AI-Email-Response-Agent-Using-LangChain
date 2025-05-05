from db.connection import DBConnection

if __name__ == "__main__":
    db = DBConnection(
        dbname="your_db",
        user="your_user",
        host="localhost",
        password="your_password"
    )
    conn = db.connect()
    if not conn:
        raise Exception("❌ Failed to connect to DB")

    cursor = conn.cursor()