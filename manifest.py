#!/usr/bin/env python2.5
# (c) Copyright 2009 Cloudera, Inc.
import simplejson
import os

class Manifest(object):
  def __init__(self,
               remotes=[],
               projects={},
               default_refspec="master",
               default_remote="origin"):
    self.remotes = remotes
    self.projects = projects
    self.default_refspec = default_refspec
    self.default_remote = default_remote

  @staticmethod
  def from_dict(data):
    remotes = dict([(name, Remote.from_dict(d)) for (name, d) in data.get('remotes', {}).iteritems()])

    default_remote = data.get("default_remote", "origin")
    assert default_remote in remotes

    projects = dict([
      (name, Project.from_dict(name=name, data=d, remotes=remotes, default_remote=default_remote))
      for (name, d) in data.get('projects', {}).iteritems()])
    
    return Manifest(
      default_refspec=data.get("default-revision", "master"),
      default_remote=default_remote,
      projects=projects,
      remotes=remotes)

  def to_json(self):
    return simplejson.dumps(self.data_for_json(), indent=2)

  def data_for_json(self):
    return {
      "default-revision": self.default_refspec,
      "default-remote": self.default_remote,
      "remotes": dict( [(name, remote.data_for_json()) for (name, remote) in self.remotes.iteritems()] ),
      "projects": dict( [(name, project.data_for_json()) for (name, project) in self.projects.iteritems()] ),
      }

  def __repr__(self):
    return self.to_json()


class Remote(object):
  def __init__(self,
               fetch):
    self.fetch = fetch

  @staticmethod
  def from_dict(data):
    return Remote(fetch=data.get('fetch'))

  def to_json(self):
    return simplejson.dumps(self.data_for_json(), indent=2)

  def data_for_json(self):
    return {'fetch': self.fetch}

class Project(object):
  def __init__(self,
               name=None,
               remotes=None,
               refspec="master", # the remote ref to pull
               from_remote="origin", # where to pull from
               dir=None,
               ):
    self.name = name
    self.remotes = remotes if remotes else []
    self.dir = dir if dir else name
    self.from_remote = from_remote
    self.refspec = refspec

  @staticmethod
  def from_dict(name, data, remotes, default_remote):
    my_remote_names = data.get('remotes', [default_remote])
    my_remotes = dict([ (r, remotes[r])
                        for r in my_remote_names])

    from_remote = data.get('from-remote')
    if not from_remote:
      if len(my_remote_names) == 1:
        from_remote = my_remote_names[0]
      elif default_remote in my_remote_names:
        from_remote = default_remote
      else:
        raise Exception("no from-remote listed for project %s, and more than one remote" %
                        name)
    
    assert from_remote in my_remote_names
    return Project(name=name,
                   remotes=my_remotes,
                   refspec=data.get('refspec', 'master'),
                   dir=data.get('dir', name),
                   from_remote=from_remote)

  @property
  def tracking_branch(self):
    return self.refspec

  @property
  def remote_refspec(self):
    return "%s/%s" % (self.from_remote, self.refspec)

  def to_json(self):
    return simplejson.dumps(self.data_for_json())

  def data_for_json(self):
    return {'name': self.name,
            'remotes': self.remotes.keys(),
            'refspec': self.refspec,
            'from-remote': self.from_remote,
            'dir': self.dir}


def load_manifest(path):
  data = simplejson.load(file(path))
  return Manifest.from_dict(data)


def test_json_load_store():
  man = load_manifest(os.path.join(os.path.dirname(__file__), 'test', 'test_manifest.json'))
  assert len(man.to_json()) > 10
