from flask import Flask, request, jsonify
import requests
import json

app = Flask(__name__)

CHATBOT_URL = "https://chatbot-ji1z.onrender.com/chatbot-ji1z"


def get_chatbot_response(question):

    english_instruction = "Please respond in English. "
    enhanced_question = english_instruction + question

    payload = {
        "messages": [
            {
                "role": "assistant",
                "content": "Hello! How can I help you today?"
            },
            {
                "role": "user",
                "content": enhanced_question
            }
        ]
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Location": "https://seoschmiede.at/en/aitools/chatgpt-tool/",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            CHATBOT_URL,
            json=payload,
            headers=headers
        )

        if response.status_code == 200:
            api_response = response.json()

            return {
                "success": True,
                "response": api_response['choices'][0]['message']['content']
            }

        return {
            "success": False,
            "error": f"Failed with status code: {response.status_code}"
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.route("/")
def home():
    return jsonify({
        "message": "CodeX_Network Flask API Running 🚀"
    })


@app.route("/chat", methods=["POST"])
def chat():

    data = request.get_json()

    if not data or "question" not in data:
        return jsonify({
            "success": False,
            "error": "Please provide a question"
        }), 400

    result = get_chatbot_response(data["question"])

    return jsonify(result)


if __name__ == "__main__":
    app.run()
