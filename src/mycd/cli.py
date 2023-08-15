import json
from pathlib import Path
from shutil import copyfile, copytree, rmtree
import subprocess
from uuid import uuid4
from typing import Union, Optional
from abc import ABC, abstractmethod
import os
import signal

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

class Build:
    def __init__(self, repo: Repo, buildfn):
        self.repo = repo
        self.state = 'created'
        self.buildfn = buildfn

    def run(self):
        try:
            self.buildfn(self)
        except Exception as e:
            print(e)
            self.state = 'error'

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
        return {"repo": self.repo.dict(), "buildfn":"", 'state':self.state}

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

    def all_builds(self):
        with self.env.begin(write=False) as txn:
            with txn.cursor() as curs:
                for i in curs:
                    yield i[0].decode('utf-8'), json.loads(i[1].decode('utf-8'))


    def was_built(self, commit: Commit):
        key = commit
        with self.env.begin(write=False) as txn:
            res = txn.get(str(key).encode('utf-8'))
            if res is not None:
                state = json.loads(res.decode('utf-8'))['state']
                return state != 'created'
            else:
                return False

    def save_build(self, build: Build):
        print(f'saving build {build.repo.uri} {build.repo.commit} {build.state}')
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
        def buildfn(build):
            commit = repo.commit

            if db.was_built(commit):
                print('commmit was already built, skipping')
                return

            build.state = 'running'
            db.save_build(build)


            print('wasnt built')

            repodir = db.get_new_builddir()
            repo.clone(repodir)
            repo.checkout(commit)

            # run the ci script and write the logs to the build dir above the repo directory
            cmd = f'cd {repo.clonedir} && ./ci.sh > >(tee -a ../stdout.log) 2> >(tee -a ../stderr.log >&2)'
            proc = sprun(cmd)

            build.state = 'success'
            db.save_build(build)

            # report
            # cleanup

        build = Build(repo, buildfn)

        return build


@click.group()
@click.option('--config', type=click.Path(dir_okay=False, file_okay=True), default='/tmp/nano_build_delivery.json')
@click.pass_context
def cli(ctx, config):
    with open(config, 'r') as f:
        configo = json.loads(f.read())
    ctx.obj = {'config': configo, 'configpath': config}

signals = None

def handler(signum, frame):
    global signals 
    print('term recieved, shutting down gracefully after the next build')
    signals = 'term'

signal.signal(signal.SIGTERM, handler)

@cli.command()
@click.pass_context
def run(ctx):
    config = ctx.obj['config']
    seeds = config['seeds']
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
        if signals is None:
            build.run()
        else:
            break


@cli.command()
@click.argument('seed')
@click.pass_context
def seed_add(ctx, seed):
    p = ctx.obj['configpath']
    nc = ctx.obj['config']
    if seed in nc['seeds']:
        print('seed already exists, aborting')
    nc['seeds'] = nc['seeds'] + [seed]
    nfp = p+'.new'
    with open(nfp, 'w') as f:
        f.write(json.dumps(nc))
    copyfile(nfp, p)
    os.remove(nfp)

def padto(s, l):
    return s + ' '*(l-len(s))

def tjoin(s):
    return '| ' + ' | '.join(s) + ' |'

@cli.command()
@click.pass_context
def config(ctx):
    print(ctx.obj['configpath'])
    print(ctx.obj['config'])

@cli.command()
@click.pass_context
def builds(ctx):
    fields = ['status', 'commit', 'repo']
    sep = '----'
    spacings = [7, 42, 40]
    print(tjoin([padto(s,l) for s,l in zip(fields, spacings)]))
    print(tjoin([padto(sep,l) for l in spacings]))
    for k, v in db.all_builds():
        reponame = v['repo']['uri']
        commit = v['repo']['commit']
        state = v['state']
        fields = [state, commit, reponame]
        print(tjoin([padto(s,l) for s,l in zip(fields, spacings)]))
