import os
from datetime import datetime
from pytz import timezone
import pytz
from flask import Flask, request, redirect, session, url_for, render_template
from werkzeug.contrib.fixers import ProxyFix
from requests_oauthlib import OAuth2, OAuth2Session
from celery import Celery

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'dev')
app.wsgi_app = ProxyFix(app.wsgi_app)

rabbitmq_url = os.environ.get('CLOUDAMQP_URL', "amqp://localhost")
celery = Celery(__name__, broker=rabbitmq_url)

client_id = os.environ['GITHUB_CLIENT_ID']
client_secret = os.environ['GITHUB_CLIENT_SECRET']
base_url = 'https://github.ugrad.cs.ubc.ca'
api_url = 'https://github.ugrad.cs.ubc.ca/api/v3'
authorization_base_url = 'https://github.ugrad.cs.ubc.ca/login/oauth/authorize'
token_url = 'https://github.ugrad.cs.ubc.ca/login/oauth/access_token'

@app.route("/")
def index():
    if 'oauth_key' not in session:
        github = OAuth2Session(client_id=client_id, scope="repo")
        authorization_url, state = github.authorization_url(authorization_base_url)
        session['oauth_state'] = state
        return render_template("index.html", authorization_url=authorization_url)
    else:
        return redirect(url_for("schedule"))

@app.route("/callback", methods=["GET"])
def callback():
    github = OAuth2Session(client_id, state=session['oauth_state'])
    token = github.fetch_token(token_url, client_secret=client_secret,
                               authorization_response=request.url)
    session['oauth_token'] = token
    return redirect(url_for('schedule'))

@app.route("/schedule", methods=["GET", "POST"])
def schedule():
    if 'oauth_key' not in session:
        return redirect(url_for("index"))

    if request.method == "GET":
        return render_template("schedule.html")
    else:
        url = request.form['url']
        comment = request.form['comment']
        dt = request.form['datetime']
        token = session['oauth_token']

        url = url.replace(base_url, api_url)
        naive_dt = datetime.strptime(dt, '%Y-%m-%dT%H:%M')
        vancouver = timezone('America/Vancouver')
        vancouver_dt = vancouver.localize(naive_dt)
        utc_dt = vancouver_dt.astimezone(pytz.utc)

        call_autobot.apply_async(args=(token, url, comment), eta=utc_dt)

@celery.task
def call_autobot(token, url, body):
    github = OAuth2(client_id, token=token)
    github.post(url, data={"body": body})
