#!/usr/bin/env python3
import os
import subprocess
import time

# Directory of the cloned GitHub repository on PythonAnywhere
REPO_DIR = '/home/charlie1234pearson/meal_planner'
# Full path to the WSGI file for the PythonAnywhere web app
WSGI_FILE = '/var/www/charlie1234pearson_pythonanywhere_com_wsgi.py'


def update():
    """Pull latest code from GitHub and reload the web app."""
    os.chdir(REPO_DIR)
    # Ensure we're on the main branch and get the latest changes
    subprocess.run(['git', 'checkout', 'main'], check=True)
    subprocess.run(['git', 'pull', 'origin', 'main'], check=True)
    # Touching the WSGI file triggers a reload on PythonAnywhere
    subprocess.run(['touch', WSGI_FILE], check=True)


while True:
    try:
        update()
        print("Updated repository and reloaded web app.")
    except Exception as exc:
        print("Update failed:", exc)
    # Wait 15 minutes before the next update
    time.sleep(15 * 60)

