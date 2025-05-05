from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import datetime

app = Flask(__name__)
CORS(app)

# ✅ Database connection
conn = psycopg2.connect(
    dbname="postgres",
    user="postgres",
    host="34.59.119.208",
    password="avantichhaya"
)
cursor = conn.cursor()

#########################################
# 📌 GET: Fetch escalated emails only
#########################################
@app.route("/api/escalations", methods=["GET"])
def get_escalations():
    cursor.execute("""
        SELECT email_id, sender_email, subject, body, received_at, classified_category, learn
        FROM emails
        WHERE classified_category = 'human_intervention'
    """)
    rows = cursor.fetchall()

    # Convert to list of dicts
    data = []
    for row in rows:
        data.append({
            "email_id": row[0],
            "sender_email": row[1],
            "subject": row[2],
            "body": row[3],
            "received_at": row[4].strftime('%Y-%m-%d %H:%M:%S'),
            "classified_category": row[5],
            "learn": row[6]  # can be None, True, or False
        })

    return jsonify(data)

#########################################
# 📌 POST: Update category and learn value
#########################################
@app.route("/api/update_email", methods=["POST"])
def update_email():
    data = request.json
    email_id = data.get("email_id")
    updated_category = data.get("updated_category")
    response_text = data.get("response")   # We will NOT save this to the DB
    learn = data.get("learn")  # True/False

    try:
        # ✅ Update category and learn only
        cursor.execute("""
            UPDATE emails
            SET classified_category = %s,
                learn = %s
            WHERE email_id = %s
        """, (updated_category, learn, email_id))

        conn.commit()

        print(f"✅ Updated email {email_id} → Category: {updated_category} | Learn: {learn}")
        print(f"📝 Response entered by admin (not saved to DB): {response_text}")

        return jsonify({"message": "Category and learn status updated successfully!"})

    except Exception as e:
        conn.rollback()
        print("❌ ERROR:", e)
        return jsonify({"error": str(e)}), 500

#########################################
# ✅ Run Flask
#########################################
if __name__ == "__main__":
    app.run(debug=True)
