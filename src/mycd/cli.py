import click
from dataclasses import dataclass, asdict, field
import json
from pathlib import Path
from shutil import copyfile
import subprocess
from uuid import uuid4
from typing import Union


RepoName = str
Uri = str
Branches = Union[str, 'default', 'all']

class RepoEntry:
    name: RepoName
    uri: Uri
    branches: Branches

@dataclass
class ConfigData:
    repos: list[RepoEntry] = field(default_factory=list)
    workdir: str = '/tmp/mycd'


class Config:
    def __init__(self, path):
        self.path = Path(path)
        self._configdata = ConfigData()

    @staticmethod
    def init_conf(path: Path):
        if not Path(path).exists():
            c = Config(path)
            c.save(missing_ok=True)
        else:
            print('conf exists, skipping creating new conf')


    @property
    def bakpath(self):
        return Path(str(self.path) + '.bak')

    @property
    def repos(self):
        return self.configdata.repos

    def load(self):
        with self.path.open('r') as f:
            self._configdata = ConfigData(**json.loads(f.read()))

    def save(self, missing_ok=False):
        if self.path.exists():
            copyfile(str(self.path), str(self.bakpath))
        elif missing_ok == False:
            raise RuntimeError('config file doesnt exist')


        with self.path.open('w') as f:
            f.write(json.dumps(asdict(self._configdata)))


    def add_repo(self, name: RepoName, uri: Uri, branches: Branches):
        if uri not in self._configdata.repos:
            self._configdata.repos.append({'name':name, 'uri': uri, 'branches':branches})
        else:
            raise RuntimeError('repo already exists in config')

    def remove_repo(self, repo: str):
        if repo not in self._configdata.repos:
            raise RuntimeError('unknown repo cant be removed known')
        else:
            self._configdata.repos.remove(repo)

    def __repr__(self):
        return f'Config({repr(self._configdata)})'

    def __getitem__(self, k):
        return getattr(self._configdata, k)

    def __setitem__(self, k, v):
        return setattr(self._configdata, k, v)

# branch = Union[str, Literal[all, default]]

def sprun(cmd)
    proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True
            )

    print(proc.stdout)
    print(proc.stderr)
    proc.check_returncode()
    return proc

class Repo:
    def __init__(self, name: RepoName, uri: Uri, branches: Branches):
        self.name = name
        self.uri = uri
        self.branches = branches

        self.destdir = None

    def clone(self, dest):
        ''' clones repo '''

        self.destdir = Path(dest) / self.name
        cmd = f'git clone {str(self.uri)} {self.destdir}',
        if not self.destdir.exists():
            sprun(cmd)
        else:
            print(f'destdir exists, skipping clone')

    def checkout(self, branch: str):
        cmd = f'cd {self.destdir} && git checkout {branch}'
        proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True
                )

        print(proc.stdout)
        print(proc.stderr)
        proc.check_returncode()

    def pull(self):
        cmd = f'cd {self.destdir} && git pull'
        sprun(cmd)

    def get_branch_tip(self, branch: str):
        cmd = f'cd {self.destdir} && git rev-parse {branch}',
        proc = sprun(cmd)
        return proc.stdout

    def get_all_branches(self):
        pass


class Builder:
    def __init__(self, repo: Repo, commit: str):
        self.repo = repo
        self.commit = commit
        self.state = 'created'

    def setup_buildenv(self):
        pass

    def cleanup(self):
        pass

    def build(self):
        self.state = 'running'
        cmd = f'cd {self.repo.destdir} && ./ci.sh'
        proc = sprun(cmd)
        self.state = 'finished'


class CI:
    def __init__(self, config: Config):
        self.config = config
        self.builds = []

    def tick(self):
        for r in self.config['repos']:
            name = r['name']
            uri = r['uri']
            branches = r['branches']
            g = Repo(name, uri, branches)
            g.clone(self.config['workdir'])

            for b in g.branches:
                g.checkout(b)
                g.pull()
                commit = g.get_branch_tip(b)
                if not commit in self.builds:
                    b = Builder(g, commit)
                    self.builds.append(commit)
                    b.build()

    @property
    def repos(self):
        return self.config.repos

    def build_commit(self):
        pass

    def notify(self):
        pass

    def __repr__(self):
        return f"CI({repr(self.config)})"





@click.command()
@click.option('--config', type=click.Path(dir_okay=False, file_okay=True))
def main(config):
    #a = Config(repos=['hello'])
    Config.init_conf('testconf')
    a = Config('testconf')
    #a.load()
    branches = ['main']
    a.add_repo('testrepo', '/home/flowpoint/devel/testrepo', branches)
    c = CI(a)
    c.tick()
    c.config['hello'] = 1
    #a.remove_repo('testrepo1')
    #a.save()
    print(c)

    print('hello')
