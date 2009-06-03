#!/usr/bin/env python2.5
# (c) Copyright 2009 Cloudera, Inc.

from git_command import GitCommand

class GitRepo(object):
  def __init__(self, path):
    self.path = path

  def command(self, cmdv, **kwargs):
    """
    Runs the given git command and returns the status code returned.

    @param cmdv the git command as a list of args (eg ["diff"])
    """
    return self.command_process(cmdv, **kwargs).Wait()
  
  def check_command(self, cmdv, capture_stdout=False):
    """
    Runs the given git command, and raises an Exception if the status
    code returned is non-zero.
    """
    p = self.command_process(cmdv, capture_stdout=capture_stdout)
    if p.Wait() != 0:
      raise Exception("Command %s returned non-zero exit code: %d" %
                      repr(cmdv), rc)
    if capture_stdout:
      return p.stdout

  def command_process(self, cmdv, **kwargs):
    p = GitCommand(project=None,
                   cwd=self.path,
                   cmdv=cmdv,
                   **kwargs)
    return p
