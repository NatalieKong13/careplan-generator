"""
Celery 异步任务

这个文件定义了所有的异步任务。
Celery 会自动发现这个文件（因为 autodiscover_tasks）。
"""
import json
from celery import shared_task
from django.conf import settings
from .llm.factory import get_llm_service


@shared_task(
    bind=True,
    max_retries=3,  # 最多重试 3 次
    default_retry_delay=5,  # 默认重试延迟 5 秒（会被指数退避覆盖）
)
def generate_careplan_task(self, careplan_id: int):
    """
    异步生成 Care Plan 的任务
    
    参数:
        self: Celery task 实例（bind=True 时自动传入）
        careplan_id: CarePlan 的数据库 ID
    
    重试策略:
        - 最多重试 3 次
        - 使用指数退避: 第1次等5秒, 第2次等10秒, 第3次等20秒
    """
    # 在函数内部导入 Model，避免循环导入
    from careplan.models import CarePlan
    
    print(f"[Celery Task] Processing CarePlan ID: {careplan_id}")
    print(f"[Celery Task] Attempt: {self.request.retries + 1} / {self.max_retries + 1}")
    
    try:
        # 1. 从数据库获取 CarePlan
        careplan = CarePlan.objects.select_related('order__patient').get(id=careplan_id)
        
        # 2. 检查状态
        if careplan.status not in ['pending', 'processing']:
            print(f"[Celery Task] CarePlan {careplan_id} status is {careplan.status}, skipping")
            return {'status': 'skipped', 'reason': f'status is {careplan.status}'}
        
        # 3. 更新状态为 processing
        careplan.status = 'processing'
        careplan.save()
        print(f"[Celery Task] CarePlan {careplan_id} status -> processing")
        
        # 4. 获取相关数据
        order = careplan.order
        patient = order.patient
        
        # 5. 调用 LLM
        print(f"[Celery Task] Calling LLM for CarePlan {careplan_id}...")
        result = call_llm_for_careplan(patient, order.medication_name, order.diagnosis)
        
        # 6. 保存结果到数据库
        careplan.problem_list = result['problem_list']
        careplan.goals = result['goals']
        careplan.pharmacist_interventions = result['pharmacist_interventions']
        careplan.monitoring_plan = result['monitoring_plan']
        careplan.status = 'completed'
        careplan.save()
        
        print(f"[Celery Task] CarePlan {careplan_id} status -> completed ✓")
        return {'status': 'completed', 'careplan_id': careplan_id}
        
    except CarePlan.DoesNotExist:
        print(f"[Celery Task] CarePlan {careplan_id} not found")
        return {'status': 'error', 'reason': 'not found'}
        
    except Exception as e:
        print(f"[Celery Task] Error: {e}")
        
        # 计算指数退避延迟: 5, 10, 20 秒
        retry_delay = 5 * (2 ** self.request.retries)
        
        # 如果还有重试次数，就重试
        if self.request.retries < self.max_retries:
            print(f"[Celery Task] Retrying in {retry_delay} seconds...")
            raise self.retry(exc=e, countdown=retry_delay)
        
        # 重试次数用完，标记为失败
        try:
            careplan = CarePlan.objects.get(id=careplan_id)
            careplan.status = 'failed'
            careplan.error_message = str(e)
            careplan.save()
            print(f"[Celery Task] CarePlan {careplan_id} status -> failed")
        except:
            pass
        
        return {'status': 'failed', 'error': str(e)}


def call_llm_for_careplan(patient, medication_name, diagnosis):
    """根据配置，调用真实 LLM 或 Mock"""
    if settings.USE_MOCK_LLM:
        return mock_llm_for_careplan(patient, medication_name, diagnosis)
    else:
        return real_llm_for_careplan(patient, medication_name, diagnosis)


def mock_llm_for_careplan(patient, medication_name, diagnosis):
    """Mock LLM：直接返回假数据，不调用 API，用于开发和测试"""
    import time
    print(f"[MOCK LLM] Simulating LLM call for {patient.first_name} {patient.last_name}...")
    time.sleep(3)  # 模拟真实 LLM 的延迟，测试 Polling 用
    print(f"[MOCK LLM] Done.")
    return {
        "problem_list": (
            f"[MOCK] 1. {diagnosis[:80]}...\n"
            "2. Risk of medication non-adherence\n"
            "3. Potential drug-drug interactions requiring monitoring"
        ),
        "goals": (
            f"[MOCK] 1. Patient will adhere to {medication_name} as prescribed\n"
            "2. Achieve target therapeutic outcomes within 3 months\n"
            "3. Patient will report any adverse effects promptly"
        ),
        "pharmacist_interventions": (
            f"[MOCK] 1. Counsel patient on proper use of {medication_name}\n"
            "2. Review medication list for interactions\n"
            "3. Provide written medication guide\n"
            "4. Schedule follow-up call in 2 weeks"
        ),
        "monitoring_plan": (
            "[MOCK] 1. Follow-up in 2 weeks via phone\n"
            "2. Lab review at next physician visit\n"
            "3. Monitor for adverse effects and report\n"
            "4. Reassess adherence at 1 month"
        ),
    }


def real_llm_for_careplan(patient, medication_name, diagnosis):
    

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

    llm = get_llm_service()        # 工厂函数决定用哪个 LLM
    response_text = llm.generate(prompt)  # 只调用 generate()，不知道底层是谁
    return json.loads(response_text)