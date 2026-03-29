"""
Celery 配置文件

Celery 是一个分布式任务队列，用于异步执行任务。
"""
import os
from celery import Celery

# 设置 Django settings 模块
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# 创建 Celery 应用
app = Celery('careplan')

# 从 Django settings 中读取 CELERY_ 开头的配置
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动发现所有 app 下的 tasks.py 文件
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """测试任务"""
    print(f'Request: {self.request!r}')
