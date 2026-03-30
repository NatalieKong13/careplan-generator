from django.urls import path
from . import views

urlpatterns = [
    path('careplan/', views.create_order_and_generate_careplan, name='create_careplan'),
    path('careplan/<int:careplan_id>/', views.get_careplan, name='get_careplan'),
    path('careplan/<int:careplan_id>/status/', views.get_careplan_status, name='get_careplan'),
    path('careplan/<int:careplan_id>/download/', views.download_careplan_pdf, name='download_careplan'),
    path('careplans/', views.list_careplans, name='list_careplans'),
    path('careplans/search/', views.search_careplans, name='search_careplans'),
    path('careplan/json/', views.order_from_json, name='create_careplan_json'),
    path('careplan/xml/', views.order_from_xml, name='create_careplan_xml'),
]
