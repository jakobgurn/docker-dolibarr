#!/usr/bin/env python3

import hashlib
import logging
import os
import re
import stat
import subprocess
import sys
import time
from logging import debug, info, warning, error, critical
from zipfile import ZipFile

logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s", 
                    level=logging.INFO,
                    datefmt="%Y-%m-%d %H:%M:%S")

__dir_doc = "/var/www/documents"
__dir_htdocs = "/var/www/html"
__dir_scripts = "/var/www/scripts"
__dir_dbinst = os.path.join(__dir_htdocs, "install")

__php_ini = "/usr/local/etc/php/php.ini"
__php_ini_prod = "/usr/local/etc/php/php.ini-production"

__doli_zip = "/tmp/dolibarr.zip"
__doli_conf = f"{__dir_htdocs}/conf/conf.php"

doli_version = os.environ.get("DOLI_VERSION")
www_uid = int(os.environ.get("WWW_USER_ID", 33))
www_gid = int(os.environ.get("WWW_GROUP_ID", 33))

if os.environ.get("DOLI_DB_TYPE") == "mysql" or os.environ.get("DOLI_DB_TYPE") == "mariadb":
    debug("using mysql/mariadb database")
    from MySQLdb import connect, IntegrityError, OperationalError, ProgrammingError

    __dir_dbinst = os.path.join(__dir_dbinst, "mysql")
    __db_exec = "/usr/bin/mariadb --host={host} --port={port} --user={user} --password={password} {database}"
    doli_db_type = "mysqli"
else:
    critical("Invalid DOLI_DB_TYPE: {}".format(os.environ.get("DOLI_DB_TYPE")))
    sys.exit(1)

def connect_to_DB():
    info("connecting to database {host}:{port}/{name} as {user}".format(
                                                                host=os.environ.get("DOLI_DB_HOST"),
                                                                port=int(os.environ.get("DOLI_DB_PORT")),
                                                                name=os.environ.get("DOLI_DB_NAME"),
                                                                user=os.environ.get("DOLI_DB_USER")))
    try:
        con = connect(  host=os.environ.get("DOLI_DB_HOST"),
                        port=int(os.environ.get("DOLI_DB_PORT")),
                        database=os.environ.get("DOLI_DB_NAME"),
                        user=os.environ.get("DOLI_DB_USER"),
                        password=os.environ.get("DOLI_DB_PASSWORD")
                        )
        return con
    except Exception as err:
        warning(f"Error connecting to database: {err}")

def chown_recursive(path, uid, gid):
    for dirpath, _, filenames in os.walk(path):
        debug(f"chown {uid}:{gid} {path}")
        os.chown(dirpath, uid, gid)
        for fname in filenames:
            debug("chown {uid}:{gid} {path}".format(uid=uid, gid=gid, path=os.path.join(dirpath, fname)))
            os.chown(os.path.join(dirpath, fname), uid, gid)

def copy_recursive(src, target):
    if os.path.exists(src):
        st = os.stat(src)
        
        if os.path.isdir(src):
            debug(f"mkdir {target}")
            os.makedirs(target, exist_ok=True)
        else:
            with open(src, "rb") as sf, open(target, "wb") as tf:
                debug(f"cp {src} {target}")
                tf.write(sf.read())
        
        # copy permissions
        debug(f"chown {st[stat.ST_UID]}:{st[stat.ST_GID]} {target}")
        os.chown(target, st[stat.ST_UID], st[stat.ST_GID])
        debug(f"chmod {st[stat.ST_MODE]} {target}")
        os.chmod(target, st[stat.ST_MODE])
        
        if os.path.isdir(src):
            for f in os.listdir(src):
                copy_recursive(os.path.join(src, f), os.path.join(target, f))

def remove_recursive(path):
    if os.path.exists(path):
        if os.path.isdir(path):
            for f in os.listdir(path):
                remove_recursive(os.path.join(path, f))
            debug(f"rmdir {path}")
            os.rmdir(path)
        else:
            debug(f"rm {path}")
            os.remove(path)

def execute_SQL(con, sql, binds=tuple(), from_script=False):
    if not from_script:
        info(f"executing SQL: {sql} ({binds})")
    cur = con.cursor()

    if len(sql.strip()) == 0:
        debug("Skipping empty sql command ...")
        return

    try:
        cur.execute(sql, binds)
    except UnicodeEncodeError as err:
        warning(f"Error executing SQL: {err} ({sql}, ({binds}))")
        return

    if cur.rowcount > 0:
        res = cur.fetchall()
    else:
        con.commit()
        res = None
    
    cur.close()

    return res

def execute_script(filename):
    info(f"Executing script {filename}")
    if not os.path.isfile(filename):
        critical(f"File {filename} not found!")
    
    return subprocess.call(__db_exec.format(
                        host=os.environ.get("DOLI_DB_HOST"),
                        port=os.environ.get("DOLI_DB_PORT"),
                        database=os.environ.get("DOLI_DB_NAME"),
                        user=os.environ.get("DOLI_DB_USER"),
                        password=os.environ.get("DOLI_DB_PASSWORD")) + f" < {filename}", shell=True)
    

def change_uid(user, uid):
    info(f"Changing uid of {user} to {uid}")
    changed = None

    with open("/etc/passwd", "r") as pwdf:
        lines = pwdf.readlines()

    olines = list()
    for l in lines:
        _l = l.split(":")

        if _l[0] == user:
            if _l[2] != str(uid):
                _l[2] = str(uid)
                changed = True
            else:
                changed = False
        else:
            if _l[2] == str(uid):
                uname = _l[0]
                error(f"The UID {uid} is already in use for user {uname}! Aborting!")
                return 

        olines.append(":".join(_l))

    if changed:
        with open("/etc/passwd", "w") as pwdf:
            pwdf.writelines(olines)
    
    return changed
    
def change_gid(group, gid):
    info(f"Changing gid of {group} to {gid}")
    changed = None
    old_gid = None

    with open("/etc/group", "r") as grpf:
        lines = grpf.readlines()

    olines = list()
    for l in lines:
        _l = l.split(":")

        if _l[0] == group:
            old_gid = _l[2]
            _l[2] = str(gid)
            changed = old_gid != str(gid)
        else:
            if _l[2] == str(gid):
                gname = _l[0]
                error(f"The GID {gid} is already in use for group {gname}! Aborting!")
                return
        olines.append(":".join(_l))

    if changed:
        with open("/etc/group", "w") as grpf:
            grpf.writelines(olines)

        with open("/etc/passwd", "r") as pwdf:
            lines = pwdf.readlines()
        olines = list()
        for l in lines:
            _l = l.split(":")
            if _l[3] == old_gid:
                _l[3] = str(gid)
            olines.append(":".join(_l))
        with open("/etc/passwd", "w") as pwdf:
            pwdf.writelines(olines)
    
    return changed

#
# create directories
#
info("Creating directories")
os.makedirs(__dir_doc, mode=0o755, exist_ok=True)
os.makedirs(__dir_htdocs, mode=0o755, exist_ok=True)
os.makedirs(__dir_scripts, mode=0o755, exist_ok=True)

#
# change UID and GID of www-data user and group
#
uidchanged = change_uid("www-data", www_uid)
gidchanged = change_gid("www-data", www_gid)


if uidchanged or gidchanged:
    info("Correcting owner of /var/www")
    chown_recursive("/var/www", www_uid, www_gid)

for d in (__dir_doc, __dir_htdocs, __dir_scripts):
    if os.stat(d).st_uid != www_uid or os.stat(d).st_gid != www_gid:
        info(f"Correcting owner of {d}")
        chown_recursive(d, www_uid, www_gid)

#
# Unzip files
#
htdocs_version = open(os.path.join(__dir_htdocs, "version"), "r").read() if os.path.isfile(os.path.join(__dir_htdocs, "version")) else None
scripts_version = open(os.path.join(__dir_scripts, "version"), "r").read() if os.path.isfile(os.path.join(__dir_scripts, "version")) else None

if htdocs_version != doli_version or scripts_version != doli_version:
    info("Version outdated or dolibarr not installed - unzipping files")
    with ZipFile(__doli_zip)as dzip:
        dzip.extractall("/tmp/dolibarr")
    
    if htdocs_version != doli_version:
        info(f"Copying htdocs to {__dir_htdocs}")
        copy_recursive(f"/tmp/dolibarr/dolibarr-{doli_version}/htdocs", __dir_htdocs)
        chown_recursive(__dir_htdocs, www_uid, www_gid)
        with open(os.path.join(__dir_htdocs, "version"), "w") as vfile:
            vfile.write(doli_version)

    if scripts_version != doli_version:
        info(f"Copying scripts  to {__dir_scripts}")
        copy_recursive(f"/tmp/dolibarr/dolibarr-{doli_version}/scripts", __dir_scripts)
        chown_recursive(__dir_scripts, www_uid, www_gid)
        with open(os.path.join(__dir_scripts, "version"), "w") as vfile:
            vfile.write(doli_version)
    
    info("Removing extracted zip")
    remove_recursive("/tmp/dolibarr")

  
if not os.path.islink("/var/www/htdocs") and not os.path.exists("/var/www/htdocs"):
    info(f"Creating symlink from /var/www/htdocs to {__dir_htdocs}")
    os.symlink(__dir_htdocs, "/var/www/htdocs")

#
# update php.ini
#
info("Updating php.ini")
__phpsrc = __php_ini if os.path.isfile(__php_ini) else __php_ini_prod
__phplines = list()

with open(__phpsrc, "r") as pf:
    __phplines = pf.readlines()

for i in range(len(__phplines)):
    if "date.timezone =" in __phplines[i]:
        __phplines[i] = "date.timezone = {}".format(os.environ.get("PHP_INI_DATE_TIMEZONE"))
    elif "sendmail_path =" in __phplines[i]:
        __phplines[i] = "sendmail_path = /usr/sbin/sendmail -t -i"

with open(__php_ini, "w") as pf:
    pf.writelines(__phplines)

#
# create dolibarr conf.php
#
info("Creating dolibarr conf.php")
if not os.path.isfile(__doli_conf):
    doli_cfg = [
         "<?php"
         "  $dolibarr_main_url_root='{}';".format(os.environ.get("DOLI_URL_ROOT")),
        f"  $dolibarr_main_document_root='{__dir_htdocs}';",
         "  $dolibarr_main_url_root_alt='/custom';",
        f"  $dolibarr_main_document_root_alt='{__dir_htdocs}/custom';",
        f"  $dolibarr_main_data_root='{__dir_doc}';",
         "  $dolibarr_main_db_host='{}';".format(os.environ.get("DOLI_DB_HOST")),
         "  $dolibarr_main_db_port='{}';".format(os.environ.get("DOLI_DB_PORT")),
         "  $dolibarr_main_db_name='{}';".format(os.environ.get("DOLI_DB_NAME")),
         "  $dolibarr_main_db_prefix='llx_';",
         "  $dolibarr_main_db_user='{}';".format(os.environ.get("DOLI_DB_USER")),
         "  $dolibarr_main_db_pass='{}';".format(os.environ.get("DOLI_DB_PASSWORD")),
        f"  $dolibarr_main_db_type='{doli_db_type}';",
         "  $dolibarr_main_prod='{}';".format(os.environ.get("DOLI_PROD"))
    ]

    with open(__doli_conf, "w") as dcf:
        dcf.write("\n".join(doli_cfg))

    os.chown(__doli_conf, www_uid, www_gid)
    os.chmod(__doli_conf, 0o400)

#
# run dolibarr installation
#
if os.environ.get("DOLI_INSTALL_AUTO") == "1":
    info("Running dolibarr installation")

    con = None
    while con is None:
        con = connect_to_DB()
        time.sleep(2)

    try:
        execute_SQL(con, "SELECT * FROM llx_const")
        _run_install = False
    except:
        _run_install = True

    if _run_install:
        info("Running dolibarr installation SQL-scripts")
        for f in os.listdir(os.path.join(__dir_dbinst, "tables")):
            if re.match(r".*\.sql$", f) and not re.match(r".*\.key\.sql$", f):
                execute_script(os.path.join(__dir_dbinst, "tables", f))

        for f in os.listdir(os.path.join(__dir_dbinst, "tables")):
            if re.match(r".*\.key\.sql$", f):
                execute_script(os.path.join(__dir_dbinst, "tables", f))

        for f in os.listdir(os.path.join(__dir_dbinst, "functions")):
            if re.match(r".*\.sql$", f):
                execute_script(os.path.join(__dir_dbinst, "functions", f))

        for f in os.listdir(os.path.join(__dir_dbinst, "data")):
            if re.match(r".*\.sql$", f):
                execute_script(os.path.join(__dir_dbinst, "data", f))

        info("Creating SuperAdmin account")
        pass_crypted = hashlib.md5(os.environ.get("DOLI_ADMIN_PASSWORD").encode()).hexdigest()
        execute_SQL(con, "INSERT INTO llx_user (entity, login, pass_crypted, lastname, admin, statut) VALUES (0, %s, %s, 'SuperAdmin', 1, 1)", (os.environ.get("DOLI_ADMIN_LOGIN"), pass_crypted))
        
        info("Setting some default const")
        for to_del in ("MAIN_VERSION_LAST_INSTALL", "MAIN_NOT_INSTALLED", "MAIN_LANG_DEFAULT"):
            execute_SQL(con, "DELETE FROM llx_const WHERE name=%s", (to_del, ))
        execute_SQL(con, "INSERT INTO llx_const (name, value, type, visible, note, entity) VALUES ('MAIN_VERSION_LAST_INSTALL', %s, 'chaine', 0, 'Dolibarr version when install', 0)", (doli_version, ))
        execute_SQL(con, "INSERT INTO llx_const (name, value, type, visible, note, entity) VALUES ('MAIN_LANG_DEFAULT', 'auto', 'chaine', 0, 'Default language', 1)")

        info("Creating install.lock")
        open(os.path.join(__dir_doc, "install.lock"), "w").close()
        os.chown(os.path.join(__dir_doc, "install.lock"), www_uid, www_gid)
        os.chmod(os.path.join(__dir_doc, "install.lock"), 0o400)

#
# run apache2
#
info("Starting apache2")
os.system("apache2-foreground")