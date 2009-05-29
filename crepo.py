#!/usr/bin/env python2.5
# (c) Copyright 2009 Cloudera, Inc.

import os
import sys
import optparse
import manifest
import logging
from git_command import GitCommand
from git_config import GitConfig

def load_manifest():
  return manifest.load_manifest("manifest.json")

def help(args):
  """shows some help

  asdfsaddsf"""
  print "hi there" + repr(args)

def workdir_for_project(p):
  return p.dir # TODO(todd) add root to manifest

def init(args):
  """Initializes repository"""
  man = load_manifest()

  for (name, project) in man.projects.iteritems():
    logging.warn("Initializing project: %s" % name)
    clone_remote = man.remotes[project.from_remote]
    clone_url = clone_remote.fetch % name
    p = GitCommand(None, ["clone", clone_url, project.dir])
    p.Wait()

def checkout_branches(args):
  """Checks out the tracking branches listed in the manifest."""
  man = load_manifest()
  for (name, project) in man.projects.iteritems():
    logging.warn("Checking out tracking branch in project: %s" % name)
    cwd = workdir_for_project(project)
    gitdir = os.path.join(cwd, ".git")
    if not os.path.isdir(gitdir):
      raise Exception("no git dir at " + gitdir)
    conf = GitConfig.ForRepository()
    print conf.GetBranch(project.refspec)                   


COMMANDS = {
  'help': help,
  'init': init,
  'checkout-branches': checkout_branches
  }

def usage():
  print >>sys.stderr, "you screwed up. here are the commands:"
  print >>sys.stderr

  for (command, function) in COMMANDS.iteritems():
    print >>sys.stderr, "  %s\t%s" % (command, function.__doc__.split("\n")[0] or "no docs")
  sys.exit(1)

def main():
  args = sys.argv[1:]
  if len(args) == 0 or args[0] not in COMMANDS:
    usage()
  command = COMMANDS[args[0]]
  command.__call__(args[1:])

if __name__ == "__main__":
  main()
