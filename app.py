# api/index.py

from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Hello, Vercel!"

@app.route("/api")
def api():
    return "Hello, API!"

@app.route("/turtle")
def turtle():
    return "Hello, Turtle!"
