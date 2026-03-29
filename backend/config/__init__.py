# 这个文件确保 Django 启动时加载 Celery
from .celery import app as celery_app

__all__ = ('celery_app',)
