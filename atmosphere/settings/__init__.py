"""
Settings for atmosphere project.

"""
from __future__ import absolute_import
from datetime import timedelta
from uuid import UUID
import logging
import sys

from dateutil.relativedelta import relativedelta
from celery.schedules import crontab
import os
import os.path
import threepio
import atmosphere
from kombu import Exchange, Queue


# Debug Mode
DEBUG = True
TEMPLATE_DEBUG = DEBUG

# Enforcing mode -- True, when in production (Debug=False)
ENFORCING = not DEBUG

SETTINGS_ROOT = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                            '../..'))
APPEND_SLASH = False
SERVER_URL = 'https://MYHOSTNAMEHERE'
# IF on the root directory, this should be BLANK, else: /path/to/web (NO
# TRAILING /)
REDIRECT_URL = ''

# Hosts/domain names that are valid for this site; required if DEBUG is False
# See https://docs.djangoproject.com/en/1.5/ref/settings/#allowed-hosts
ALLOWED_HOSTS = [unicode(SERVER_URL.replace('https://', ''))]

# NOTE: first admin will be sender of atmo emails.
ADMINS = (
    ('Atmosphere Admin', 'atmo@iplantcollaborative.org'),
    ('Steven Gregory', 'esteve@iplantcollaborative.org'),
    ('Atmosphere Alerts', 'atmo-alerts@iplantcollaborative.org'),
)


# Required to send RequestTracker emails
ATMO_SUPPORT = ADMINS
ATMO_DAEMON = (("Atmosphere Daemon", "atmo-alerts@iplantcollaborative.org"),)

# Django uses this one..
MANAGERS = ADMINS

DATABASES = {
    'default': {
        'NAME': 'atmosphere',
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'USER': 'atmo_app',
        'PASSWORD': 'atmosphere',
        'HOST': 'localhost',
        'PORT': '5432'
    },
}
INSTALLED_APPS = (
    # contrib apps
    'django.contrib.auth',
    'django.contrib.admin',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.staticfiles',

    # 3rd party apps
    'rest_framework',
    'django_filters',

    'djcelery',
    'corsheaders',
    # 3rd party apps (Development Only)
    #'django_jenkins',
    #'sslserver',

    # iPlant apps
    'rtwo',

    # atmosphere apps
    'api',
    'allocation',
    'authentication',
    'service',
    'core',
)

TIME_ZONE = 'America/Phoenix'

LANGUAGE_CODE = 'en-us'

SITE_ID = 1

USE_I18N = True

USE_TZ = True

# Atmosphere Time Allocation settings
FIXED_WINDOW = relativedelta(day=1, months=1)

# To load images for 404 page
MEDIA_ROOT = os.path.join(PROJECT_ROOT, 'resources/')
MEDIA_URL = '/resources/'

# URL prefix for admin media -- CSS, JavaScript and images. Make sure to use a
# trailing slash.
# Examples: 'http://foo.com/media/', '/media/'.
STATIC_ROOT = os.path.join(PROJECT_ROOT, 'static/')
STATIC_URL = '/static/'

# This key however should stay the same, and be shared with all Atmosphere
ATMOSPHERE_NAMESPACE_UUID = UUID("40227dff-dedf-469c-a9f8-1953a7372ac1")

MIDDLEWARE_CLASSES = (
    'corsheaders.middleware.CorsMiddleware',
    # corsheaders.middleware.CorsMiddleware Must be ahead of
    # configuration CommonMiddleware for an edge case.

    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'atmosphere.slash_middleware.RemoveSlashMiddleware',
)

ROOT_URLCONF = 'atmosphere.urls'

# Python dotted path to the WSGI application used by Django's runserver.
WSGI_APPLICATION = 'atmosphere.wsgi.application'

TEMPLATE_DIRS = (
    os.path.join(PROJECT_ROOT, 'templates'),
)

AUTH_USER_MODEL = 'core.AtmosphereUser'

AUTHENTICATION_BACKENDS = (
    # For Token-Access
    'authentication.authBackends.AuthTokenLoginBackend',
    # For Web-Access
    'authentication.authBackends.CASLoginBackend',
    'authentication.authBackends.SAMLLoginBackend',
    # For Service-Access
    'authentication.authBackends.LDAPLoginBackend',
)

# django-cors-headers
CORS_ORIGIN_ALLOW_ALL = True
CORS_ORIGIN_WHITELIST = None

# The age of session cookies, in seconds.
# http://docs.djangoproject.com/en/dev/ref/settings/
# http://docs.djangoproject.com/en/dev/topics/http/sessions/
# Now I set sessio cookies life time = 3600 seconds = 1 hour
SESSION_EXPIRE_AT_BROWSER_CLOSE = True


# ATMOSPHERE APP CONFIGS
INSTANCE_SERVICE_URL = SERVER_URL + REDIRECT_URL + '/api/notification/'
API_SERVER_URL = SERVER_URL + REDIRECT_URL + '/resources/v1'
AUTH_SERVER_URL = SERVER_URL + REDIRECT_URL + '/auth'
INIT_SCRIPT_PREFIX = '/init_files/'
DEPLOY_SERVER_URL = SERVER_URL.replace("https", "http")

# Stops 500 errors when logs are missing.
# NOTE: If the permissions are wrong, this won't help


def check_and_touch(file_path):
    if os.path.exists(file_path):
        return
    parent_dir = os.path.dirname(file_path)
    if not os.path.isdir(parent_dir):
        os.makedirs(parent_dir)
    #'touch' the file.
    with open(file_path, 'a'):
        os.utime(file_path, None)
    return

# logging
LOGGING_LEVEL = logging.DEBUG
DEP_LOGGING_LEVEL = logging.INFO  # Logging level for dependencies.

# Filenames


def create_log_path(filename):
    return os.path.abspath(
        os.path.join(
            os.path.dirname(atmosphere.__file__),
            '..',
            'logs',
            filename))

LOG_FILENAME = create_log_path("atmosphere.log")
API_LOG_FILENAME = create_log_path("atmosphere_api.log")
AUTH_LOG_FILENAME = create_log_path('atmosphere_auth.log')
EMAIL_LOG_FILENAME = create_log_path('atmosphere_email.log')
STATUS_LOG_FILENAME = create_log_path('atmosphere_status.log')
DEPLOY_LOG_FILENAME = create_log_path('atmosphere_deploy.log')

check_and_touch(LOG_FILENAME)
check_and_touch(API_LOG_FILENAME)
check_and_touch(AUTH_LOG_FILENAME)
check_and_touch(EMAIL_LOG_FILENAME)
check_and_touch(STATUS_LOG_FILENAME)
check_and_touch(DEPLOY_LOG_FILENAME)

#####
# FileHandler
#####
# Default filehandler will use 'LOG_FILENAME'
api_fh = logging.FileHandler(API_LOG_FILENAME)
auth_fh = logging.FileHandler(AUTH_LOG_FILENAME)
email_fh = logging.FileHandler(EMAIL_LOG_FILENAME)
status_fh = logging.FileHandler(STATUS_LOG_FILENAME)
deploy_fh = logging.FileHandler(DEPLOY_LOG_FILENAME)
####
# Formatters
####
# Logger initialization
# NOTE: The format for status_logger is defined in the message ONLY!
# timestamp, user, instance_alias, machine_alias, size_alias, status_update
# create formatter and add it to the handlers
base_format = '%(message)s'
formatter = logging.Formatter(base_format)
status_fh.setFormatter(formatter)

####
# Logger Initialization
####
threepio.initialize("atmosphere",
                    log_filename=LOG_FILENAME,
                    app_logging_level=LOGGING_LEVEL,
                    dep_logging_level=DEP_LOGGING_LEVEL)
# Add handler to the remaining loggers
threepio.status_logger = threepio\
        .initialize("atmosphere_status",
                    handlers=[status_fh],
                    app_logging_level=LOGGING_LEVEL,
                    dep_logging_level=DEP_LOGGING_LEVEL,
                    global_logger=False,
                    format=base_format)
threepio.email_logger = threepio\
        .initialize("atmosphere_email",
                    handlers=[email_fh],
                    log_filename=LOG_FILENAME,
                    app_logging_level=LOGGING_LEVEL,
                    dep_logging_level=DEP_LOGGING_LEVEL,
                    global_logger=False)
threepio.api_logger = threepio\
        .initialize("atmosphere_api",
                    handlers=[api_fh],
                    log_filename=LOG_FILENAME,
                    app_logging_level=LOGGING_LEVEL,
                    dep_logging_level=DEP_LOGGING_LEVEL,
                    global_logger=False)
threepio.auth_logger = threepio\
        .initialize("atmosphere_auth",
                    handlers=[auth_fh],
                    log_filename=LOG_FILENAME,
                    app_logging_level=LOGGING_LEVEL,
                    dep_logging_level=DEP_LOGGING_LEVEL,
                    global_logger=False)
threepio.deploy_logger = threepio\
        .initialize("atmosphere_deploy",
                    handlers=[deploy_fh],
                    log_filename=DEPLOY_LOG_FILENAME,
                    app_logging_level=LOGGING_LEVEL,
                    dep_logging_level=DEP_LOGGING_LEVEL,
                    global_logger=False)


# Directory that the app (One level above this file) exists
# (TEST if this is necessary)
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if 'PYTHONPATH' in os.environ:
    os.environ['PYTHONPATH'] = root_dir + ':' + os.environ['PYTHONPATH']
else:
    os.environ['PYTHONPATH'] = root_dir


# Redirect stdout to stderr.
sys.stdout = sys.stderr

# REST FRAMEWORK
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': (
        # Included Renderers
        'rest_framework.renderers.JSONRenderer',
        'rest_framework_jsonp.renderers.JSONPRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
        'rest_framework_yaml.renderers.YAMLRenderer',
        'rest_framework_xml.renderers.XMLRenderer',
        # Our Renderers
        'api.renderers.PNGRenderer',
        'api.renderers.JPEGRenderer',
    ),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'authentication.token.JWTTokenAuthentication',
        'authentication.token.OAuthTokenAuthentication',
        'authentication.token.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,                 # Default to 20
    # Allow client to override, using `?page_size=xxx`.
    'PAGINATE_BY_PARAM': 'page_size',
    'DEFAULT_FILTER_BACKENDS': (
        'rest_framework.filters.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter'
    )
}
LOGIN_REDIRECT_URL = "/api/v1"


# CASLIB
SERVER_URL = SERVER_URL + REDIRECT_URL
CAS_SERVER = 'https://auth.iplantcollaborative.org'
SERVICE_URL = SERVER_URL + '/CAS_serviceValidater?sendback='\
    + REDIRECT_URL + '/application/'
PROXY_URL = SERVER_URL + '/CAS_proxyUrl'
PROXY_CALLBACK_URL = SERVER_URL + '/CAS_proxyCallback'

# Chromogenic
LOCAL_STORAGE = "/storage"

# pyes secrets
ELASTICSEARCH_HOST = SERVER_URL
ELASTICSEARCH_PORT = 9200

# Django-Celery secrets
BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
# Related to Broker and ResultBackend
REDIS_CONNECT_RETRY = True
# General Celery Settings
CELERY_ENABLE_UTC = True
CELERYD_PREFETCH_MULTIPLIER = 1
CELERY_TIMEZONE = TIME_ZONE
CELERY_SEND_EVENTS = True
CELERY_TASK_RESULT_EXPIRES = 3 * 60 * 60  # Store results for 3 hours
CELERYD_MAX_TASKS_PER_CHILD = 10
CELERYD_LOG_FORMAT = "[%(asctime)s: %(name)s-%(levelname)s"\
    "/%(processName)s [PID:%(process)d]"\
    " @ %(pathname)s on %(lineno)d] %(message)s"
CELERYD_TASK_LOG_FORMAT = "[%(asctime)s: %(name)s-%(levelname)s"\
    "/%(processName)s [PID:%(process)d]"\
    " [%(task_name)s(%(task_id)s)] "\
    "@ %(pathname)s on %(lineno)d] %(message)s"
# To use Manual Routing:
# - 1. Create an Exchange,
# - 2. Create a Queue,
# - 3. Bind Queue to Exchange
CELERY_QUEUES = (
    Queue(
        'default', Exchange('default'), routing_key='default'), Queue(
            'email', Exchange('default'), routing_key='email.sending'), Queue(
                'ssh_deploy', Exchange('deployment'), routing_key='long.deployment'), Queue(
                    'fast_deploy', Exchange('deployment'), routing_key='short.deployment'), Queue(
                        'imaging', Exchange('imaging'), routing_key='imaging'), Queue(
                            'periodic', Exchange('periodic'), routing_key='periodic'), )
CELERY_DEFAULT_QUEUE = 'default'
CELERY_DEFAULT_ROUTING_KEY = "default"
CELERY_DEFAULT_EXCHANGE = 'default'
CELERY_DEFAULT_EXCHANGE_TYPE = 'direct'
# NOTE: We are Using atmosphere's celery_router as an interim solution.
CELERY_ROUTES = ('atmosphere.celery_router.CloudRouter', )
# # Django-Celery Development settings
# CELERY_EAGER_PROPAGATES_EXCEPTIONS = True  # Issue #75

import djcelery
djcelery.setup_loader()

# Related to Celerybeat
CELERYBEAT_CHDIR = PROJECT_ROOT

CELERYBEAT_SCHEDULE = {
    "check_image_membership": {
        "task": "check_image_membership",
        "schedule": timedelta(minutes=60),
        "options": {"expires": 10 * 60, "time_limit": 2 * 60}
    },
    "monitor_machines": {
        "task": "monitor_machines",
        # Every day of the week @ 1am
        "schedule": crontab(hour="1", minute="0", day_of_week="*"),
        "options": {"expires": 10 * 60, "time_limit": 10 * 60}
    },
    "monitor_sizes": {
        "task": "monitor_sizes",
        "schedule": timedelta(minutes=30),
        "options": {"expires": 10 * 60, "time_limit": 10 * 60}
    },
    "monitor_instances": {
        "task": "monitor_instances",
        "schedule": timedelta(minutes=15),
        "options": {"expires": 10 * 60, "time_limit": 10 * 60}
    },
    "clear_empty_ips": {
        "task": "clear_empty_ips",
        "schedule": timedelta(minutes=120),
        "options": {"expires": 60 * 60}
    },
    "monthly_allocation_reset": {
        "task": "monthly_allocation_reset",
        # Every month, first of the month.
        "schedule": crontab(0, 0, day_of_month=1, month_of_year="*"),
        "options": {"expires": 5 * 60, "time_limit": 5 * 60}
    },
    "remove_empty_networks": {
        "task": "remove_empty_networks",
        # Every two hours.. midnight/2am/4am/...
        "schedule": crontab(hour="*/2", minute="0", day_of_week="*"),
        "options": {"expires": 5 * 60, "time_limit": 5 * 60}
    },
}

#     # Django-Celery Development settings
# CELERY_EAGER_PROPAGATES_EXCEPTIONS = True  # Issue #75

"""
For generating a unique SECRET_KEY -- Used by Django in various ways.
"""
# This Method will generate SECRET_KEY and write it to file..


def generate_secret_key(secret_key_path):
    from django.utils.crypto import get_random_string
    from datetime import datetime
    chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
    secret_value = get_random_string(50, chars)
    comment_block = "\"\"\"\nThis file was Auto-Generated on %s\n\"\"\"\n" % datetime.now()
    with open(secret_key_path, "w") as key_file:
        key_file.write(comment_block)
        key_file.write("SECRET_KEY=\"%s\"\n" % secret_value)

# This import will Use an existing SECRET_KEY, or Generate your SECRET_KEY
# if it doesn't exist yet.
try:
    from .secret_key import SECRET_KEY
except ImportError:
    SETTINGS_DIR = os.path.abspath(os.path.dirname(__file__))
    generate_secret_key(os.path.join(SETTINGS_DIR, 'secret_key.py'))
    try:
        from .secret_key import SECRET_KEY
    except ImportError:
        raise Exception(
            "__init__.py could not generate a SECRET_KEY in secret_key.py")

"""
Import local settings specific to the server, and secrets not checked into Git.
"""
from atmosphere.settings.local import *
