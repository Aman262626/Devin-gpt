from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

POLLINATIONS_URL = "https://text.pollinations.ai/"


def get_chatbot_response(question):
    payload = {
        "messages": [
            {
                "role": "system",
                "content": "You are CodeX Network AI, a helpful and knowledgeable assistant. "
                           "Respond clearly and concisely.",
            },
            {
                "role": "user",
                "content": question,
            },
        ],
        "model": "openai",
    }

    try:
        response = requests.post(
            POLLINATIONS_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60,
        )

        if response.status_code == 200:
            answer = response.text.strip()
            if answer:
                return {"success": True, "response": answer}
            return {"success": False, "error": "Empty response from AI"}

        return {
            "success": False,
            "error": f"AI service returned status {response.status_code}",
        }

    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"An error occurred: {str(e)}"}


@app.route("/")
def home():
    return jsonify({"message": "CodeX_Network Flask API Running 🚀"})


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()

    if not data or "question" not in data:
        return jsonify({
            "success": False,
            "error": "Please provide a question",
        }), 400

    result = get_chatbot_response(data["question"])
    return jsonify(result)


if __name__ == "__main__":
    app.run()
