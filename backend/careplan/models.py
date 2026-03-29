from django.db import models

class Patient(models.Model):
    mrn = models.CharField(max_length=50)  # Medical Record Number
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    dob = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

class Provider(models.Model):
    npi = models.CharField(max_length=20)  # National Provider Identifier
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

class Order(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE)
    medication_name = models.CharField(max_length=200)
    diagnosis = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

class CarePlan(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Care Plan 输出的4个必须字段
    problem_list = models.TextField(blank=True)
    goals = models.TextField(blank=True)
    pharmacist_interventions = models.TextField(blank=True)
    monitoring_plan = models.TextField(blank=True)
    
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
