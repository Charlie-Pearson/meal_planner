#!/usr/bin/env python3
import os
import subprocess
import traceback

REPO_DIR = '/home/charlie1234pearson/mysite'
WSGI_FILE = '/var/www/charlie1234pearson_pythonanywhere_com_wsgi.py'

def update():
    os.chdir(REPO_DIR)
    
    # Stash any local changes
    subprocess.run(['git', 'stash', '--include-untracked'], check=True)
    
    # Fetch the latest updates
    subprocess.run(['git', 'fetch'], check=True)
    
    # Check if updates exist
    local_head = subprocess.check_output(['git', 'rev-parse', 'HEAD']).strip()
    remote_head = subprocess.check_output(['git', 'rev-parse', 'origin/main']).strip()

    if local_head != remote_head:
        print("New updates found. Pulling updates.")
        subprocess.run(['git', 'checkout', 'main'], check=True)
        subprocess.run(['git', 'pull', 'origin', 'main'], check=True)
        subprocess.run(['touch', WSGI_FILE], check=True)
        print("Update successful.")
    else:
        print("No updates found.")

    # Re-apply stashed changes (if any)
    # If there’s nothing to pop, this will exit quietly
    subprocess.run(['git', 'stash', 'pop'], check=False)

try:
    update()
except Exception as exc:
    print("Update failed:", exc)
    traceback.print_exc()


