"""Web app for the runcompose tool."""

import json
import os

import flask
import google.auth.transport.requests
import google.oauth2.id_token
import requests


app = flask.Flask(__name__)

# Get LLM configuration from environment variables
LLM_URL = os.environ.get("LLM_URL", "")
if "/engines/v1/" in LLM_URL:
  LLM_URL = LLM_URL.replace("/engines/v1/", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
HISTORY_DIR = "/data/history"


@app.route("/")
def index():
  return flask.render_template("index.html")


@app.route("/ask", methods=["POST"])
def ask():
  """Returns the response from the LLM agent."""
  os.makedirs(HISTORY_DIR, exist_ok=True)

  is_json_request = flask.request.is_json

  if is_json_request:
    data = flask.request.get_json()
    question = data.get("question")
    username = data.get("username")
  else:
    question = flask.request.form.get("question")
    username = flask.request.form.get("username")

  if not question:
    error_message = "Please provide a question."
    if is_json_request:
      return flask.jsonify(error=error_message), 400
    else:
      return flask.render_template("index.html", error=error_message)

  if not username:
    error_message = "Please provide a username."
    if is_json_request:
      return flask.jsonify(error=error_message), 400
    else:
      return flask.render_template("index.html", error=error_message)

  payload = {}

  try:
    history = []
    history_file = os.path.join(HISTORY_DIR, f"{username}.json")
    if os.path.exists(history_file):
      with open(history_file, "r") as f:
        history = json.load(f)

    messages = [
        {"role": "system", "content": "You are a helpful assistant."}
    ]
    for item in history[-10:]:
      messages.append({"role": "user", "content": item["question"]})
      messages.append({"role": "assistant", "content": item["response"]})
    messages.append({"role": "user", "content": question})

    payload = {
        "model": LLM_MODEL,
        "messages": messages,
    }

    headers = {"Content-Type": "application/json"}

    chat_completion_url = f"{LLM_URL}/engines/llama.cpp/v1/chat/completions"
    response = requests.post(
        chat_completion_url,
        headers=headers,
        data=json.dumps(payload),
        timeout=5,
    )

    response.raise_for_status()  # Raise an exception for bad status codes

    response_data = response.json()
    # Extract the message content from the response
    if response_data.get("choices") and response_data["choices"]:
      message = response_data["choices"][0].get("message", {})
      content = message.get("content", "No content in response.")
    else:
      content = "No response from the model."

    history.append({"question": question, "response": content})
    with open(history_file, "w") as f:
      json.dump(history, f)

  except requests.exceptions.RequestException as e:
    content = f"Error connecting to the LLM agent: {e}"
  except Exception as e:
    content = f"An unexpected error occurred: {e}"

  return flask.jsonify(payload=payload, question=question, response=content)


@app.route("/history")
def get_history():
  """Returns the chat history for a user."""
  username = flask.request.args.get("username")
  if not username:
    return flask.jsonify(error="Please provide a username."), 400

  history_file = os.path.join(HISTORY_DIR, f"{username}.json")
  if os.path.exists(history_file):
    with open(history_file, "r") as f:
      history = json.load(f)
    return flask.jsonify(history=history)
  else:
    return flask.jsonify(history=[])


@app.route("/delete_history", methods=["POST"])
def delete_history():
  """Deletes the chat history for a user."""
  data = flask.request.get_json()
  username = data.get("username")
  if not username:
    return flask.jsonify(error="Please provide a username."), 400

  history_file = os.path.join(HISTORY_DIR, f"{username}.json")
  if os.path.exists(history_file):
    os.remove(history_file)
    return flask.jsonify(message="History deleted successfully.")
  else:
    return flask.jsonify(error="No history found for this user."), 404


@app.route("/load_model_dmr", methods=["POST"])
def load_model():
  """Loads the model."""

  try:
    model_create_url = f"{LLM_URL}/models/create"
    response = requests.post(
        model_create_url,
        headers={"Content-Type": "application/json"},
        json={"from": LLM_MODEL},
    )
    response.raise_for_status()
    return (
        flask.jsonify(
            message="Model loaded successfully", model_name=LLM_MODEL
        ),
        200,
    )
  except requests.exceptions.RequestException as e:
    if e.response is not None and "TOOMANYREQUESTS" in e.response.text:
      return flask.jsonify(error="Rate Limit Exceeded. Can't load model"), 429
    return flask.jsonify(error=str(e)), 500


@app.route("/models")
def get_models():
  """Returns the list of models available in the LLM agent."""

  try:
    auth_req = google.auth.transport.requests.Request()
    id_token = google.oauth2.id_token.fetch_id_token(auth_req, LLM_URL)

    headers = {"Authorization": f"Bearer {id_token}"}
    model_list_url = f"{LLM_URL}/engines/llama.cpp/v1/models"
    response = requests.get(model_list_url, headers=headers)
    response.raise_for_status()
    return flask.jsonify(response.json())
  except requests.exceptions.RequestException as e:
    return flask.jsonify(error=f"{str(e)}"), 500


@app.route("/env")
def get_env_vars():
  """Returns the LLM environment variables as a JSON object."""

  return flask.jsonify(
      LLM_URL=LLM_URL,
      LLM_MODEL=LLM_MODEL,
  )


@app.route("/hello")
def hello():
  return "Hello World\n"


@app.route("/admin", methods=["GET", "POST"])
def admin():
  if flask.request.method == "POST":
    password = flask.request.form.get("password")
    with open("/run/secrets/admin_password", "r") as f:
      correct_password = f.read().strip()
    if password == correct_password:
      history_data = get_all_history()
      return flask.render_template("admin.html", history_data=history_data)
    else:
      return flask.render_template("login.html", error="Invalid password")
  return flask.render_template("login.html")


@app.route("/delete_all_history", methods=["POST"])
def delete_all_history():
  if os.path.exists(HISTORY_DIR):
    for filename in os.listdir(HISTORY_DIR):
      if filename.endswith(".json"):
        os.remove(os.path.join(HISTORY_DIR, filename))
  history_data = get_all_history()
  return flask.render_template("admin.html", history_data=history_data)


def get_all_history():
  history_data = {}
  if os.path.exists(HISTORY_DIR):
    for filename in os.listdir(HISTORY_DIR):
      if filename.endswith(".json"):
        username = filename[:-5]
        with open(os.path.join(HISTORY_DIR, filename), "r") as f:
          history_data[username] = json.load(f)
  return history_data


if __name__ == "__main__":
  app.run(debug=True, host="0.0.0.0", port=8080)
