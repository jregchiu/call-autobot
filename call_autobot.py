import os
from datetime import datetime
import pytz
from flask import Flask, request, redirect, session, url_for, render_template
from werkzeug.contrib.fixers import ProxyFix
import requests
from requests_oauthlib import OAuth2Session
from celery import Celery

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'dev')
app.wsgi_app = ProxyFix(app.wsgi_app)

rabbitmq_url = os.environ.get('CLOUDAMQP_URL', "amqp://localhost")
celery = Celery(__name__, broker=rabbitmq_url, broker_pool_limit=1)

client_id = os.environ['GITHUB_CLIENT_ID']
client_secret = os.environ['GITHUB_CLIENT_SECRET']
base_url = 'https://github.ugrad.cs.ubc.ca'
api_url = 'https://github.ugrad.cs.ubc.ca/api/v3/repos'
authorization_base_url = 'https://github.ugrad.cs.ubc.ca/login/oauth/authorize'
token_url = 'https://github.ugrad.cs.ubc.ca/login/oauth/access_token'

@app.route("/")
def index():
    '''
    Landing page when a user first visits Call Autobot. Either sets up the authentication flow to UBC CS Github or redirects to the scheduler
    '''
    if 'oauth_token' not in session:
        github = OAuth2Session(client_id=client_id, scope="repo")
        authorization_url, state = github.authorization_url(authorization_base_url)
        session['oauth_state'] = state
        return render_template("index.html", authorization_url=authorization_url)
    else:
        return redirect(url_for("schedule"))

@app.route("/callback", methods=["GET"])
def callback():
    '''
    Callback URL to handle fetching a token after a user authorizes Call Autobot with UBC CS Github. Redirects to the scheduler
    '''
    github = OAuth2Session(client_id, state=session['oauth_state'])
    token = github.fetch_token(token_url, client_secret=client_secret,
                               authorization_response=request.url)
    session['oauth_token'] = token
    return redirect(url_for('schedule'))

@app.route("/schedule", methods=["GET", "POST"])
def schedule():
    '''
    Scheduling page to get a user's commit, comment, and time to post it
    '''
    if 'oauth_token' not in session:
        return redirect(url_for("index"))

    if request.method == "GET":
        return render_template("schedule.html")
    else:
        # grab all the info from the form
        url = request.form['url']
        comment = request.form['comment']
        dt = request.form['datetime']
        token = session['oauth_token']

        # clean up the URL that the user submits
        url = url.replace(base_url, api_url)
        url = url.replace('commit', 'commits')
        url = url + '/comments'

        # clean up the datetime so that it's UTC
        naive_dt = datetime.strptime(dt, '%Y-%m-%dT%H:%M')
        vancouver = pytz.timezone('America/Vancouver')
        vancouver_dt = vancouver.localize(naive_dt)
        utc_dt = vancouver_dt.astimezone(pytz.utc)

        # schedule the call to autobot
        call_autobot.apply_async(args=(token, url, comment), eta=utc_dt)
        flash('Successfully scheduled your call!')
        return render_template("schedule.html")

@celery.task
def call_autobot(token, url, body):
    '''
    Represents the call to autobot, to be performed by a Celery worker
    '''
    github = OAuth2Session(client_id, token=token)
    github.post(url, json={"body": body})
