#!/usr/bin/env python3

"""
https://docs.python.org/3/library/tarfile.html
https://janakiev.com/blog/python-shell-commands/

import subprocess
process = subprocess.Popen(['echo', 'More output'],
                     stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE)
stdout, stderr = process.communicate()
stdout, stderr

with open('test.txt', 'w') as f:
    process = subprocess.Popen(['ls', '-l'], stdout=f)
"""

import os
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

  def __init__(self, config, path, workdir):
    self.config = config
    self.path = path
    self.workdir = workdir
    self.http = None

  def gitFilter(self, vl):
    if(base is not None):
      vl = [v for v in vl if (v[1][0] >= base * 100 ** 4 and v[1][0] < (base + 1) * 100 ** 4)]
    vl = [v for v in vl if (v[1][1][1] >= releasea[release])]
    return vl

  def createDirs(self, base):
    os.makedirs(os.path.join(base, "core"), exist_ok=True)
    os.makedirs(os.path.join(base, "modules"), exist_ok=True)
    os.makedirs(os.path.join(base, "themes"), exist_ok=True)
    return base

  def createWorkingDir(self):
    if self.workdir is None:
      self.workdir = tempfile.mkdtemp(prefix="drupal_")
      self.createDirs(self.workdir)
    else:
      self.workdir = os.path.join(base, "drupal")
      os.makedirs(self.workdir, exist_ok=True)
      self.createDirs(self.workdir)

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
    self.dcore = d.getVersion(DREPOSITORY, drerev)
    self.dcoref = d.gitFilter(self.dcore)
    rfile = DFILE.format(self.dcoref[-1][0])
    url = DTAR.format(rfile)
    file = os.path.join(self.workdir, "core", rfile)
    self.SaveFile(url, file)
    return file

  def installCore(self):
    file = self.SaveCore()
    tar = tarfile.open(file, 'r:gz')
    # TODO check if path exists otherwise create it
    basepath = os.path.split(os.path.normpath(self.path))[0]
    tar.extractall(path=basepath)
    tar.close()
    os.rename(os.path.join(basepath, DDIR.format(self.dcoref[-1][0])), self.path)

  def SaveModule(self, modules):
    if modules is not None:
      for m in modules:
        dmrepo = DMREPOSITORY.format(m)
        dmodules = d.getVersion(dmrepo, dmrerev)
        dmodulesf = d.gitFilter(dmodules)
        rfile = DMFILE.format(m, dmodulesf[-1][0])
        url = DTAR.format(rfile)
        file = os.path.join(self.workdir, "modules", rfile)
        self.SaveFile(url, file)
        yield (m, file)

  def SaveModules(self, modules):
    for _ in self.SaveModule(modules):
      pass

  def installModules(self):
    pass
#     basepath = os.path.split(os.path.normpath(self.path))[0]
#     for i in self.SaveModules(modules):
#       tar.extractall(path=basepath)

  def composerModules(self):
    pass

  def createConnection(self):
    adminuser = self.config["db_admin"]["user"]
    connhost = self.config["db_admin"]["host"]
    ssl = self.config["db_admin"]["ssl"]
    
    user = self.config["db"]["user"]
    db = self.config["db"]["db"]
    passwd = "pino"
    host = "localhost"
    
    print('DB superuser credentials')
    pwd = getpass.getpass(prompt='Password for user: ')
    self.conn = MySQLdb.connect(host=connhost, user=adminuser, passwd=pwd,
                                ssl=ssl
                                )
    cur = self.conn.cursor()
    cur.execute('create database if not exists {};'.format(db))
    cur.execute("create user if not exists %s@%s", (user, host,))
#     cur.execute("set password for %s@%s = password(%s)", (user, host, passwd,))
#     cur.execute("""
#       grant select, insert, update, delete, create, drop, index, alter,
#       create temporary tables on %s.* to %s@%s
#     """, (db, user, host,))
    cur.execute("flush privileges")

  def createUser(self):
    pass

  def Drush(self):
    p = subprocess.run(["composer", "require", "drush/drush"], cwd=self.path)
    if(p == 0): print("Drush OK")


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    description='install drupal and a list of modules',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument('-b', '--base',
                        dest='base',
                        metavar='BASEVERSION',
                        help='main base version: 7, 8, 9...',
                        type=int)
  parser.add_argument('-d', '--db',
                        dest='db',
                        metavar='DB',
                        help='db connection JSON file')
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
                        required=True,
                        help='destination path')
  parser.add_argument('-w', '--workdir',
                        dest='workdir',
                        metavar='PATH',
                        help='working directory and cache')
  parser.add_argument('-c', '--config',
                        dest='config',
                        metavar='FILE',
                        help='path to yaml config file')
  parser.add_argument('-a', '--action',
                        dest='action',
                        choices=('download', 'composer', 'install'),
                        type=str.lower,
                        default='download',
#                         required=True,
                        help='action [download (just download), install (install modules and themes from tar), composer (install modules and themes with composer)] ')

  args = parser.parse_args()

  base = args.base
  release = args.release
  modules = args.modules
  action = args.action
  path = args.path
  workdir = args.workdir
  config = args.config

  g = git.cmd.Git()
  
  with open(config) as y:
    cfg = yaml.load(y, Loader=yaml.FullLoader)

  d = Drupal(cfg, path, workdir)
  OB = OnBreak(d)

  d.createConnection()
  exit()

  d.createWorkingDir()

  if (action == 'download'):
    d.SaveCore()
    d.SaveModules(modules)
  elif(action == 'install'):
    d.installCore()
#     first install drupal and DB, then install modules
    d.installModules()
    if(args.drush):
      d.Drush()
  elif(action == 'composer'):
    d.installCore()
    d.composerModules()
    if(args.drush):
      d.Drush()

  print("OK")

