#!/usr/bin/env python

# Copyright (C) 2011-2015 Alex Oleshkevich <alex.oleshkevich@gmail.com>
#
# Authors:
#  Alex Oleshkevich
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; version 3.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

import argparse, getpass, sys, logging, configparser, os, subprocess, pwd, grp

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

configs = (os.getenv('HOME') + '/.vhost/vhost.conf', '/etc/vhost.conf', 'vhost.conf')

config_files = [config for config in configs if os.path.exists(config)]

if len(config_files) == 0:
    logger.error('Vhost is not configured. Configure ~/.vhost.conf first.')
    sys.exit(1)

config = configparser.ConfigParser()
config.read(configs)

uid = pwd.getpwnam(config.get('general', 'user')).pw_uid
gid = grp.getgrnam(config.get('general', 'group')).gr_gid

class SkipFilter(logging.Filter):
    def filter(self, record):
        return False

def restart_httpd():
    subprocess.call(config.get('apache', 'restart_command').split())

def exists(path):
    return os.path.exists(path)

def get_sitename(name):
    return name + config.get('general', 'domain', fallback='.local')

def get_vhost_avail_path(vhost_name):
    ext = config.get('general', 'vhost_file_suffix', fallback='.conf')
    path = config.get('apache', 'dir_hosts_available', fallback='/etc/vhost/sites-available') + '/' + vhost_name + ext
    return path

def get_vhost_enabl_path(vhost_name):
    ext = config.get('general', 'vhost_file_suffix', fallback='.conf')
    path = config.get('apache', 'dir_hosts_enabled', fallback='/etc/vhost/sites-enabled') + '/' + vhost_name + ext
    return path

def find_file(file_set):
    return [file for file in file_set if os.path.exists(file)]

def has_in_hosts(sitename):
    handle = open(config.get('general', 'hosts_file', fallback='/etc/hosts'), 'r')
    contents = handle.read()
    handle.close()
    return sitename in contents

def add_to_hosts(sitename):
    path = config.get('general', 'hosts_file', fallback='/etc/hosts')
    if not has_in_hosts(sitename):
        logger.debug('--> add vhost to %s' % path)
        handle = open(path, 'a')
        handle.write('127.0.0.1         %s\n' % sitename)
        handle.close()
    else:
        logger.debug('--> sitename already in %s' % path)

def remove_from_hosts(sitename):
    path =  config.get('general', 'hosts_file', fallback='/etc/hosts')
    if has_in_hosts(sitename):
        handle = open(path, 'r+') # rw
        contents = handle.readlines()
        new_contents = ''
        for line in contents:
            if sitename not in line:
                new_contents += line

        handle.seek(0)
        handle.write(new_contents)
        handle.truncate()
        handle.close()
        logger.debug('--> removed from %s' % path)
    else:
        logger.debug('--> sitename is not in %s' % path)

def is_enabled(name):
    path = get_vhost_enabl_path(name)
    return exists(path)

def has_mysql_module():
    has = False
    try:
        import importlib
        importlib.import_module('mysql.connector')
        has = True
    except:
        pass
    return has

def get_mysql_connection():
    import mysql.connector
    from mysql.connector import errorcode
    mysql_user = config.get('mysql', 'user')
    mysql_pass = config.get('mysql', 'password')
    mysql_host = config.get('mysql', 'host')
    return mysql.connector.connect(user=mysql_user, password=mysql_pass, host=mysql_host)

def get_site_root(name):
    sitesroot = config.get('general', 'sites_dir', fallback='/var/www')
    return '%s/%s' % (sitesroot, get_sitename(name))

def _create(args):
    if not args.dump:
        if os.path.exists(get_vhost_avail_path(args.name)):
            logger.warning('--> vhost exists. you may want to enable this?')
            sys.exit()
    else:
        logger.addFilter(SkipFilter())

    logger.info('Create: %s', args.name)

    sitesroot = config.get('general', 'sites_dir', fallback='/var/www')
    template = find_file((os.getenv('HOME') + '/.vhost/share/vhost.conf', '/etc/vhost/share/vhost.conf', 'share/vhost.conf'))[0]
    logger.debug('Use template: %s' % template)
    contents = open(template).read()
    contents = contents\
        .replace('%name%', get_sitename(args.name))\
        .replace('%sitesdir%', sitesroot)\
        .replace('%ip%', args.ip)

    # handle --subdir switch
    subdir = args.subdir or ''
    if len(subdir) > 0 and subdir[0] != '/':
        subdir = '/' + subdir
    contents = contents.replace('%subdir%', subdir)

    port = 80
    ssl_content = ''
    if args.ssl:
        ssl_part = find_file((os.getenv('HOME') + '/.vhost/share/ssl.conf', '/etc/vhost/ssl.conf', 'share/ssl.conf'))[0]
        if not ssl_part:
            raise Exception('Could not find SSL part.')

        cert_file = config.get('ssl', 'cert_file', fallback=None)
        key_file = config.get('ssl', 'key_file', fallback=None)

        if cert_file is None or key_file is None:
            raise Exception('Either ssl.cert_file or ssl.key_file is not found in config.')

        if not os.path.exists(cert_file):
            raise Exception('File not found: %s' % cert_file)

        if not os.path.exists(key_file):
            raise Exception('File not found: %s' % key_file)

        port = 443
        ssl_content = open(ssl_part).read()
        ssl_content = ssl_content.replace('%cert_file%', cert_file).replace('%key_file%', key_file)

    contents = contents.replace('%ssl%', ssl_content).replace('%port%', str(port))

    if args.dump:
        print (contents)
        sys.exit()

    # open file and write contents
    avail_vhost_path = get_vhost_avail_path(args.name)

    output = open(avail_vhost_path, 'w')
    output.write(contents)
    output.close()
    os.chown(avail_vhost_path, uid, gid)

    dirs = ('log', 'www' + subdir, 'tmp')
    site_root = '%s/%s' % (sitesroot, get_sitename(args.name))
    if not os.path.exists(site_root):
        os.mkdir(site_root)
        os.chown(site_root, uid, gid)

    for dir in dirs:
        new_dir = '%s/%s/%s' % (sitesroot, get_sitename(args.name), dir)
        logger.info('Create directory: %s' % new_dir)
        if os.path.exists(new_dir):
            logger.warning('--> already exists')
        else:
            os.makedirs(new_dir)
            os.chown(new_dir, uid, gid)

    if args.sample:
        sample_index = '%s/%s/www/index.html' % (sitesroot, get_sitename(args.name))
        index_template = find_file((os.getenv('HOME') + '/.vhost/share/index.html', '/etc/vhost/share/index.html', 'share/index.html'))[0]
        index_contents = open(index_template).read()
        index_contents = index_contents.replace('%site%', get_sitename(args.name))
        out = open(sample_index, 'w')
        out.write(index_contents)
        out.close()
        os.chown(sample_index, uid, gid)
        logger.info('--> add index.html: %s' % sample_index)

    if args.mysql:
        if has_mysql_module():
            try:
                mysql_charset = config.get('mysql', 'charset')
                connection = get_mysql_connection()
                logger.info('--> add mysql database: %s' % args.name)
                connection._execute_query('CREATE DATABASE %s CHARACTER SET %s' % (args.name, mysql_charset))
            except Exception as e:
                logger.error('MySQL error: %s' % str(e))
        else:
            logger.error('MySQL: cannot load connector. Install module: python-mysql-connector')

def _enable(args):
    logger.info('Enable: %s' % args.name)
    if is_enabled(args.name):
        logger.warning('--> already enabled')
    else:
        if exists(get_vhost_avail_path(args.name)):
            os.symlink(get_vhost_avail_path(args.name), get_vhost_enabl_path(args.name))
            os.chown(get_vhost_enabl_path(args.name), uid, gid)
            add_to_hosts(get_sitename(args.name))
            restart_httpd()
        else:
            logger.error('--> vhost does not exists')

def _disable(args):
    logger.info('Disable: %s' % args.name)
    if exists(get_vhost_avail_path(args.name)):
        if not is_enabled(args.name):
            logger.warning('--> not enabled')
        else:
            os.remove(get_vhost_enabl_path(args.name))
            remove_from_hosts(get_sitename(args.name))
            restart_httpd()
    else:
        logger.error('--> vhost does not exists')

def _remove(args):
    logger.info('Remove vhost')
    _disable(args)
    if exists(get_vhost_avail_path(args.name)):
        os.remove(get_vhost_avail_path(args.name))

    if args.purge:
        site_root = get_site_root(args.name)

        if exists(site_root):
            logger.info('--> remove site files in: %s' % site_root)

            import shutil
            shutil.rmtree(site_root)
        else:
            logger.warning('--> site root does not exists in: %s' % site_root)

    if args.mysql:
        if has_mysql_module():
            connection = get_mysql_connection()
            connection._execute_query('DROP DATABASE IF EXISTS %s' % args.name)
            logger.warning('--> database has been dropped')
        else:
            logger.error('MySQL: cannot load connector. Install module: python-mysql-connector')

def _info(args):
    if exists(get_vhost_avail_path(args.name)):
        print ('Config path: %s' % get_vhost_avail_path(args.name))
        print ('Host enabled: %s' % exists(get_vhost_enabl_path(args.name)))
        print ('Site root: %s' % get_site_root(args.name))
        print ('Site root exists: %s' % exists(get_site_root(args.name)))

        connection = get_mysql_connection()
        cursor = connection.cursor()
        cursor.execute('SELECT COUNT(*) AS exist FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = "%s"' % args.name)
        db_exists = False
        for exist in cursor:
            db_exists = (exist[0] == 1)
            break
        print ('Has database: %s' % db_exists)
    else:
        logger.critical('Vhost does not exists: %s' % args.name)

def _list(args):
    dir = config.get('apache', 'dir_hosts_available', fallback='/etc/apache2/sites-available')
    if args.only_enabled:
        dir = config.get('apache', 'dir_hosts_enabled', fallback='/etc/apache2/sites-enabled')

    for (dirpath, dirnames, filenames) in os.walk(dir):
        for file in filenames:
            print (file)

def main():
    parser = argparse.ArgumentParser(
        prog='vhost',
        description='Handy helper for easy PHP development.',
        epilog = 'Bug reports send to alex.oleshkevich@gmail.com'
    )

    group = parser.add_mutually_exclusive_group()

    # create
    group.add_argument('-c', '--create', help='create a new vhost', action='store_true', dest='create', default=False)
    parser.add_argument('--subdir', help='point document root this subdirectory', action='store', dest='subdir', default=None)
    parser.add_argument('--sample', help='add sample index.html file', action='store_true', dest='sample', default=None)
    parser.add_argument('--ip', help='bind to that IP address', action='store', dest='ip', default='*')
    parser.add_argument('--ssl', help='use SSL for that vhost', action='store_true', dest='ssl', default=False)
    parser.add_argument('--dump', help='dump vhost config', action='store_true', dest='dump', default=False)
    parser.add_argument('--mysql', help='create mysql database with same name as vhost', action='store_true', dest='mysql', default=False)

    # enable
    group.add_argument('-e', '--enable', help='enable existing vhost', action='store_true', dest='enable', default=False)

    # disable
    group.add_argument('-d', '--disable', help='disable vhost', action='store_true', dest='disable', default=False)

    # alter
    group.add_argument('-a', '--alter', help='alter vhost (opens GUI editor)', action='store_true', dest='alter', default=False)

    # remove
    group.add_argument('-r', '--remove', help='remove vhost', action='store_true', dest='remove', default=False)
    parser.add_argument('--purge', help='also remove site files', action='store_true', dest='purge', default=False)

    # list
    parser.add_argument('-l', '--list', help='list vhosts', action='store_true', dest='list', default=False)
    parser.add_argument('--enabled', help='show only enabled vhosts', action='store_true', dest='only_enabled', default=False)

    # info
    parser.add_argument('-i', '--info', help='vhosts details', action='store_true', dest='info', default=False)

    # vhost name
    parser.add_argument('name', action='store', default=False, help='vhost name')

    args = parser.parse_args()

    if not args.dump and not args.alter and not args.list and not args.info:
        if getpass.getuser() != 'root':
            print ('* You must be root to use this program.')
            sys.exit()

    try:
        if args.create:
            _create(args)
            _enable(args)
        elif args.enable:
            _enable(args)
        elif args.disable:
            _disable(args)
        elif args.remove:
            _remove(args)
        elif args.list:
            _list(args)
        elif args.info:
            _info(args)
        elif args.alter:
            if not exists(get_vhost_avail_path(args.name)):
                raise Exception('vhost "%s" does not exists' % args.name)
            subprocess.call(['xdg-open', get_vhost_avail_path(args.name)])
    except Exception as e:
        logger.critical(str(e))
        sys.exit()

if __name__ == '__main__':
    try:
        main()
    except OSError as e:
        logger.critical(e.strerror)
        sys.exit(e.errno)
