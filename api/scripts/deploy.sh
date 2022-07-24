#!/bin/bash
set -e

SERVER_NAME="ops-sre-ngconf2"
CURRENT_VERSIONS="core_version_17_instances_3"
CLUSTER="core"
DEPLOY_TYPE="canary"
INSTANCE_NUMBER="1"
COMMIT_ID="16"

#获取当前线上版本
[[ -n "${CURRENT_VERSIONS}" ]] &&  { OLD_VERSION=$(echo ${CURRENT_VERSIONS}|awk -F'_' '{print $3}'); } || { OLD_VERSION="0"; }
#echo $OLD_VERSION

TOKEN="Token 2668e7da6a8377fccda2d06983e22483e488c176"

#deploymen
function Deployment () {
    curl -H "Content-type: application/json" -H "Authorization: ${TOKEN}" -X POST -d '{"service_name":"'${SERVER_NAME}'","commit_id":"'${COMMIT_ID}'","cluster":"'${CLUSTER}'","deploy_type":"'${DEPLOY_TYPE}'","instance_number":"'${INSTANCE_NUMBER}'","current_version":"'${OLD_VERSION}'"}' http://kubernetes-cd.int.yidian-inc.com/api/cd/deployment|tee /tmp/result.txt
    result=$(cat "/tmp/result.txt")

    [[ -z "$(echo ${result}|grep {\"detail\")" ]] || { echo "\ndeploy failed.";exit 1; }
    [[ -z "$(echo ${result}|grep FAILED)" ]] || { echo "\ndeploy failed.";exit 1; }

    echo "\n##################################Start deployment######################################\n"

    if [[ "${DEPLOY_TYPE}" == "canary" ]];then
        variable="${SERVER_NAME}-canary"
    else
        variable="${SERVER_NAME}"
    fi
    #echo "${CLUSTER}-${variable}-end"

    while true
    do
        curl -s -o /tmp/result.txt -H "Content-type: application/json" "http://kubernetes-cd.int.yidian-inc.com/api/cd/deployment?cluster=${CLUSTER}&commit_id=${COMMIT_ID}&deploy_type=${DEPLOY_TYPE}&service_name=${SERVER_NAME}"
        re_result=$(cat "/tmp/result.txt")
        [[ -z "$(echo ${re_result}|grep FAILED)" ]] || { echo "${re_result} \n deploy failed."; exit 1; }

        [[ -z "$(echo ${re_result}|egrep ${CLUSTER}-${variable}-${COMMIT_ID}-deployment-end)" ]] || { echo "${re_result}\n deploy success."; exit 0; }

        #info=`echo "${re_result}"|grep -Po '(?<="info":").*?(?="})'`
        info=`echo "${re_result}"|awk -F',' '{print $NF}'`
        echo "$info\n"
        sleep 3
    done
}

Deployment
:
