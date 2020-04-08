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

# import tempfile

import re

import urllib3
import git

import tarfile

import argparse

DREPOSITORY = "https://git.drupal.org/project/drupal.git"
DMREPOSITORY = "https://git.drupalcode.org/project/{}.git"
DFILE = "drupal-{}.tar.gz"
DMFILE = "{}-{}.tar.gz"
DTAR = "https://ftp.drupal.org/files/projects/{}"


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


def getVersion(repo, refilter):
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

def createWorkingDir(workdir):
  if workdir is None:
    pass
  else:
    return "use temp" 
  

class Drupal():
  pass


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    description='install drupal and a list of modules',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument('-b', '--base',
                        dest='base',
                        metavar='BASEVERSION',
                        help='main base version: 7, 8, 9...',
                        type=int)
  parser.add_argument('-r', '--release',
                        dest='release',
                        metavar='RELEASE',
                        help='minimum required dev version (dev, alpha, beta, rc), stable if omitted')
  parser.add_argument('-m', '--modules',
                        dest='modules',
                        metavar='MODULE',
                        nargs='*',
                        help='list of modules to be installed')
  parser.add_argument('-t', '--manual',
                        dest='manual',
                        action='store_true',
                        help='capture adc')
  parser.add_argument('-p', '--path',
                        dest='path',
                        metavar='PATH',
                        required=True,
                        help='path')
  parser.add_argument('-a', '--action',
                        dest='action',
                        choices=('download', 'composer', 'install'),
#                         metavar='ACTION',
                        type=str.lower,
#                         required=True,
                        help='action [download (just download), install (install modules and themes from tar), composer (install modules and themes with composer)] ')

  args = parser.parse_args()

  drupal = Drupal()
  OB = OnBreak(drupal)

  base = args.base
  release = args.release
  modules = args.modules
  action = args.action

  releasea = { 'dev': 0, 'alpha': 1, 'beta': 2, 'rc': 3, None: 4 }
  g = git.cmd.Git()
  # 9.0.0-beta2
  # 5 4 3    21
  # 7.0-unstable-10 not supported
  # 7.0-alpha7
  drerev = re.compile(r"[^ \t]+[ \t]+refs/tags/(([0-9]+)\.([0-9]+)\.?([0-9]+)?-?(dev|alpha|beta|rc)?([0-9]+)?).*")
  dmrerev = re.compile(r"[^ \t]+[ \t]+refs/tags/(([0-9]+)\.x-([0-9]+)?\.?([0-9]+)?-?(dev|alpha|beta|rc)?([0-9]+)?).*")
  a = {}
  va = []

  rev_temp = getVersion(DREPOSITORY, drerev)
  if(base is not None):
    rev_temp = [v for v in rev_temp if (v[1][0] >= base * 100 ** 4 and v[1][0] < (base + 1) * 100 ** 4)]
  rev_temp = [v for v in rev_temp if (v[1][1][1] >= releasea[release])]

  file = DFILE.format(rev_temp[-1][0])
  
  url = DTAR.format(file)
  print(url)
  
  if modules is not None:
    for m in modules:
      a = {}
      va = []
      dmrepo = DMREPOSITORY.format(m)
      rev_temp = getVersion(dmrepo, dmrerev)
      if(base is not None):
        rev_temp = [v for v in rev_temp if (v[1][0] >= base * 100 ** 4 and v[1][0] < (base + 1) * 100 ** 4)]
      rev_temp = [v for v in rev_temp if (v[1][1][1] >= releasea[release])]
  
      file = DMFILE.format(m, rev_temp[-1][0])
      url = DTAR.format(file)
      print(url)

#   http = urllib3.PoolManager()
#   r = http.request('GET', url)
#   f = open(file, 'wb')
#   f.write(r.data)
#   f.close

  print("OK")

