#!/usr/bin/env bash

DIR=~/.vhost
if [[ ! -d $DIR ]] ; then
    mkdir -p ~/.vhost
#    sudo ln -sv $DIR /root/.vhost
fi

cp -vR share ~/.vhost
sudo cp -v vhost.py /usr/bin/vhost

if [ ! -f ~/.vhost/vhost.conf ]; then
    cp -v vhost.conf ~/.vhost/vhost.conf
fi