from django.urls import path
from api.views import k8s_cd
from django.conf.urls import url

urlpatterns = [
    url(r'^$',k8s_cd.index),
    path('cd/deployment',k8s_cd.Kubernetes_deploy.as_view()),
    path('cd/service/versions',k8s_cd.Service_version.as_view())
]



