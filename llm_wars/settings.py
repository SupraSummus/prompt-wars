"""
Django settings for llm_wars project.

Generated by 'django-admin startproject' using Django 4.2.9.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""

from pathlib import Path

import environ
import sentry_sdk


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
env.read_env(str(BASE_DIR / '.env'))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env.str('DJANGO_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool('DJANGO_DEBUG', default=False)

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])


# Application definition
SILENCED_SYSTEM_CHECKS = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    'django.contrib.sites',
    'django_recaptcha',
    'django_goals',
    'django_scheduler.apps.DjangoSchedulerConfig',
    'django_object_actions',
    'users.apps.UsersConfig',
    'warriors.apps.WarriorsConfig',
    'labirynth.apps.LabirynthConfig',
    'stories.apps.StoriesConfig',
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    'whitenoise.middleware.WhiteNoiseMiddleware',
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "llm_wars.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "OPTIONS": {
            'loaders': [
                ('django.template.loaders.filesystem.Loader', [BASE_DIR / 'templates']),
                'django.template.loaders.app_directories.Loader',
                'djsfc.TemplateLoader',
            ],
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
            'builtins': [
                'djsfc',
            ],
        },
    },
]

WSGI_APPLICATION = "llm_wars.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    'default': {
        **env.db('DATABASE_URL'),
        'CONN_MAX_AGE': 600,  # 10 minutes
    },
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / 'static'
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


AUTH_USER_MODEL = 'users.User'
LOGIN_REDIRECT_URL = 'warrior_create'
LOGOUT_REDIRECT_URL = 'warrior_create'


OPENAI_API_KEY = env.str('OPENAI_API_KEY', default='')
ANTHROPIC_API_KEY = env.str('ANTHROPIC_API_KEY', default='')
VOYAGE_API_KEY = env.str('VOYAGE_API_KEY', default='')
GOOGLE_AI_API_KEY = env.str('GOOGLE_AI_API_KEY', default='')

# recaptcha (default are disclosed testing keys)
RECAPTCHA_PUBLIC_KEY = env.str('RECAPTCHA_PUBLIC_KEY', '6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI')
RECAPTCHA_PRIVATE_KEY = env.str('RECAPTCHA_PRIVATE_KEY', '6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe')
SILENCED_SYSTEM_CHECKS.append('django_recaptcha.recaptcha_test_key_error')


if SENTRY_DSN := env.str('SENTRY_DSN', default=''):
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.01,
    )


# set none to select site based on request domain
SITE_ID = env.int('SITE_ID', default=None)


# enforce https traffic
FORCE_HTTPS = env.bool('FORCE_HTTPS', default=True)
if FORCE_HTTPS:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = env.list('SECURE_PROXY_SSL_HEADER')


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django_goals': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'django_scheduler': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'warriors': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
    'formatters': {
        'verbose': {
            'format': 'pid={process:d} {name} {levelname} {message}',
            'style': '{',
        },
    },
}

ENABLE_DEBUG_TOOLBAR = env.bool('ENABLE_DEBUG_TOOLBAR', default=False)
if ENABLE_DEBUG_TOOLBAR:
    INSTALLED_APPS.append('debug_toolbar')
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
    INTERNAL_IPS = ['127.0.0.1']
