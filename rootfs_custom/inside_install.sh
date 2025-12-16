#!/bin/sh

export LD_LIBRARY_PATH=/usr/lib/apt-private/lib:$LD_LIBRARY_PATH
export DEBIAN_FRONTEND=noninteractive

apt-get update

rm /etc/ssl/openssl.cnf

apt-get install -y python3
python3 --version

apt-get install -y wget curl

python3 get-pip.py -i https://mirrors.aliyun.com/pypi/simple
pip3 --version

pip3 install -i https://mirrors.aliyun.com/pypi/simple/ /axengine-0.1.3-py3-none-any.whl
pip3 install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

apt-get clean
apt-get autoclean
rm -rf /var/lib/apt/lists/*

rm /get-pip.py
rm /axengine-0.1.3-py3-none-any.whl
rm /requirements.txt
rm -rf /tmp/*
rm /inside_install.sh

history -c

exit