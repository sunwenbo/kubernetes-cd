#!/usr/bin/env python
# _#_ coding:utf-8 _*_

from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view
from api.scripts import kubernetes_op
from django.shortcuts import render

def index(request):
    return render(request,'api/index.html')

class Service_version(APIView):
    def get(self,request,format=None):
        response_data = {'status':'success','reason': "", 'result': []}
        request_data = request.query_params
        try:
            Servicename = request_data['service']
        except Exception as err:
            request_data['status'] = 'FAILED'
            request_data['info'] = err
            return Response(response_data,status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        v_status,v_data = kubernetes_op.Version_obtain(servicename=Servicename,env='prod')
        #response_data['result'] = v_data
        if v_status:
            response_data['result'] = v_data
            service_status = status.HTTP_200_OK
        else:
            response_data['status'] = 'FAILED'
            response_data['reason'] = v_data
            service_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response(response_data,status=service_status)

class Kubernetes_deploy(APIView):
    def get(self, request, format=None):
        response_data = {'status': 'SUCCESS'}
        request_data = request.query_params
        try:
            Servicename = request_data['service_name']
            Imageversion = request_data['commit_id']
            Cluster = request_data['cluster']
            Deploytype = request_data['deploy_type']
        except Exception as err:
            response_data['status'] = 'FAILED'
            response_data['info'] = err
            return Response(response_data,status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        deploy_check = kubernetes_op.Deploy_check(servicename=Servicename,imageversion=Imageversion,cluster=Cluster,deploytype=Deploytype)
        #check_status,check_data = kubernetes_op.Deploy_log(servicename=Servicename,imageversion=Imageversion,cluster=Cluster,deploytype=Deploytype)
        check_status,check_data = deploy_check.log_check()
        if check_status:
            response_data['info'] = check_data
        else:
            response_data['status'] = 'FAILED'
            response_data['info'] = check_data

            mta_url = 'http://mta.int.yidian-inc.com/send.json'
            error_proj = '<ERROR>: {cluster}; servcie:{servicename}; deploytype:{deploytype};describe：部署失败,请及时处理.'.format(cluster=Cluster,servicename=Servicename,deploytype=Deploytype)
            params_data = {
                "content": error_proj,
                "dst":"xiaoxiang",
                "alarmtype": "ding"
            }
            kubernetes_op.Request_Op(url=mta_url,params_data=params_data,req_type='POST')
            return Response(response_data,status=status.HTTP_200_OK)

        return Response(response_data,status=status.HTTP_200_OK)

    def post(self,request,formt=None):
        response_data = {'status': 'SUCCESS','info':'Helm task scheduled successfully'}
        dynamic_data = request.data
        try:
            Servicename = dynamic_data['service_name']
            Imageversion = str(dynamic_data['commit_id'])
            Cluster = dynamic_data['cluster']
            Deploytype = dynamic_data['deploy_type']
            ReplicaCount = int(dynamic_data['instance_number'])
            Currentversion = str(dynamic_data['current_version'])
        except Exception as err:
            response_data['status'] = 'FAILED'
            response_data['info'] = err
            return Response(response_data,status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        #判断是否为灰度发布
        if Deploytype == 'canary':
            if Currentversion == '0':
                response_data['info'] = 'New project, please use the formal release!'
                response_data['status'] = 'FAILED'
                return Response(response_data,status=status.HTTP_200_OK)
            # 调用axe api接口拿到创建deployment 相关的数据和状态
            v_status, v_data = kubernetes_op.Service_config(servicename=Servicename, cluster=Cluster)
            if v_status:
                curr_version = v_data['image']['tag']
                if Imageversion == curr_version:
                    #提交的版本和线上一致,无需发布
                    response_data['info'] = 'The submitted version is consistent with the online version.'
                    response_data['status'] = 'FAILED'
                    return Response(response_data,status=status.HTTP_200_OK)
            else:
                response_data['status'] = 'FAILED'
                response_data['info'] = v_data
                return Response(response_data,status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        helmop = kubernetes_op.Helm_template(servicename=Servicename, imageversion=Imageversion, cluster=Cluster, deploytype=Deploytype, replicaCount=ReplicaCount)
        #判断镜像是否存在
        # image_status = helmop.judge_image()
        image_status = {}
        image_status['status']  = 'True'

        if image_status['status'] == 'False':
            req_data = image_status['data']
            return Response(req_data,status=status.HTTP_200_OK)
        else:
            #判断服务status是否有状态，如果为None，直接返回报错，判断本地路径是否有项目目录，如果没有则执行git clone 将gitlab代码拉到本地。
            te_status,te_data = helmop.template_obtain()

            if te_status:
               #如果返回结果正常，开始进行发布
               re_status,re_data = helmop.helm_op()
               if not re_status:
                   response_data['status'] = 'FAILED'
                   response_data['info'] = re_data
            else:
               response_data['status'] = 'FAILED'
               response_data['info'] = te_data
               return Response(response_data,status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            response_data['info'] = te_data
            return Response(response_data,status=status.HTTP_200_OK)














