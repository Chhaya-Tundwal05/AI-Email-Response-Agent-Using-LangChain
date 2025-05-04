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
        SELECT email_id, sender_email, subject, body, received_at, classified_category
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
            "classified_category": row[5]
        })

    return jsonify(data)

#########################################
# 📌 POST: Update category and capture learn choice
#########################################
@app.route("/api/update_email", methods=["POST"])
def update_email():
    data = request.json
    email_id = data.get("email_id")
    updated_category = data.get("updated_category")
    response_text = data.get("response")   # We will NOT save this to the DB
    learn = data.get("learn")  # True/False

    try:
        # ✅ Update only the category — keep status and escalated unchanged
        cursor.execute("""
            UPDATE emails
            SET classified_category = %s
            WHERE email_id = %s
        """, (updated_category, email_id))

        conn.commit()

        print(f"✅ Updated email {email_id} with new category: {updated_category}")
        print(f"📝 Response entered by admin (not saved to DB): {response_text}")

        if learn:
            print(f"🧠 Email {email_id} marked for learning!")

        return jsonify({"message": "Category updated successfully!"})

    except Exception as e:
        conn.rollback()
        print("❌ ERROR:", e)
        return jsonify({"error": str(e)}), 500

#########################################
# ✅ Run Flask
#########################################
if __name__ == "__main__":
    app.run(debug=True)
