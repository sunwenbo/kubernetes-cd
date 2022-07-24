#!/bin/bash
git config --global http.sslVerify false
python /home/service/kubernetes-cd/manage.py runserver 0.0.0.0:8888