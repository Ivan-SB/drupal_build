#!/usr/bin/env python3

"""
dependencies:
python3-urllib3
python3-git
python3-yaml
python3-urllib3

https://docs.python.org/3/library/tarfile.html
https://janakiev.com/blog/python-shell-commands/

stdout, stderr = process.communicate()
stdout, stderr

with open('test.txt', 'w') as f:
    process = subprocess.Popen(['ls', '-l'], stdout=f)
"""

import os
import stat

import shutil
import sys
import signal

import subprocess

import tempfile

import re

import urllib3
import git

import tarfile

import MySQLdb
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

import yaml
import argparse
import getpass

# import pprint

DREPOSITORY = "https://git.drupal.org/project/drupal.git"
DPREPOSITORY = "https://git.drupalcode.org/project/{}.git"
DFILE = "drupal-{}.tar.gz"
DDIR = "drupal-{}"
DMFILE = "{}-{}.tar.gz"
DTAR = "https://ftp.drupal.org/files/projects/{}"

releases = { 'dev': 0, 'alpha': 1, 'beta': 2, 'rc': 3, None: 4, '': 4, 'x': 4 }

dctags_re = re.compile(r"[^ \t]+[ \t]+refs/tags/(([0-9]+)\.([0-9]+)\.?([0-9]+)?-?(dev|alpha|beta|rc)?([0-9]+)?).*")
dcbranches_re = re.compile(r"[^ \t]+[ \t]+refs/heads/(([0-9]+)\.([0-9x]+)?\.?([0-9x]+)?)()()().*")
dmtags_re = re.compile(r"[^ \t]+[ \t]+refs/tags/(([0-9]+)\.x-([0-9]+)?\.?([0-9]+)?-?(dev|alpha|beta|rc)?([0-9]+)?).*")
dmbranches_re = re.compile(r"[^ \t]+[ \t]+refs/heads/(([0-9]+)\.([0-9x]+)?-([0-9x]+)?\.?([0-9x]+)?)()().*")

class OnBreak():
  kill_now = False

  def __init__(self, s2S):
    self._s2S = s2S
    signal.signal(signal.SIGINT, self.exit_stoptasks)
    signal.signal(signal.SIGTERM, self.exit_stoptasks)

  def exit_stoptasks(self, signum, frame):
#     SOME ACTION
    sys.exit(0)

def zeroOnNoneX(x):
  t = 0 if(x == "x" or x == '') else x
  return int(t) if t is not None else 0


class Drupal():

  def _unpackProjects(self, components):
#     always return a list with 2 elements (component name, git flag)
    if components is not None:
      return list(map(lambda m: m.partition(',')[0:3:2], components))
    else:
      return None

  def __init__(self, cfg):
    self.cfg = cfg
    self.conn = None
    self.http = None
    self.modules = self._unpackProjects(cfg["modules"])
    self.themes = self._unpackProjects(cfg["themes"])

  def gitFilter(self, vl):
    if(self.cfg["base"] is not None):
      vl = [v for v in vl if (v[1][0] >= self.cfg["base"] * 100 ** 4 and v[1][0] < (self.cfg["base"] + 1) * 100 ** 4)]
    vl = [v for v in vl if (v[1][1][1] >= releases[self.cfg["release"]])]
    return vl

  def createDirs(self, base):
    os.makedirs(os.path.join(base, "core"), exist_ok=True)
    os.makedirs(os.path.join(base, "modules"), exist_ok=True)
    os.makedirs(os.path.join(base, "themes"), exist_ok=True)
    return base

  def createWorkingDir(self):
    if self.cfg["workdir"] is None:
      self.cfg["workdir"] = tempfile.mkdtemp(prefix="drupal_")
      self.createDirs(self.cfg["workdir"])
    else:
#       self.cfg["workdir"] = os.path.join(self.cfg["workdir"], "drupal_cache")
      os.makedirs(self.cfg["workdir"], exist_ok=True)
      self.createDirs(self.cfg["workdir"])

  def getRefs(self, repo, refsfilter):
    a = {}
    va = []
    refs = g.ls_remote(repo).split('\n')
    for ref in refs:
      refsmatch = re.search(refsfilter, ref)
      if(refsmatch is not None):
        va = [ zeroOnNoneX(refsmatch.group(6)),
            zeroOnNoneX(releases[refsmatch.group(5)]),
            zeroOnNoneX(refsmatch.group(4)),
            zeroOnNoneX(refsmatch.group(3)),
            zeroOnNoneX(refsmatch.group(2))]
        v = va[0] + 100 * va[1] + 100 ** 2 * va[2] + 100 ** 3 * va[3] + 100 ** 4 * va[4]
        a[refsmatch.group(1)] = (v, va)
    vl = sorted(a.items(), key=lambda kv:(kv[1][0]))
    return vl

  def getHTTP(self):
    if self.http is None:
      self.http = urllib3.PoolManager()
    return self.http

  def SaveFile(self, url, file):
    r = self.getHTTP().request('GET', url)
    f = open(file, 'wb')
    f.write(r.data)
    f.close

  def SaveCore(self):
    print("Saving Core")
    dcore = d.getRefs(DREPOSITORY, dctags_re)
    self.dcoref = d.gitFilter(dcore)
    rfile = DFILE.format(self.dcoref[-1][0])
    file = os.path.join(self.cfg["workdir"], "core", rfile)
    if(not os.path.exists(file)):
      url = DTAR.format(rfile)
      self.SaveFile(url, file)
      print("Core Saved")
    else:
      print("Core from cache")
    return file

  def installCore(self):
    file = self.SaveCore()
    print("Unpacking Core")
    tar = tarfile.open(file, 'r:gz')
    # TODO check if path exists otherwise create it
    basepath = os.path.split(os.path.normpath(self.cfg["path"]))[0]
    tar.extractall(path=basepath)
    tar.close()
    os.rename(os.path.join(basepath, DDIR.format(self.dcoref[-1][0])), self.cfg["path"])
    print("Core unpacked")

  def enableCore(self):
    print("Enabling Core")
    dbstring = "{}://{}:{}@{}/{}".format(self.cfg["db"]["driver"],
                                                  self.cfg["db"]["user"],
                                                  self.cfg["db"]["passwd"],
                                                  self.cfg["db"]["host"],
                                                  self.cfg["db"]["db"])
#     drush seems to need shell
    sstring = " ".join(("drush",
                        "site-install",
                        self.cfg["site"]["type"],
                        "--yes",
                        "--db-url",
                        dbstring,
                        "--account-mail", self.cfg["site"]["admin-mail"],
                        "--account-name", self.cfg["site"]["admin-name"],
                        "--account-pass", self.cfg["site"]["admin-passwd"],
                        "--site-mail", self.cfg["site"]["site-mail"],
                        "--site-name", self.cfg["site"]["site-name"],
                        ))
    p = subprocess.run(sstring, cwd=self.cfg["path"], shell=True, check=True)
    if(p.returncode == 0):
      print("Core enabled")
    else:
      print(p)

  def SaveProject(self, component):
    if(component == "modules"):
      components = self.modules
    elif(component == "themes"):
      components = self.themes
    else:
      components = None
    if components is not None:
      for m in components:
        dmrepo = DPREPOSITORY.format(m[0])
#         get tags
        if m[1] == '':
          print("Saving component {}".format(m[0]))
          dcomponents = self.getRefs(dmrepo, dmtags_re)
          dcomponentsf = self.gitFilter(dcomponents)
          rfile = DMFILE.format(m[0], dcomponentsf[-1][0])
          file = os.path.join(self.cfg["workdir"], component, rfile)
          if(not os.path.exists(file)):
            url = DTAR.format(rfile)
            self.SaveFile(url, file)
            print("Project {} saved".format(m[0]))
          else:
            print("Project {} from cache".format(m[0]))
        else:
#           get heads
          dcomponents = self.getRefs(dmrepo, dmbranches_re)
          dcomponentsf = self.gitFilter(dcomponents)
          file = None
        yield {"name": m[0], "file": file, "git": m[1], "branch": dcomponentsf[-1][0]}
    else:
      return

  def SaveProjects(self, component):
    for _ in self.SaveProject(component):
      pass

#   def installProject(self, component):
#     basepath = os.path.normpath(self.cfg["path"])
#     if(component=="modules"):
#       componentpath = os.path.join(basepath, "modules/contrib")
#     elif(component=="themes"):
#       componentpath = os.path.join(basepath, "themes/contrib")

  def installProjects(self, component):
    basepath = os.path.normpath(self.cfg["path"])
    componentpath = os.path.join(basepath, component, "contrib")
    for m in self.SaveProject(component):
      repo = DPREPOSITORY.format(m["name"])
      mdir = os.path.join(componentpath, m["name"])
      if m["git"] == 'g':
        print("shallow clone {}".format(m["name"]))
        p = subprocess.run(["git", "clone", "--depth", "1", "-b", m["branch"], repo, mdir])
        if(p.returncode == 0):
          print("Projects {} cloning OK".format(m["name"]))
        else:
          print(p)
      elif m["git"] == 'f':
        print("full clone {}".format(m["name"]))
        p = subprocess.run(["git", "clone", "--depth", "1", "-b", m["branch"], repo, mdir])
        if(p.returncode == 0):
          print("Projects {} cloning OK".format(m["name"]))
        else:
          print(p)
      else:
        print("Unpacking project {}".format(m["name"]))
        tar = tarfile.open(m['file'], 'r:gz')
        tar.extractall(path=componentpath)
        print("Project {} unpacked".format(m["name"]))

  def enableProjects(self, component):
    pass
#     if self.cfg.get("modules", None) is not None:
#       mod = ",".join(self.cfg["modules"])
#       p = subprocess.run(["drush", "en", mod], cwd=self.cfg["path"])
#       if(p.returncode == 0):
#         print("Projects OK")
#       else:
#         print(p)

  def composerPackages(self, packages):
    crequire = ["composer", "require"]
    cfgdir = os.path.join(self.cfg["path"], "sites", "default")
    pstring = ", ".join(packages)
    st_mode = os.stat(cfgdir).st_mode
    os.chmod(cfgdir, st_mode | stat.S_IWUSR)
    print("Installing packages {} via composer".format(pstring))
    crequire.extend(packages)
    p = subprocess.run(crequire, cwd=self.cfg["path"])
    if(p.returncode == 0):
      print("Composer packages {} OK".format(pstring))
    else:
      print(p)
    os.chmod(cfgdir, st_mode)

  def composerProjects(self, component):
    if(component == "modules"):
      components = self.modules
    elif(component == "themes"):
      components = self.themes
    else:
      components = None
    if components is not None:
      packages = list(map(lambda m: "drupal/{}".format(m[0]), components))
      self.composerPackages(packages)

  def createConnectionPG(self):
    ssl = self.cfg["db_admin"].get("ssl", None)
#     print('DB superuser credentials')
#     pwd = getpass.getpass(prompt='Password for user: ')
#     pwd = None
    if ssl is not None:
      key = ssl.get("key", None)
      cert = ssl.get("cert", None)
      ca = ssl.get("ca", None)
    else:
      key = None
      cert = None
      ca = None
#     TODO creating a connection with template1 makes other connection fail?
    self.conn = psycopg2.connect(
                                dbname="postgres",
#                                host=self.cfg["db_admin"]["host"],
                                user=self.cfg["db_admin"]["user"],
    #                             password=pwd,    
                                sslrootcert=ca, sslcert=cert, sslkey=key)
    self.conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    self.cur = self.conn.cursor()

  def createConnectionMySQL(self):
    print('DB superuser credentials')
    pwd = getpass.getpass(prompt='Password for user: ')
    self.conn = MySQLdb.connect(host=self.cfg["db_admin"]["host"],
                                user=self.cfg["db_admin"]["user"],
                                passwd=pwd,
                                ssl=self.cfg["db_admin"].get("ssl", None)
                              )
    self.cur = self.conn.cursor()

  def createConnection(self):
    if self.conn is None:
      if (self.cfg["db"]["driver"] == "mysql"):
        self.createConnectionMySQL()
      elif (self.cfg["db"]["driver"] == "pgsql"):
        self.createConnectionPG()
  
  def createUserMySQL(self):
    host = self.cfg["db"]["host"]
    user = self.cfg["db"]["user"]
    #     TODO generate or get passwd
    passwd = self.cfg["db"]["passwd"]
    db = self.cfg["db"]["db"]
    self.cur.execute("create user if not exists %s@%s", (user, host,))
    self.cur.execute("set password for %s@%s = password(%s)", (user, host, passwd,))
    self.cur.execute("""
        grant select, insert, update, delete, create, drop, index, alter,
        create temporary tables on {}.* to %s@%s
        """.format(db), (user, host,))
    self.cur.execute("flush privileges")
    
  def createUserPG(self):
    user = self.cfg["db"]["user"]
    #     TODO generate or get passwd
    passwd = self.cfg["db"]["passwd"]
    self.cur.execute("create user {} nocreaterole nocreatedb encrypted password '{}'".format(user, passwd))
  
  def createDBMySQL(self):
    db = self.cfg["db"]["db"]
    self.cur.execute('create database {};'.format(db))
  
  def createDBPG(self):
    db = self.cfg["db"]["db"]
    user = self.cfg["db"]["user"]
    self.cur.execute('create database {} with owner {}'.format(db, user))

  def setupDB(self):
    print("Setting up DB")
    self.createConnection()
    if (self.cfg["db"]["driver"] == "mysql"):
      self.createDBMySQL()
      self.createUserMySQL()
    elif (self.cfg["db"]["driver"] == "pgsql"):
      self.createUserPG()
      self.createDBPG()
    print("DB ready")

  def Drush(self):
    print("Instaling Drush")
    p = subprocess.run(["composer", "require", "drush/drush"], cwd=self.cfg["path"])
    if(p.returncode == 0):
      print("Drush OK")
    else:
      print(p)

  def DrupalCheck(self):
    if(int(cfg["base"]) > 8):
      self.composerPackages(["--dev", "phpunit/phpunit", "mglaman/drupal-check"])
    else:
      self.composerPackages(["phpunit/phpunit", "^7"])
      self.composerPackages(["--dev", "mglaman/drupal-check"])
      
  def dropUserMySQL(self, user):
    host = self.cfg["db"]["host"]
    self.cur.execute("drop user if exists %s@%s", (user, host,))
  
  def dropUserPG(self, user):
#     self.cur.execute("drop user if exists %s", (user,))
    self.cur.execute("drop user if exists {}".format(user))

  def cleanupDB(self):
    print("Cleaning up DB")
    self.createConnection()
    user = self.cfg["db"]["user"]
    db = self.cfg["db"]["db"]
    self.cur.execute('drop database if exists {};'.format(db))
    if (self.cfg["db"]["driver"] == "mysql"):
      self.dropUserMySQL(self, user)
    elif (self.cfg["db"]["driver"] == "pgsql"):
      self.dropUserPG(user)
    print("DB cleaned up")

  def cleanupDir(self):
    print("Changing permissions")
    for r, d, f in os.walk(cfg["path"]):
      for ld in d:
        ldpath = os.path.join(r, ld)
        ldpermissions = os.stat(ldpath).st_mode
        try:
          os.chmod(ldpath, ldpermissions | stat.S_IWUSR)
        except PermissionError:
          # TODO improve reporting permission errors
          print("PermissionError, check if everything has been deleted")
      for lf in f:
        lfpath = os.path.join(r, lf)
        lfpermission = os.stat(lfpath).st_mode
        try:
          os.chmod(lfpath, lfpermission | stat.S_IWUSR)
        except PermissionError:
          # TODO improve reporting permission errors
          print("PermissionError, check if everything has been deleted")
    print("Removing files")
    shutil.rmtree(cfg["path"])
    print("Files removed")

  def Cleanup(self):
    self.cleanupDB()
    self.cleanupDir()

if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    description='install drupal and a list of modules and themes',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument('-b', '--base',
                        dest='base',
                        metavar='BASEVERSION',
                        help='main base version: 7, 8, 9...',
                        type=int)
  parser.add_argument('-s', '--drush',
                        dest='drush',
                        action='store_const',
                        const=True,
                        default=None,
                        help='install drush')
  parser.add_argument('-g', '--git',
                        dest='git',
                        action='store_true',
                        help='use git HEAD')
  parser.add_argument('-r', '--release',
                        dest='release',
                        metavar='RELEASE',
                        help='minimum required dev version (dev, alpha, beta, rc), stable if omitted')
  parser.add_argument('-m', '--modules',
                        dest='modules',
                        metavar='MODULE,g',
                        nargs='*',
                        help='list of modules to be installed, g|f install from git HEAD')
  parser.add_argument('-t', '--themes',
                        dest='themes',
                        metavar='THEME,g',
                        nargs='*',
                        help='list of themes to be installed, g|f install from git HEAD')
  parser.add_argument('-p', '--path',
                        dest='path',
                        metavar='PATH',
                        help='destination path')
  parser.add_argument('-w', '--workdir',
                        dest='workdir',
                        metavar='PATH',
                        help='working directory and cache')
  parser.add_argument('-d', '--db',
                        dest='db',
                        metavar='USER:PASSWORD@HOST:DB',
                        help='db info')
  parser.add_argument('-c', '--config',
                        dest='config',
                        metavar='FILE',
                        help='path to yaml config file')
  parser.add_argument('-a', '--action',
                        dest='action',
                        choices=('none', 'modules', 'download', 'unpack', 'db', 'install', 'composer', 'wipe'),
                        type=str.lower,
                        help='action [download (just download), install (install modules and themes from tar), composer (install modules and themes with composer)] ')
  parser.add_argument('-e', '--enable',
                        dest='enable_modules',
                        action='store_true',
                        help='enable modules')
  parser.add_argument('-k', '--check',
                        dest='check',
                        action='store_const',
                        const=True,
                        default=None,
                        help='install drupal-check')

  args = parser.parse_args()

  config = args.config
  with open(config) as y:
    cfg = yaml.load(y, Loader=yaml.FullLoader)

  cfg["base"] = cfg.get("base", None) if args.base is None else args.base
  cfg["release"] = cfg.get("release", None) if args.release is None else args.release
  cfg["git"] = cfg.get("git", None) if args.git is None else args.git
  cfg["modules"] = cfg.get("modules", None) if args.modules is None else args.modules
  cfg["themes"] = cfg.get("themes", None) if args.themes is None else args.themes
  cfg["path"] = cfg.get("path", None) if args.path is None else args.path
  cfg["workdir"] = cfg.get("workdir", None) if args.workdir is None else args.workdir
  cfg["drush"] = cfg.get("drush", None) if args.drush is None else args.drush
  cfg["check"] = cfg.get("check", None) if args.check is None else args.check
  cfg["enable_modules"] = cfg.get("enable_modules", None) if args.enable_modules is None else args.enable_modules

  cfg["action"] = cfg.get("action", None) if args.action is None else args.action
  action = cfg["action"]

  g = git.cmd.Git()

  d = Drupal(cfg)
  OB = OnBreak(d)

  d.createWorkingDir()

  if (action == 'modules'):
    d.SaveProjects("modules")
  elif(action == 'themes'):
    d.SaveProjects("themes")
  elif(action == 'download'):
    d.SaveCore()
    d.SaveProjects("modules")
    d.SaveProjects("themes")
  elif(action == 'unpack'):
    d.installCore()
    d.installProjects("modules")
    d.installProjects("themes")
    if(cfg["drush"]):
      d.Drush()
  elif(action == 'db'):
    d.setupDB()
    d.installCore()
    if(cfg["drush"]):
      d.Drush()
    d.installProjects("modules")
    d.installProjects("themes")
  elif(action == 'install'):
    d.setupDB()
    d.installCore()
    d.Drush()
    d.enableCore()
    d.installProjects("modules")
    d.installProjects("themes")
    if(cfg["enable_modules"]):
      d.enableProjects("modules")
      d.enableProjects("themes")
  elif(action == 'composer'):
    d.setupDB()
    d.installCore()
    d.Drush()
    d.enableCore()
    d.composerProjects("modules")
    d.composerProjects("themes")
    if(cfg["enable_modules"]):
      d.enableProjects("modules")
      d.enableProjects("themes")
  elif(action == 'wipe'):
    d.Cleanup()

  if(cfg["check"] and (action != 'wipe')):
    d.DrupalCheck()

  print("FINISH")
