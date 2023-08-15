import json
from pathlib import Path
from shutil import copyfile, copytree, rmtree
import subprocess
from uuid import uuid4
from typing import Union, Optional
from abc import ABC, abstractmethod

import click
import lmdb

RepoName = str
Uri = str

def sprun(cmd: str):
    print(f'running command: {cmd}')
    proc = subprocess.run(
            cmd,
            shell=True,
            text=True,
            capture_output=True
            )

    print(f'stdout: {proc.stdout}')
    print(f'stderr: {proc.stderr}')
    proc.check_returncode()
    return proc


class Commit:
    def __init__(self, hash_, uri):
        self.hash = hash_
        self.uri = uri

    def dict(self):
        return {"hash":self.hash, "uri": self.uri}

class Repo:
    def __init__(self, uri: Uri, name=str(uuid4()), clonedir=None):
        self.uri = uri
        self.name = name
        self.clonedir : Optional[Path] = clonedir

    def clone(self, dest: Path):
        ''' clones repo '''
        print('cloning repo')

        self.clonedir = dest / self.name
        cmd = f'git clone {str(self.uri)} {self.clonedir}'
        if not self.clonedir.exists():
            sprun(cmd)
        else:
            print(f'clonedir exists, skipping clone')

    def checkout(self, branch: str):
        print('checking out branch')
        cmd = f'cd {self.clonedir} && git checkout {branch}'
        sprun(cmd)

    def pull(self):
        print('pulling branch')
        cmd = f'cd {self.clonedir} && git pull'
        sprun(cmd)

    def get_branch_tip(self, branch: str):
        cmd = f'cd {self.clonedir} && git rev-parse {branch}'
        proc = sprun(cmd)
        return Commit(proc.stdout, self.uri)

    def dict(self):
        return {"name":self.name, 
                "uri": self.uri, 
                "clonedir": self.clonedir}


# seed_uris = 'repouri'

# cache 
# caches crawler

# crawlers = (seed) -> downloaded_commit
# those get one or many commits from a seed

# buildrules = (downloaded_commit) -> build

class Build:
    def __init__(self, commit: Commit):
        self.repo = Repo(commit.uri)
        self.commit = commit
        self.state = 'created'
        db = BuildDB()
        self.builddir = db.get_new_builddir()

    def setup_builddir(self):
        self.repo.clone(self.builddir)
        self.repo.checkout(self.commit.hash)
        print('setting up builddir')
        #self.repo.clone(self.builddir)
        #copytree(self.repo.clonedir, self.builddir)
        pass

    def cleanup(self):
        print('cleaning up builddir')
        #rmtree(self.builddir)

    def run(self):
        print('starting build')
        self.state = 'setting_up'
        self.setup_builddir()
        self.state = 'running'

        cmd = f'cd {self.repo.clonedir} && ./ci.sh'
        proc = sprun(cmd)
        self.state = 'cleaning_up'
        self.cleanup()
        self.state = 'finished'

    def start(self):
        pass

    def pause(self):
        pass
    def resume(self):
        pass
    def cancel(self):
        pass

    def dict(self):
        return {"repo": self.repo.dict(), "commit": self.commit.dict()}

class BuildDB(ABC):
    def __init__(self):
        self.path = Path('/tmp/mycd_builddb')

    def get_new_builddir(self):
        return self.path / str(uuid4())

    def get_new_repodir(self):
        return self.path / str(uuid4())


class BuildLMDB(BuildDB):
    def __init__(self):
        super().__init__()
        self.env = lmdb.open(self.path)

    def was_built(self, commit: Commit):
        key = commit.hash
        with self.env.begin(write=False) as txn:
            res = txn.get(str(key).encode('utf-8'))
            return res is not None

    def set_built(self, build: Build):
        key = build.commit.hash
        value = json.dumps(build.dict())
        with self.env.begin(write=True) as txn:
            return txn.put(str(key).encode('utf-8'), str(value).encode('utf-8'))


class Crawler(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def crawl(self, seed) -> Commit:
        pass

class SimpleCrawler(Crawler):
    def __init__(self):
        super().__init__()
    
    def crawl(self, seed):
        db = BuildDB()
        r = Repo(seed)
        repodir = db.get_new_repodir()
        r.clone(repodir)
        r.checkout('main')
        hash_ = r.get_branch_tip('main').hash
        rmtree(repodir)
        return Commit(hash_, seed)



class BuildRule(ABC):
    def __init__(self):
        pass

    def get(self, commit):
        pass

class SimpleBuildRule(BuildRule):
    def __init__(self):
        super().__init__()

    def get(self, commit: Commit):
        hash_ = commit.hash
        uri = commit.uri

        def buildfn():
            db = BuildDB()
            r = Repo(uri)
            repodir = db.get_new_builddir()
            r.clone(repodir)
            r.checkout(hash_)

            build = Build(commit)
            build.run()

        return buildfn


@click.group()
@click.option('--config', type=click.Path(dir_okay=False, file_okay=True), default='/tmp/nano_build_delivery.json')
@click.pass_context
def cli(ctx, config):
    ctx.obj = config
    pass

@cli.command()
@click.pass_obj
def run(config):
    with open(config, 'r') as f:
        config = json.loads(f.read())

    seeds = config['seeds']
    #seeds = ['/home/flowpoint/devel/testrepo']
    crawlers = [SimpleCrawler()]
    buildrules = [SimpleBuildRule()]

    commits = []
    for s in seeds:
        for cr in crawlers:
            commits.append(cr.crawl(s))

    for cm in commits:
        for rule in buildrules:
            r = rule.get(cm)
            print(r)
            r()
