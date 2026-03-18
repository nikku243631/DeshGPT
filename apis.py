from flask import Flask, render_template, request, jsonify
from apis import get_ai_response

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    msg = data.get("message")

    reply = get_ai_response(msg)

    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run()
