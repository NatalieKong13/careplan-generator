import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'dev-secret-key-change-in-production'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'corsheaders',
    'careplan',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
]

CORS_ALLOW_ALL_ORIGINS = True

ROOT_URLCONF = 'config.urls'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'careplan',
        'USER': 'careplan',
        'PASSWORD': 'careplan123',
        'HOST': 'db',
        'PORT': '5432',
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# API Keys
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# Redis URL
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# ===================
# Celery 配置
# ===================
CELERY_BROKER_URL = REDIS_URL  # 使用 Redis 作为消息代理
CELERY_RESULT_BACKEND = REDIS_URL  # 使用 Redis 存储任务结果
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
USE_MOCK_LLM = os.environ.get('USE_MOCK_LLM', 'false').lower() == 'true'