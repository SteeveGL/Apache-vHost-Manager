#!/usr/bin/env bash

DIR=/home/`whoami`/.vhost
if [[ ! -d $DIR ]] ; then
    mkdir -p ~/.vhost
fi

cp -vR share ~/.vhost
sudo cp -v vhost.py /usr/bin/vhost
sudo ln -sv $DIR /root/.vhost

if [ ! -f ~/.vhost/vhost.conf ]; then
    cp -v vhost.conf ~/.vhost/vhost.conf
    xdg-open ~/.vhost/vhost.conf
fi

