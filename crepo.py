#!/usr/bin/env python2.5
# (c) Copyright 2009 Cloudera, Inc.

import os
import sys
import optparse
import manifest
import logging
from git_command import GitCommand
from git_config import GitConfig


#TODO(todd) default_revision should be default_refspec

def load_manifest():
  return manifest.load_manifest("manifest.json")

def help(args):
  """Shows help"""
  if len(args) == 1:
    command = args[0]
    doc = COMMANDS[command].__doc__
    if doc:
      print >>sys.stderr, "Help for command %s:\n" % command
      print >>sys.stderr, doc
      sys.exit(1)
  usage()

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

  checkout_branches([])

def ensure_remotes(args):
  """Ensure that remotes are set up"""
  man = load_manifest()
  for (proj_name, project) in man.projects.iteritems():
    cwd = workdir_for_project(project)
    for remote_name in project.remotes:
      remote = man.remotes[remote_name]
      new_url = remote.fetch % proj_name
      p = GitCommand(None, ["config", "--get", "remote.%s.url" % remote_name],
                     cwd=cwd, capture_stdout=True)
      if p.Wait() == 0:
        cur_url = p.stdout.strip()
        if cur_url != new_url:
          p = GitCommand(None, ["config", "--set", "remote.%s.url" % remote_name,
                                new_url],
                         cwd=cwd)
          p.Wait()
      else:
        p = GitCommand(None, ["remote", "add", remote_name,
                              new_url],
                       cwd=cwd)
        p.Wait()

def ensure_tracking_branches(args):
  """Ensures that the tracking branches are set up"""
  man = load_manifest()
  for (name, project) in man.projects.iteritems():
    cwd = workdir_for_project(project)

    p = GitCommand(project=None,
                   cwd=cwd,
                   cmdv=["rev-parse", "--verify", "-q", project.refspec],
                   capture_stdout=True)
    # Make the tracking branch if it doesn't exist
    if p.Wait() != 0:
      logging.warn("Branch %s does not exist in project %s. checking out." %
                   (project.refspec, name))
      p = GitCommand(project=None,
                     cwd=cwd,
                     cmdv=["branch", "--track",
                           project.tracking_branch, project.remote_refspec])  

def check_dirty(args):
  """Prints output if any projects have dirty working dirs or indexes."""
  man = load_manifest()
  any_dirty = False
  for (name, project) in man.projects.iteritems():
    cwd = workdir_for_project(project)
    p = GitCommand(project=None, cwd=cwd,
                   cmdv=["diff", "--quiet"])
    workdir_dirty = p.Wait()

    p = GitCommand(project=None, cwd=cwd,
                   cmdv=["diff", "--quiet", "--cached"])
    index_dirty = p.Wait()

    if workdir_dirty:
      print "Project %s has a dirty working directory (unstaged changes)." % name
    if index_dirty:
      print "Project %s has a dirty index (staged changes)." % name

    any_dirty = any_dirty or workdir_dirty or index_dirty

  return any_dirty

def checkout_branches(args):
  """Checks out the tracking branches listed in the manifest."""

  ensure_tracking_branches([])
  if check_dirty([]) and '-f' not in args:
    raise Exception("Cannot checkout new branches with dirty projects.")
  
  man = load_manifest()
  for (name, project) in man.projects.iteritems():
    print >>sys.stderr, "Checking out tracking branch in project: %s" % name
    cwd = workdir_for_project(project)
    # Check that sucker out
    p = GitCommand(project=None, cwd=cwd,
                   cmdv=["checkout", project.tracking_branch])
    p.Wait()

def hard_reset_branches(args):
  """Hard-resets your tracking branches to match the remotes."""
  checkout_branches(args)
  man = load_manifest()
  for (name, project) in man.projects.iteritems():
    print >>sys.stderr, "Hard resetting tracking branch in project: %s" % name
    cwd = workdir_for_project(project)
    # Check that sucker out
    p = GitCommand(project=None, cwd=cwd,
                   cmdv=["reset", "--hard", project.remote_refspec])
    p.Wait()
  

def do_all_projects(args):
  """Run the given git-command in every project

  Pass -p to do it in parallel"""
  man = load_manifest()

  if args[0] == '-p':
    parallel = True
    del args[0]
  else:
    parallel = False

  for (name, project) in man.projects.iteritems():
    cwd = workdir_for_project(project)
    print >>sys.stderr, "In project: ", name, " running ", " ".join(args)
    p = GitCommand(project=None,
                   cwd=cwd,
                   cmdv=args)
    if not parallel:
      p.Wait()
    print >>sys.stderr

def do_all_projects_remotes(args):
  """Run the given git-command in every project, once for each remote.

  Pass -p to do it in parallel"""
  man = load_manifest()

  if args[0] == '-p':
    parallel = True
    del args[0]
  else:
    parallel = False

  for (name, project) in man.projects.iteritems():
    cwd = workdir_for_project(project)
    for remote_name in project.remotes.keys():
      cmd = args + [remote_name]
      print >>sys.stderr, "In project: ", name, " running ", " ".join(cmd)
      p = GitCommand(project=None,
                     cwd=cwd,
                     cmdv=cmd)
      if not parallel:
        p.Wait()
      print >>sys.stderr


def fetch(args):
  """Run git-fetch in every project"""
  do_all_projects_remotes(["fetch"])

def pull(args):
  """Run git-pull in every project"""
  do_all_projects_remotes(["pull"])

def _tracking_status(dir, local_branch, remote_branch):
  """
  Return a tuple (left_commits, right_commits). The
  first element is the number of commits in the local branch and not in remote.
  The second element is the other direction
  """
  p = GitCommand(project=None, cwd=dir,
                 cmdv=["rev-list", "--left-right", "%s...%s" % (local_branch, remote_branch)],
                 capture_stdout=True)
  p.Wait()
  commits = p.stdout.strip().split("\n")
  left_commits,right_commits = (0,0)
  for commit in commits:
    if not commit: continue
    if commit[0] == '<':
      left_commits += 1
    else:
      right_commits += 1

  return (left_commits, right_commits)

def status(args):
  """Shows where your branches have diverged from the specified remotes."""
  ensure_tracking_branches([])
  man = load_manifest()
  first = True
  for (name, project) in man.projects.iteritems():
    if not first: print
    first = False
    
    print "Project %s:" % name
    cwd = workdir_for_project(project)
    (left, right) = _tracking_status(cwd, project.tracking_branch, project.remote_refspec)
    if (left,right) == (0,0):
      print "  Your tracking branch and remote branches are up to date."""
    elif left == 0:
      print "  The remote branch %s is %d revisions ahead of tracking branch %s." % \
            (project.remote_refspec, right, project.tracking_branch)
    elif right == 0:
      print ("  Your tracking branch %s is %s revisions ahead of\n" +
             "  remote branch %s.") % \
             (project.tracking_branch, left, project.remote_refspec)
    else:
      print ("  Your local branch %s and remote branch %s\n" +
             "  have diverged by %d and %d revisions.") % \
             (project.tracking_branch, project.remote_branch, left, right)


COMMANDS = {
  'help': help,
  'init': init,
  'checkout': checkout_branches,
  'hard-reset': hard_reset_branches,
  'do-all': do_all_projects,
  'fetch': fetch,
  'pull': pull,
  'status': status,
  'check-dirty': check_dirty,
  'setup-remotes': ensure_remotes
  }

def usage():
  print >>sys.stderr, "you screwed up. here are the commands:"
  print >>sys.stderr

  max_comlen = 0
  out = []
  for (command, function) in COMMANDS.iteritems():
    docs = function.__doc__ or "no docs"
    docs = docs.split("\n")[0]
    if len(command) > max_comlen:
      max_comlen = len(command)

    out.append( (command, docs) )

  for (command, docs) in sorted(out):
    command += " " * (max_comlen - len(command))
    available_len = 80 - max_comlen - 5
    output_docs = []
    cur_line = ""
    for word in docs.split(" "):
      if cur_line and len(cur_line + " " + word) > available_len:
        output_docs.append(cur_line)
        cur_line = " " * (max_comlen + 5)
      cur_line += " " + word
    if cur_line: output_docs.append(cur_line)
    print >>sys.stderr, "  %s   %s" % (command, "\n".join(output_docs))
  sys.exit(1)

def main():
  args = sys.argv[1:]
  if len(args) == 0 or args[0] not in COMMANDS:
    usage()
  command = COMMANDS[args[0]]
  sys.exit(command.__call__(args[1:]))

if __name__ == "__main__":
  main()
