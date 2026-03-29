"""
Worker 脚本 - 从 Redis 队列拉取任务，调用 LLM，存入数据库

运行方式:
    docker compose exec backend python worker.py

这个脚本会:
1. 从 Redis 队列 (careplan:queue) 拉取一个 careplan_id
2. 从数据库读取对应的 CarePlan 和 Order 信息
3. 调用 LLM 生成 Care Plan 内容
4. 把结果存回数据库
5. 重复以上步骤，直到队列为空
"""

import os
import sys
import json
import time
import django
import redis

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# 现在可以导入 Django 的东西了
from django.conf import settings
import anthropic
from careplan.models import CarePlan

# Redis 配置
REDIS_URL = settings.REDIS_URL
CAREPLAN_QUEUE = 'careplan:queue'


def get_redis_client():
    return redis.from_url(REDIS_URL)


def call_llm_for_careplan(patient, medication_name, diagnosis):
    """调用 Anthropic Claude 生成 care plan"""
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    
    prompt = f"""You are a clinical pharmacist creating a care plan for a CVS pharmacy.

Patient: {patient.first_name} {patient.last_name}, DOB: {patient.dob}
Medication: {medication_name}
Diagnosis: {diagnosis}

Generate a care plan with these 4 sections. Be specific and clinical.

Respond ONLY with valid JSON, no other text:
{{
    "problem_list": "List the clinical problems...",
    "goals": "List the therapeutic goals...",
    "pharmacist_interventions": "List specific pharmacist interventions...",
    "monitoring_plan": "List parameters to monitor..."
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    
    return json.loads(response.content[0].text)


def process_one_task(careplan_id):
    """处理单个任务"""
    print(f"[Worker] Processing CarePlan ID: {careplan_id}")
    
    try:
        # 1. 从数据库获取 CarePlan
        careplan = CarePlan.objects.select_related('order__patient').get(id=careplan_id)
        
        # 2. 检查状态，只处理 pending 的
        if careplan.status != 'pending':
            print(f"[Worker] CarePlan {careplan_id} is not pending (status={careplan.status}), skipping")
            return
        
        # 3. 更新状态为 processing
        careplan.status = 'processing'
        careplan.save()
        print(f"[Worker] CarePlan {careplan_id} status -> processing")
        
        # 4. 获取相关数据
        order = careplan.order
        patient = order.patient
        
        # 5. 调用 LLM
        print(f"[Worker] Calling LLM for CarePlan {careplan_id}...")
        result = call_llm_for_careplan(patient, order.medication_name, order.diagnosis)
        
        # 6. 保存结果到数据库
        careplan.problem_list = result['problem_list']
        careplan.goals = result['goals']
        careplan.pharmacist_interventions = result['pharmacist_interventions']
        careplan.monitoring_plan = result['monitoring_plan']
        careplan.status = 'completed'
        careplan.save()
        
        print(f"[Worker] CarePlan {careplan_id} status -> completed ✓")
        
    except CarePlan.DoesNotExist:
        print(f"[Worker] CarePlan {careplan_id} not found in database")
    except Exception as e:
        print(f"[Worker] Error processing CarePlan {careplan_id}: {e}")
        # 更新状态为 failed
        try:
            careplan = CarePlan.objects.get(id=careplan_id)
            careplan.status = 'failed'
            careplan.error_message = str(e)
            careplan.save()
            print(f"[Worker] CarePlan {careplan_id} status -> failed")
        except:
            pass


def run_worker():
    """主循环 - 从 Redis 队列拉取任务并处理"""
    print("=" * 50)
    print("[Worker] Starting Care Plan Worker...")
    print(f"[Worker] Redis URL: {REDIS_URL}")
    print(f"[Worker] Queue name: {CAREPLAN_QUEUE}")
    print("=" * 50)
    
    redis_client = get_redis_client()
    
    # 检查 Redis 连接
    try:
        redis_client.ping()
        print("[Worker] Redis connection OK")
    except Exception as e:
        print(f"[Worker] Redis connection failed: {e}")
        sys.exit(1)
    
    # 主循环
    while True:
        # 从队列左边取出一个任务 (LPOP)
        task = redis_client.lpop(CAREPLAN_QUEUE)
        
        if task is None:
            # 队列为空，等待 2 秒再检查
            print("[Worker] Queue empty, waiting...")
            time.sleep(2)
            continue
        
        # task 是 bytes，需要解码
        careplan_id = int(task.decode('utf-8'))
        
        # 处理任务
        process_one_task(careplan_id)
        
        print("-" * 30)


if __name__ == '__main__':
    run_worker()
