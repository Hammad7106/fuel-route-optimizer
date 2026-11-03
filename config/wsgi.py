"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

# Load the place and station indexes before serving, so no request pays for
# it. With gunicorn --preload this runs once and workers share the memory.
from django.db import connections  # noqa: E402

from routing.services.trip_planner import warm_up  # noqa: E402

warm_up()
connections.close_all()  # Don't share the warm-up DB connection with forked workers.
