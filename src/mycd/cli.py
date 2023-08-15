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
Commit: str

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
        return {"hash":str(self.hash), "uri": self.uri}

class Repo:
    def __init__(self, uri: Uri, name=str(uuid4()), clonedir=None, commit=None):
        self.uri = uri
        self.name = name
        self.clonedir : Optional[Path] = clonedir
        self.commit : Optional[Commit] = commit

    def clone(self, dest: Path):
        ''' clones repo '''
        print('cloning repo')

        self.clonedir = dest / self.name
        cmd = f'git clone {str(self.uri)} {self.clonedir}'
        if not self.clonedir.exists():
            sprun(cmd)
        else:
            print(f'clonedir exists, skipping clone')

        self.commit = self.get_branch_tip()

    def checkout(self, branch: str):
        print('checking out branch')
        cmd = f'cd {self.clonedir} && git checkout {branch}'
        sprun(cmd)
        self.commit = self.get_branch_tip()

    def pull(self):
        print('pulling branch')
        cmd = f'cd {self.clonedir} && git pull'
        sprun(cmd)

    def get_branch_tip(self):
        cmd = f'cd {self.clonedir} && git log -n 1 --pretty=format:"%H"'
        proc = sprun(cmd)
        return proc.stdout

    def dict(self):
        return {"name":self.name, 
                "uri": self.uri, 
                "commit": str(self.commit),
                "clonedir": str(self.clonedir)}


# seed_uris = 'repouri'

# cache 
# caches crawler

# crawlers = (seed) -> downloaded_commit
# those get one or many commits from a seed

# buildrules = (downloaded_commit) -> build

class Build:
    def __init__(self, repo: Repo, buildfn, reportfn):
        self.repo = repo
        self.state = 'created'
        self.buildfn = buildfn
        self.reportfn = reportfn

    def run(self):
        self.buildfn()
        self.reportfn(self)

    '''
    def start(self):
        pass

    def pause(self):
        pass
    def resume(self):
        pass
    def cancel(self):
        pass
    '''

    def dict(self):
        return {"repo": self.repo.dict(), "buildfn":""}

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
        self.env = lmdb.open(str(self.path))

    def was_built(self, commit: Commit):
        key = commit
        with self.env.begin(write=False) as txn:
            res = txn.get(str(key).encode('utf-8'))
            return res is not None

    def set_built(self, build: Build):
        key = build.repo.commit
        value = json.dumps(build.dict())
        with self.env.begin(write=True) as txn:
            return txn.put(str(key).encode('utf-8'), str(value).encode('utf-8'))

db = BuildLMDB()

class Crawler(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def crawl(self, seed) -> Repo:
        pass

class SimpleCrawler(Crawler):
    ''' only returns the repo on the latest main branch commit '''
    def __init__(self):
        super().__init__()
    
    def crawl(self, seed) -> Repo:
        r = Repo(seed)
        repodir = db.get_new_repodir()
        r.clone(repodir)
        r.checkout('main')
        commit = r.commit
        rmtree(repodir)
        return r


class BuildRule(ABC):
    def __init__(self):
        pass

    def get(self, repo):
        pass

class SimpleBuildRule(BuildRule):
    def __init__(self):
        super().__init__()

    def get(self, repo: Repo) -> Build:
        def buildfn():
            commit = repo.commit

            if db.was_built(commit):
                print('commmit was already built, skipping')
                return

            repodir = db.get_new_builddir()
            repo.clone(repodir)
            repo.checkout(commit)

            cmd = f'cd {repo.clonedir} && ./ci.sh'
            proc = sprun(cmd)

            # report
            # cleanup

        def reportfn(build):
            db.set_built(build)

        build = Build(repo, buildfn, reportfn)

        return build


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

    builds = []
    for cm in commits:
        for rule in buildrules:
            build = rule.get(cm)
            builds.append(build)

    for build in builds:
        build.run()

@cli.command()
@click.argument('cmd')
@click.pass_obj
def builds(config, cmd):
    with open(config, 'r') as f:
        config = json.loads(f.read())
