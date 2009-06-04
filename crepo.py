#!/usr/bin/env python2.5
# (c) Copyright 2009 Cloudera, Inc.

import os
import sys
import optparse
import manifest
import logging
import textwrap
from git_command import GitCommand
from git_repo import GitRepo

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
    p = GitCommand(None, ["clone", "-o", project.from_remote, "-n", clone_url, project.dir])
    p.Wait()

    repo = GitRepo(workdir_for_project(project))
    if repo.command(["show-ref", "-q", "HEAD"]) != 0:
      # There is no HEAD (maybe origin/master doesnt exist) so check out the tracking
      # branch
      repo.check_command(["checkout", "--track", "-b", project.tracking_branch,
                        project.remote_refspec])
    else:
      repo.check_command(["checkout"])

  ensure_remotes([])
  fetch([])
  checkout_branches([])

def ensure_remotes(args):
  """Ensure that remotes are set up"""
  man = load_manifest()
  for (proj_name, project) in man.projects.iteritems():
    repo = GitRepo(workdir_for_project(project))
    for remote_name in project.remotes:
      remote = man.remotes[remote_name]
      new_url = remote.fetch % proj_name

      p = repo.command_process(["config", "--get", "remote.%s.url" % remote_name],
                               capture_stdout=True)
      if p.Wait() == 0:
        cur_url = p.stdout.strip()
        if cur_url != new_url:
          repo.check_command(["config", "--set", "remote.%s.url" % remote_name, new_url])
      else:
        repo.check_command(["remote", "add", remote_name, new_url])

def ensure_tracking_branches(args):
  """Ensures that the tracking branches are set up"""
  man = load_manifest()
  for (name, project) in man.projects.iteritems():
    repo = GitRepo(workdir_for_project(project))
    branch_missing = repo.command(
      ["rev-parse", "--verify", "-q", project.refspec],
      capture_stdout=True)
    
    if branch_missing:
      logging.warn("Branch %s does not exist in project %s. checking out." %
                   (project.refspec, name))
      repo.command(["branch", "--track",
                    project.tracking_branch, project.remote_refspec])

def check_dirty(args):
  """Prints output if any projects have dirty working dirs or indexes."""
  man = load_manifest()
  any_dirty = False
  for (name, project) in man.projects.iteritems():
    repo = GitRepo(workdir_for_project(project))
    any_dirty = check_dirty_repo(repo) or any_dirty
  return any_dirty

def check_dirty_repo(repo, indent=0):
  workdir_dirty = repo.is_workdir_dirty()
  index_dirty = repo.is_index_dirty()

  name = repo.name
  if workdir_dirty:
    print " " * indent + "Project %s has a dirty working directory (unstaged changes)." % name
  if index_dirty:
    print " " * indent + "Project %s has a dirty index (staged changes)." % name

  return workdir_dirty or index_dirty


def checkout_branches(args):
  """Checks out the tracking branches listed in the manifest."""

  ensure_tracking_branches([])
  if check_dirty([]) and '-f' not in args:
    raise Exception("Cannot checkout new branches with dirty projects.")
  
  man = load_manifest()
  for (name, project) in man.projects.iteritems():
    print >>sys.stderr, "Checking out tracking branch in project: %s" % name
    repo = GitRepo(workdir_for_project(project))
    # Check that sucker out
    repo.check_command(["checkout", project.tracking_branch])

def hard_reset_branches(args):
  """Hard-resets your tracking branches to match the remotes."""
  checkout_branches(args)
  man = load_manifest()
  for (name, project) in man.projects.iteritems():
    print >>sys.stderr, "Hard resetting tracking branch in project: %s" % name
    repo = GitRepo(workdir_for_project(project))
    repo.check_command(["reset", "--hard", project.remote_refspec])
  

def do_all_projects(args):
  """Run the given git-command in every project

  Pass -p to do it in parallel"""
  man = load_manifest()

  if args[0] == '-p':
    parallel = True
    del args[0]
  else:
    parallel = False

  towait = []

  for (name, project) in man.projects.iteritems():
    repo = GitRepo(workdir_for_project(project))
    print >>sys.stderr, "In project: ", name, " running ", " ".join(args)
    p = repo.command_process(args)
    if not parallel:
      p.Wait()
      print >>sys.stderr
    else:
      towait.append(p)

  for p in towait:
    p.Wait()
      
def do_all_projects_remotes(args):
  """Run the given git-command in every project, once for each remote.

  Pass -p to do it in parallel"""
  man = load_manifest()

  if args[0] == '-p':
    parallel = True
    del args[0]
  else:
    parallel = False
  towait = []

  for (name, project) in man.projects.iteritems():
    repo = GitRepo(workdir_for_project(project))
    for remote_name in project.remotes.keys():
      cmd = args + [remote_name]
      print >>sys.stderr, "In project: ", name, " running ", " ".join(cmd)
      p = repo.command_process(cmd)
      if not parallel:
        p.Wait()
        print >>sys.stderr
      else:
        towait.append(p)
  for p in towait:
    p.Wait()


def fetch(args):
  """Run git-fetch in every project"""
  do_all_projects_remotes(args + ["fetch"])

def pull(args):
  """Run git-pull in every project"""
  do_all_projects(args + ["pull"])

def _format_tracking(local_branch, remote_branch,
                     left, right):
  """
  Takes a tuple returned by repo.tracking_status and outputs a nice string
  describing the state of the repository.
  """
  if (left,right) == (0,0):
    return "Your tracking branch and remote branches are up to date."
  elif left == 0:
    return ("The remote branch %s is %d revisions ahead of tracking branch %s." %
            (remote_branch, right, local_branch))
  elif right == 0:
    return ("Your tracking branch %s is %s revisions ahead of remote branch %s." %
            (local_branch, left, remote_branch))
  else:
    return ("Your local branch %s and remote branch %s have diverged by " +
            "%d and %d revisions." %
            (local_branch, project.remote_branch, left, right))

def project_status(project, indent=0):
  repo = GitRepo(workdir_for_project(project))
  repo_status(repo, project.tracking_branch, project.remote_refspec, indent=indent)

def repo_status(repo, tracking_branch, remote_refspec, indent=0):
  # Make sure the right branch is checked out
  if repo.current_branch() != tracking_branch:
    print " " * indent + ("Checked out branch is %s instead of %s" %
                         (repo.current_branch(), tracking_branch))
  # Print tracking branch status
  (left, right) = repo.tracking_status(tracking_branch, remote_refspec)
  text = _format_tracking(tracking_branch, remote_refspec, left, right)
  indent_str = " " * indent
  print textwrap.fill(text, initial_indent=indent_str, subsequent_indent=indent_str)

def status(args):
  """Shows where your branches have diverged from the specified remotes."""
  ensure_tracking_branches([])
  man = load_manifest()
  first = True
  for (name, project) in man.projects.iteritems():
    if not first: print
    first = False

    print "Project %s:" % name
    project_status(project, indent=2)
    check_dirty_repo(GitRepo(workdir_for_project(project)),
                     indent=2)

  man_repo = get_manifest_repo()
  if man_repo:
    print
    print "Manifest repo:"
    repo_status(man_repo,
                man_repo.current_branch(),
                "origin/" + man_repo.current_branch(),
                indent=2)
    check_dirty_repo(man_repo, indent=2)


def get_manifest_repo():
  """
  Return a GitRepo object pointing to the repository that contains
  the crepo manifest.
  """
  # root dir is cwd for now
  cdup = GitRepo(".").command_process(["rev-parse", "--show-cdup"],
                                      capture_stdout=True,
                                      capture_stderr=True)
  if cdup.Wait() != 0:
    return None
  cdup_path = cdup.stdout.strip()
  if cdup_path:
    return GitRepo(cdup_path)
  else:
    return GitRepo(".")

def dump_refs(args):
  """
  Output a list of all repositories along with their
  checked out branches and their hashes.
  """
  man = load_manifest()
  first = True
  for (name, project) in man.projects.iteritems():
    if not first: print
    first = False
    print "Project %s:" % name

    repo = GitRepo(workdir_for_project(project))
    print "  HEAD: %s" % repo.rev_parse("HEAD")
    print "  Symbolic: %s" % repo.current_branch()
    project_status(project, indent=2)

  repo = get_manifest_repo()
  if repo:
    print
    print "Manifest repo:"
    print "  HEAD: %s" % repo.rev_parse("HEAD")
    print "  Symbolic: %s" % repo.current_branch()
    repo_status(repo,
                repo.current_branch(),
                "origin/" + repo.current_branch(),
                indent=2)
    check_dirty_repo(repo, indent=2)
  


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
  'setup-remotes': ensure_remotes,
  'dump-refs': dump_refs
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
