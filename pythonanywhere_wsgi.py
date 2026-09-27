"""
PythonAnywhere WSGI Configuration Template for MapúaQ
Username: justinovate

To deploy MapúaQ on PythonAnywhere:
1. Open the 'Web' tab in your PythonAnywhere dashboard.
2. Click on the WSGI configuration file link (e.g., /var/www/justinovate_pythonanywhere_com_wsgi.py).
3. Replace its contents with this file or import this module.
"""

import sys
import os

# 1. Enforce absolute project directory path
project_home = '/home/justinovate/cpe106l-4_finalproject'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# 2. Change current working directory to project root
os.chdir(project_home)

# 3. Load environment variables from .env if present
from dotenv import load_dotenv
dotenv_path = os.path.join(project_home, '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# 4. Import Flask app object as WSGI application entry point
from app import app as application
