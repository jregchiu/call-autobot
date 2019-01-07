web: gunicorn call_autobot:app
worker: celery worker -A call_autobot:celery -l info
