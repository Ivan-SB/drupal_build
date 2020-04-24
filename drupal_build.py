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

import yaml
import argparse
import getpass

DREPOSITORY = "https://git.drupal.org/project/drupal.git"
DMREPOSITORY = "https://git.drupalcode.org/project/{}.git"
DFILE = "drupal-{}.tar.gz"
DDIR = "drupal-{}"
DMFILE = "{}-{}.tar.gz"
DTAR = "https://ftp.drupal.org/files/projects/{}"

releasea = { 'dev': 0, 'alpha': 1, 'beta': 2, 'rc': 3, None: 4 }

# 9.0.0-beta2
# 5 4 3    21
# 7.0-unstable-10 not supported
# 7.0-alpha7
drerev = re.compile(r"[^ \t]+[ \t]+refs/tags/(([0-9]+)\.([0-9]+)\.?([0-9]+)?-?(dev|alpha|beta|rc)?([0-9]+)?).*")
dmrerev = re.compile(r"[^ \t]+[ \t]+refs/tags/(([0-9]+)\.x-([0-9]+)?\.?([0-9]+)?-?(dev|alpha|beta|rc)?([0-9]+)?).*")


class OnBreak():
  kill_now = False

  def __init__(self, s2S):
    self._s2S = s2S
    signal.signal(signal.SIGINT, self.exit_stoptasks)
    signal.signal(signal.SIGTERM, self.exit_stoptasks)

  def exit_stoptasks(self, signum, frame):
#     SOME ACTION
    sys.exit(0)


def zeroOnNone(x):
  return int(x) if x is not None else 0


class Drupal():

  def __init__(self, cfg):
    self.cfg = cfg
    self.conn = None
    self.http = None

  def gitFilter(self, vl):
    if(self.cfg["base"] is not None):
      vl = [v for v in vl if (v[1][0] >= self.cfg["base"] * 100 ** 4 and v[1][0] < (self.cfg["base"] + 1) * 100 ** 4)]
    vl = [v for v in vl if (v[1][1][1] >= releasea[self.cfg["release"]])]
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

  def getVersion(self, repo, refilter):
    a = {}
    va = []
    for ref in g.ls_remote(repo).split('\n'):
      dmatch = re.search(refilter, ref)
      if(dmatch is not None):
        va = [ zeroOnNone(dmatch.group(6)),
            zeroOnNone(releasea[dmatch.group(5)]),
            zeroOnNone(dmatch.group(4)),
            zeroOnNone(dmatch.group(3)),
            zeroOnNone(dmatch.group(2))]
        v = va[0] + 100 * va[1] + 100 ** 2 * va[2] + 100 ** 3 * va[3] + 100 ** 4 * va[4]
        a[dmatch.group(1)] = (v, va)
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
    self.dcore = d.getVersion(DREPOSITORY, drerev)
    self.dcoref = d.gitFilter(self.dcore)
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
    dbstring="mysql://{}:{}@{}/{}".format(self.cfg["db"]["user"],
                                                   self.cfg["db"]["passwd"],
                                                   self.cfg["db"]["host"],
                                                   self.cfg["db"]["db"])
#     drush seems to need shell
    sstring=" ".join(("drush",
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

  def SaveModule(self):
    if self.cfg.get("modules", None) is not None:
      for m in self.cfg['modules']:
        print("Saving module {}".format(m))
        dmrepo = DMREPOSITORY.format(m)
        dmodules = self.getVersion(dmrepo, dmrerev)
        dmodulesf = self.gitFilter(dmodules)
        rfile = DMFILE.format(m, dmodulesf[-1][0])
        file = os.path.join(self.cfg["workdir"], "modules", rfile)
        if(not os.path.exists(file)):
          url = DTAR.format(rfile)
          self.SaveFile(url, file)
          print("Module {} saved".format(m))
        else:
          print("Module {} from cache".format(m))
        yield {"module": m, "file": file}
    else:
      return

  def SaveModules(self):
    for _ in self.SaveModule():
      pass

  def installModules(self):
    basepath = os.path.normpath(self.cfg["path"])
    for m in self.SaveModule():
      print("Unpacking module {}".format(m["module"]))
      modulepath = os.path.join(basepath, "modules/contrib")
      tar = tarfile.open(m['file'], 'r:gz')
      tar.extractall(path=modulepath)
      print("Module {} unpacked".format(m["module"]))

  def enableModules(self):
    pass
#     if self.cfg.get("modules", None) is not None:
#       mod = ",".join(self.cfg["modules"])
#       p = subprocess.run(["drush", "en", mod], cwd=self.cfg["path"])
#       if(p.returncode == 0):
#         print("Modules OK")
#       else:
#         print(p)

  def composerPackages(self, packages):
    crequire = ["composer", "require"]
    cfgdir = os.path.join(self.cfg["path"], "sites", "default")
    pstring = ", ".join(packages)
    st_mode = os.stat(cfgdir).st_mode
    os.chmod(cfgdir, st_mode | stat.S_IWUSR | stat.S_IWGRP)
    print("Installing packages {} via composer".format(pstring))
    crequire.extend(packages)
    p = subprocess.run(crequire, cwd=self.cfg["path"])
    if(p.returncode == 0):
      print("Composer packages {} OK".format(pstring))
    else:
      print(p)
    os.chmod(cfgdir, st_mode)

  def composerModules(self):
    if self.cfg.get("modules", None) is not None:
      packages = list(map(lambda m: "drupal/{}".format(m), self.cfg["modules"]))
      self.composerPackages(packages)

  def createConnection(self):
    if self.conn is None:
      adminuser = self.cfg["db_admin"]["user"]
      connhost = self.cfg["db_admin"]["host"]
      ssl = self.cfg["db_admin"].get("ssl", None)
      print('DB superuser credentials')
      pwd = getpass.getpass(prompt='Password for user: ')
      self.conn = MySQLdb.connect(host=connhost, user=adminuser, passwd=pwd,
                                ssl=ssl
                                )
      self.cur = self.conn.cursor()

  def createUser(self):
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

  def createDB(self):
    db = self.cfg["db"]["db"]
    self.cur.execute('create database if not exists {};'.format(db))

  def setupDB(self):
    print("Setting up DB")
    self.createConnection()
    self.createDB()
    self.createUser()
    print("DB ready")

  def Drush(self):
    p = subprocess.run(["composer", "require", "drush/drush"], cwd=self.cfg["path"])
    if(p.returncode == 0):
      print("Drush OK")
    else:
      print(p)
  
  def DrupalCheck(self):
#     TODO passing --dev should be decided by argument passed 
    self.composerPackages(["--dev", "phpunit/phpunit", "mglaman/drupal-check"])
  
  def cleanupDB(self):
    print("Cleaning up DB")
    self.createConnection()
    host = self.cfg["db"]["host"]
    user = self.cfg["db"]["user"]
    db = self.cfg["db"]["db"]
    self.cur.execute("drop user %s@%s", (user, host,))
    self.cur.execute('drop database {};'.format(db))
    print("DB cleaned up")
      
  def Cleanup(self):
    self.cleanupDB()
#     TODO files may be write-protected, not enough to change ownership
    print("Removing files")
    shutil.rmtree(cfg["path"])
    print("Files removed")

if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    description='install drupal and a list of modules',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument('-b', '--base',
                        dest='base',
                        metavar='BASEVERSION',
                        help='main base version: 7, 8, 9...',
                        type=int)
  parser.add_argument('-s', '--drush',
                        dest='drush',
                        action='store_true',
                        help='install drush')
  parser.add_argument('-r', '--release',
                        dest='release',
                        metavar='RELEASE',
                        help='minimum required dev version (dev, alpha, beta, rc), stable if omitted')
  parser.add_argument('-m', '--modules',
                        dest='modules',
                        metavar='MODULE',
                        nargs='*',
                        help='list of modules to be installed')
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
                        choices=('module', 'download', 'unpack', 'db', 'install', 'composer', 'wipe'),
                        type=str.lower,
                        default='download',
#                         required=True,
                        help='action [download (just download), install (install modules and themes from tar), composer (install modules and themes with composer)] ')
  parser.add_argument('-e', '--enable',
                        dest='enable_modules',
                        action='store_true',
                        help='enable modules')
  parser.add_argument('-k', '--check',
                        dest='check',
                        action='store_true',
                        help='install drupal-check')

  args = parser.parse_args()

  config = args.config
  with open(config) as y:
    cfg = yaml.load(y, Loader=yaml.FullLoader)

  cfg["base"] = cfg.get("base", None) if args.base is None else args.base
  cfg["release"] = cfg.get("release", None) if args.release is None else args.release
  cfg["modules"] = cfg.get("modules", None) if args.modules is None else args.modules
  cfg["path"] = cfg.get("path", None) if args.path is None else args.path
  cfg["workdir"] = cfg.get("workdir", None) if args.workdir is None else args.workdir
  cfg["drush"] = cfg.get("drush", None) if args.drush is None else args.drush
  cfg["check"] = cfg.get("check", None) if args.check is None else args.check
  cfg["enable_modules"] = cfg.get("enable_modules", None) if args.enable_modules is None else args.enable_modules
  action = args.action

  g = git.cmd.Git()

  d = Drupal(cfg)
  OB = OnBreak(d)

  d.createWorkingDir()

  if (action == 'module'):
    d.SaveModules()
  elif(action == 'download'):
    d.SaveCore()
    d.SaveModules()
  elif(action == 'unpack'):
    d.installCore()
    d.installModules()
    if(cfg["drush"]):
      d.Drush()
  elif(action == 'db'):
    d.setupDB()
    d.installCore()
    if(cfg["drush"]):
      d.Drush()
    d.installModules()
  elif(action == 'install'):
    d.setupDB()
    d.installCore()
    d.Drush()
    d.enableCore()
    d.installModules()
    if(cfg["enable_modules"]):
      d.enableModules()
  elif(action == 'composer'):
    d.setupDB()
    d.installCore()
    d.Drush()
    d.enableCore()
    d.composerModules()
    if(cfg["enable_modules"]):
      d.enableModules()
  elif(action == 'wipe'):
    d.Cleanup()
    
  if(cfg["check"]):
    d.DrupalCheck()

  print("FINISH")
