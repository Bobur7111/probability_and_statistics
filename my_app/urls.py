from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),

    path('upload/', views.upload_file, name='upload_file'),
    path('mapping/', views.mapping, name='mapping'),
    path('result/', views.result_view, name='result'),

    path('distribution-calculator/', views.distribution_calculator, name='distribution_calculator'),
    path('problem-solver/', views.problem_solver, name='problem_solver'),

    path('trainer/', views.trainer_home, name='trainer_home'),
    path('trainer/<str:topic_slug>/', views.trainer_topic, name='trainer_topic'),
]