FROM harbor.int.yidian-inc.com/sre-project/ops-sre-kubernetes-cd-2-image:latest
MAINTAINER xiaoxiang

RUN rm -rf /home/service/kubernetes-cd && rm -rf /root/.kube/config
COPY  kubernetes-cd /home/service/kubernetes-cd
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && unzip awscliv2.zip && ./aws/install
WORKDIR /home/service/kubernetes-cd
CMD ["/bin/sh", "bin/deploy.sh"]
EXPOSE 8888
