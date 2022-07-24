#!/usr/bin/env python
# _#_ coding:utf-8 _*_
import re
import os
import time
import json
import logging
import requests
import subprocess
from git import Repo
from pathlib import Path
from ruamel import yaml
from django.conf import settings
from requests.packages.urllib3.exceptions import InsecureRequestWarning

server_logger = logging.getLogger('django')


class Deploy_check(object):
    def __init__(self,servicename=None, imageversion=None, cluster=None, deploytype=None, namespace='spatio-dev'):
        self.imageversion = imageversion
        self.cluster = cluster
        self.deploytype = deploytype
        self.logdir = settings.CONFIG.get('k8s_templates', 'deploylog_dir')

        if deploytype == 'canary':
            self.service_name = '%s-canary' % servicename
            self.service_comm = '%s,track=canary' % servicename
        else:
            self.service_name = servicename
            self.service_comm = servicename

        if self.cluster == 'spatio-dev':
            self.namespace = 'spatio-dev'
        else:
            self.namespace = namespace

        self.variable = '{cluster}-{svcname}-{commitid}'.format(cluster=self.cluster, svcname=self.service_name, commitid=self.imageversion)

    def command_operator(self,comm):
        sub_data = subprocess.run(comm, shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
        str_data = str(sub_data.stdout, encoding="utf-8")
        if sub_data.returncode == 0:
            return True, str_data
        return False, str_data

    def file_op(self,filename=None,content=None,optype='r'):
        file_r = open(filename, optype)
        if optype == 'r':
            content_info =  file_r.readline()
        else:
            content_info = file_r.write(content)
        file_r.close()
        return content_info

    def pod_check(self):
        pod_comm = '/usr/local/bin/kubectl get pod -n %s -l app=%s --output=wide |grep -v "Evicted"' % (self.namespace, self.service_comm)
        comm_status, comm_data = self.command_operator(pod_comm)
        return comm_data

    def timer_check(self,timerlog,times):
        deploy_info = self.file_op(filename=timerlog, optype='r')
        info_split = deploy_info.split(',')
        old_timer = int(info_split[2])
        if (times - old_timer) > 599:
            os.remove(timerlog)
            info_split.append('\n FAILED: No progress is found in 5 minutes, please contact sre(sre@spatio-inc.com)')
            return False,info_split
        return True,info_split

    def container_check(self):
        check_command = '/usr/local/bin/kubectl get deployment.apps -n %s -l app=%s |tail -1|awk "{print \$2,\$3}"' % (self.namespace, self.service_comm)
        print(check_command)
        comm_status,comm_data = self.command_operator(check_command)
        if comm_status:
            timerlog = '%s/%s-timer.log' % (self.logdir, self.variable)
            pod_list = comm_data.split()
            pod_curr = int(pod_list[1])
            pod_total = int((pod_list[0]).split('/')[1])

            times = int(time.time())
            content_info = '%d,%d,%d' % (pod_total, pod_curr, times)

            if pod_total == pod_curr:
                if os.path.isfile(timerlog):
                    #comm_status,comm_data = self.command_operator(pod_comm)
                    comm_data = self.pod_check()

                    pod_curr_list = comm_data.split('\n')
                    pod_curr_number = len(pod_curr_list) - 2
                    pod_curr_running = len(re.findall(r'Running',comm_data))

                    if pod_curr_number == pod_total and pod_curr_running == pod_total:
                        comm_data += '\n %s-deployment-end.' % self.variable
                        os.remove(timerlog)
                    else:
                        deploy_status, deploy_data = self.timer_check(timerlog,times)
                        if deploy_status:
                            comm_data = '\n 1 In application deployment. progress is %s/%s.' % (pod_curr, pod_total)
                            if int(deploy_data[1]) != pod_curr:
                                self.file_op(filename=timerlog, content=content_info, optype='w')
                        else:
                            comm_data += deploy_data[-1]
                            return False,comm_data
                else:
                    #content_info = '%d,%d,%d' % (pod_total, pod_curr, times)
                    self.file_op(filename=timerlog, content=content_info, optype='w')
                    comm_data = '\n 2 In application deployment. progress is %s/%s.' % (pod_curr, pod_total)
                    time.sleep(5)
            else:
                if os.path.isfile(timerlog):
                    deploy_status, deploy_data = self.timer_check(timerlog, times)
                    if int(deploy_data[1]) == pod_curr:
                        if deploy_status:
                            content_info = '%d,%d,%d' % (pod_total, pod_curr, int(deploy_data[2]))
                        else:
                            comm_data = self.pod_check()
                            comm_data += deploy_data[-1]
                            return False,comm_data

                self.file_op(filename=timerlog, content=content_info, optype='w')
                comm_data = '\n 3 In application deployment. progress is %s/%s.' % (pod_curr, pod_total)

        return comm_status,comm_data


    def log_check(self):
        logfile = '%s/%s.log' % (self.logdir, self.variable)
        if Path(logfile).is_file():
            check_command = 'tail -500 %s' % logfile
            sub_data = subprocess.run(check_command, shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
            if sub_data.returncode == 0:
                str_data = str(sub_data.stdout, encoding="utf-8")
                if 'Error' in str_data or 'FAILED' in str_data:
                    return False, str_data
                else:
                    re_data = str_data.split('\n')[-3:]
                    re_data_join = '\n'.join(re_data)

                    key_information = 'helm-%s-deployment-success' % self.variable
                    if key_information in re_data_join:
                        return self.container_check()

                    return True, re_data_join
            else:
                return False, 'Log acquisition failed'
        else:
            return False, 'The log file(%s) does not exist' % logfile


def Deploy_log(servicename=None, imageversion=None, cluster=None, deploytype=None, namespace='spatio-prod'):
    if deploytype == 'canary':
        service_name = '%s-canary' % servicename
    else:
        service_name = servicename
        print(service_name)
    variable = '{cluster}-{svcname}-{commitid}'.format(cluster=cluster, svcname=service_name, commitid=imageversion)
    logfile = '%s/%s.log' % (settings.CONFIG.get('k8s_templates', 'deploylog_dir'), variable)
    if Path(logfile).is_file():
        check_command = 'tail -500 %s' % logfile
        sub_data = subprocess.run(check_command, shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
        if sub_data.returncode == 0:
            str_data = str(sub_data.stdout, encoding="utf-8")
            if 'Error' in str_data or 'FAILED' in str_data:
                return False, str_data
            else:
                re_data = str_data.split('\n')[-3:]
                re_data_join = '\n'.join(re_data)

                key_information = '%s-deployment-end' % variable
                if key_information in re_data_join:
                    # obtain container info
                    check_comm = '/usr/local/bin/kubectl get pod -n %s -l app=%s --output=wide |grep -v Terminating' % (
                    namespace, servicename)
                    sub_check = subprocess.run(check_comm, shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
                    re_data_join += str(sub_check.stdout, encoding='utf-8')

                return True, re_data_join
        else:
            return False, 'Log acquisition failed'
    else:
        return False, 'The log file(%s) does not exist' % logfile


def Request_Op(url, params_data={}, headers_data={}, req_type='GET'):
    if req_type == 'POST':
        post_data = json.dumps(params_data)
        ret = requests.post(url, headers=headers_data, data=post_data)
    else:
        ret = requests.get(url, headers=headers_data, params=params_data)
    if ret.status_code == 200:
        ret_data = ret.json()
        ret_data['template'] = 'public_templates'
        return True, ret_data
    print(params_data)
    print(ret.status_code)
    return False, ret.text


def Service_config(servicename=None, cluster='spatio-dev', env='prod'):
    Axe_token = 'db7a5ef934405db9632410bbea115020b319dc1e'
    Axe_url = 'http://center.devops.spatio-inc.com/api/v1/k8s/deployment/'
    parm_data = {
        "token": Axe_token,
        "name": servicename,
        "cluster": cluster,
        "env": env
    }
    conf_status, default_conf = Request_Op(url=Axe_url, params_data=parm_data)
    server_logger.info(default_conf)
    return conf_status, default_conf


def Version_obtain(servicename=None, env='prod'):
    cluster_list = settings.CONFIG.get('k8s_templates', 'clusters')
    result_info = []
    for cluser in cluster_list.split(','):
        cluster_info = {"cluster": cluser}
        conf_status, conf_data = Service_config(servicename, cluser, env)
        if conf_status:
            curr_version = conf_data['image']['tag']
            curr_instance = conf_data['replicaCount']
            cluster_info['versions'] = {curr_version: curr_instance}
            result_info.append(cluster_info)

    if result_info == []:
        return False, 'Version retrieval failed.'
    return True, result_info


class Helm_template(object):
    def __init__(self, servicename='ops-sre-ngconf2', imageversion='16', cluster='spatio-dev', deploytype='formal',namespaces='spatio-dev',replicaCount=1):
        self.servicename = servicename
        self.imageversion = imageversion
        self.cluster = cluster
        self.deploytype = deploytype
        self.namespaces = namespaces
        self.replicacount = replicaCount
        self.repository_path = "%s/%s" % (settings.CONFIG.get('k8s_templates', 'template_dir'), self.servicename)
        self.serviceconf = self._Config_obtain()

    def _Config_obtain(self):
        res_conf = {"status": True}
        conf_status, default_conf = Service_config(self.servicename, self.cluster)
        if not conf_status:
            res_conf['status'] = False
            res_conf['conf'] = default_conf
            server_logger.error(res_conf)
            return res_conf

        try:
            if self.deploytype == 'canary':
                default_conf['canary']['enabled'] = 'true'
                default_conf['canary']['imagetag'] = self.imageversion
                default_conf['canary']['replicaCount'] = self.replicacount
                formal_replicacount = default_conf['replicaCount']

                if self.replicacount >= formal_replicacount:
                    res_conf['status'] = False
                    res_conf['conf'] = 'Replicacount must be less than the formal quantity.'
            else:
                default_conf['canary']['enabled'] = 'false'
                default_conf['image']['tag'] = self.imageversion
            default_conf['service']['name'] = self.servicename
            default_conf['cluster'] = self.cluster
            # 标签修改
            if default_conf['affinity']['node_idc'] == "random":
                del default_conf['affinity']['node_idc']

            if default_conf['livenessProbe_enabled']:
                del default_conf['livenessProbe']['type']
                del default_conf['livenessProbe']['value']
            if default_conf['readinessProbe_enabled']:
                del default_conf['readinessProbe']['type']
                del default_conf['readinessProbe']['value']
            if default_conf['startupProbe_enabled']:
                del default_conf['startupProbe']['type']
                del default_conf['startupProbe']['value']

        except Exception as Err:
            res_conf['status'] = False
            res_conf['conf'] = 'template conf obtain failed：%s' % Err
            server_logger.error(res_conf)

        else:
            res_conf['conf'] = default_conf
        return res_conf
    #生成helm values文件
    def template_product(self, json_data, values_file=None):
        template_type = json_data['template']
        if values_file == None:
            values_file = "%s/%s/values.yaml" % (self.repository_path, template_type)
        else:
            values_file = "%s/%s/values-%s.yaml" % (self.repository_path, template_type, values_file)

        with open(values_file, "w", encoding="utf-8") as f:
            yaml.dump(json_data, f, Dumper=yaml.RoundTripDumper)

    def command_operation(self, comm):
        comm_op = subprocess.run(comm, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        if comm_op.returncode == 0:
            return True, 'command(%s) operation success.' % comm
        else:
            return False, comm_op.stderr

    def template_obtain(self):
        conf_data = self.serviceconf['conf']
        if self.serviceconf['status'] is None:
            return False, conf_data

        git_token = settings.CONFIG.get('k8s_templates', 'token')
        git_uri = settings.CONFIG.get('k8s_templates', 'giturl')
        giturl = "https://oauth2:%s@%s" % (git_token, git_uri)

        try:
            if not Path(self.repository_path).is_dir():
                Repo.clone_from(giturl, self.repository_path, branch='master')
            repo = Repo(self.repository_path)
            repo.git.reset('--hard')
            o = repo.remotes.origin
            o.pull()
        except Exception as Err:
            error_log = 'git operation filed: %s' % Err
            server_logger.error(error_log)
            return False, error_log
        self.template_product(conf_data, values_file=self.deploytype)
        return True, "helm template obtain success."

    # def judge_image(self):
    #     req_data = {'status': True, 'data': 'Mirror exists'}
    #     conf_data = self.serviceconf['conf']
    #     image_name= conf_data['image']['image']
    #     image_name = '{image_name}:{image_tag}'.format(image_name=image_name,image_tag=conf_data['image']['tag'])
    #     image_env = ''.join(re.findall(r"\S+/(\w+.+)/", conf_data['image']['repository'], flags=re.I))
    #     image_url = 'https://docker2.yidian.com:5000/v2/{image_env}/{image_name}/manifests/latest'.format(image_env=image_env, image_name=image_name)
    #     headers = {'Accept': 'application/vnd.docker.distribution.manifest.v2+json'}
    #     requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    #     res = requests.get(url=image_url, headers=headers, verify=False)
    #     if res.status_code == 200:
    #         return req_data
    #     else:
    #         judge_ops = re.match('ops', image_name)
    #         if judge_ops:
    #             return req_data
    #         else:
    #             req_data['status'] = 'False'
    #             req_data['data'] = 'docker2.yidian.com:5000/{image_env}/{image_name} does not exists'.format(
    #                 image_env=image_env, image_name=image_name)
    #             return req_data

    def delete_hpa(self,switch=False):
        if switch == True:
            delete_command = 'kubectl delete hpa {servicename}  -n {namespaces} "'.format(servicename=self.servicename,namespaces=self.namespaces)
            un_status, un_data = self.command_operation(delete_command)
            print(un_status, un_data)

    def helm_op(self):
        conf_data = self.serviceconf['conf']
        if self.deploytype == 'canary':
            canaryname = '%s-canary' % self.servicename
        else:
            canaryname = self.servicename

        variable = '{cluster}-{servicename}-{commitid}'.format(cluster=self.cluster, servicename=canaryname,commitid=self.imageversion)
        #指定发布目录的绝对路径
        template_path = '{repository}/{template}/'.format(repository=self.repository_path,template=conf_data['template'])
        helm_command='cd {templatepath} && helm upgrade -i -f values-{valuefile}.yaml {servicename} ./ -n {namespace} --debug'.format(
            templatepath=template_path, valuefile=self.deploytype, servicename=canaryname,
            namespace=conf_data['namespace'])

        end_command = 'echo "helm-{servicevariable}-deployment-success."'.format(servicevariable=variable)
        operation_command = 'echo "{helm_command}"'.format(helm_command=helm_command)
        #生成发布命令和echo命令
        deploy_command = '{helmcommand} && {endcommand} && {operation_command}'.format(helmcommand=helm_command,endcommand=end_command,operation_command=operation_command)
        server_logger.info(deploy_command)

        deploylog_dir = settings.CONFIG.get('k8s_templates', 'deploylog_dir')
        #判断是否存在这个目录，如果存在不创建
        Path(deploylog_dir).mkdir(exist_ok=True)
        deploy_log = '{logdir}/{servicevariable}.log'.format(logdir=deploylog_dir, servicevariable=variable)
        # if os.path.exists(deploy_log):
        #     os.remove(deploy_log)
        if self.deploytype == 'formal':
            self.delete_hpa(self.serviceconf['conf']['hpa']['enabled'])
        subprocess.Popen(deploy_command, shell=True, stdout=open(deploy_log, 'w'), stderr=subprocess.STDOUT)

        if self.deploytype == 'canary':
            conf_data['canary']['enabled'] = 'false'
            formal_replicacount = conf_data['replicaCount']
            new_repliccacount = int(formal_replicacount) - int(self.replicacount)

            if new_repliccacount > 1:
                del_command = 'cd {templatepath} && kubectl scale deployment {servicename} -n  {namespace} --replicas={new_repliccacount} "'.format(
                    templatepath=template_path, servicename=self.servicename, namespace=conf_data['namespace'],
                    new_repliccacount=new_repliccacount)
                print(del_command)
                server_logger.info(del_command)
                #执行删除副本数的操作
                del_status, del_data = self.command_operation(del_command)
                return del_status, del_data

            return True, 'Helm operation completed.'

        else:
            uninstall_canary = 'helm uninstall {servicename}-canary -n {namespace}'.format(
                servicename=self.servicename, namespace=conf_data['namespace'])
            server_logger.info(uninstall_canary)
            un_status, un_data = self.command_operation(uninstall_canary)
            return True, un_data


if __name__ == '__main__':
    a = Helm_template()
    c, d = a.template_obtain()

