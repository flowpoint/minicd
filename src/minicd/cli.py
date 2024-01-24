import json
from pathlib import Path
from shutil import copyfile, copytree, rmtree
import subprocess
from uuid import uuid4
from typing import Union, Optional
from abc import ABC, abstractmethod
import os
import signal
import base64

import click
import lmdb # type: ignore

from typing import Dict, List

Uri = str

DEBUG=False

homedir = Path(os.environ['HOME'])

default_config = {
        "db_path": str( homedir / 'minicd_builddb'),
        "seeds":[],
        "crawlers":[],
        "buildrules":[],
        }

def sprun(cmd: str):
    print(f'running command: {cmd}')
    proc = subprocess.run(
            cmd,
            shell=True,
            text=True,
            capture_output=True
            )

    if DEBUG:
        print(f'stdout: {proc.stdout}')
        print(f'stderr: {proc.stderr}')
    proc.check_returncode()
    return proc


class Commit:
    def __init__(self, hash_, repo):
        self.hash = str(hash_)
        self.repo = repo

    def dict(self):
        return {"hash":str(self.hash), "repo": self.repo.dict()}

    def __str__(self):
        return self.hash


class Repo:
    def __init__(self, uri: Uri, name=None, clonedir=None, commit=None):
        self.uri = uri
        if name is None:
            # = is the padding in base32, we remove it
            self.name = base64.b32encode(str(uri).encode('utf-8')).decode('utf-8').replace("=",'')
        else:
            self.name = name

        self.clonedir : Optional[Path] = clonedir
        self.commit : Optional[Commit] = commit

    def clone(self, dest: Path):
        ''' clones repo '''
        print('cloning repo')

        self.clonedir = dest / self.name
        cmd = f'git clone {str(self.uri)} {str(self.clonedir)}'
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

    def fetch(self):
        print('pulling branch')
        cmd = f'cd {self.clonedir} && git fetch'
        sprun(cmd)

    def all_branches(self):
        cmd = f'cd {self.clonedir} && git branch -a --format "%(refname)"'
        proc = sprun(cmd)
        raise NotImplemented()
        return proc.stdout.split('\n')
    
    def remote_branches(self):
        cmd = f'git remote ls {self.uri}'
        proc = sprun(cmd)
        return proc.stdout.strip().split(' ')[-1]

    def get_branch_tip(self):
        cmd = f'cd {self.clonedir} && git log -n 1 --pretty=format:"%H"'
        proc = sprun(cmd)
        c_hash = proc.stdout
        return Commit(c_hash, self)

    def dict(self):
        return {"name":self.name, 
                "uri": self.uri, 
                "commit": str(self.commit),
                "clonedir": str(self.clonedir)}

class Build:
    def __init__(self, commit: Commit, buildfn):
        self.commit = commit
        self.state = 'created'
        self.buildfn = buildfn
        self.data : Dict = {}

    def run(self):
        try:
            self.buildfn(self)
        except Exception as e:
            print(e)
            self.state = 'error'
            db.save_build(self)

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
        return {"commit": self.commit.dict(), "buildfn":"", 'state':self.state, 'data':self.data}

class BuildDB(ABC):
    def __init__(self):
        pass

    def load(self, path):
        self.path = Path(path)
        self.env = lmdb.open(str(self.path))

    @property
    def builddir(self):
        return self.path / 'builds' #/ str(uuid4())

    @property
    def repodir(self):
        return self.path / 'repos'


class BuildLMDB(BuildDB):
    def __init__(self):
        super().__init__()


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
        print(f'saving build {build.commit.repo.uri} {build.commit.hash} {build.state}')
        key = build.commit.hash
        value = json.dumps(build.dict())
        with self.env.begin(write=True) as txn:
            return txn.put(str(key).encode('utf-8'), str(value).encode('utf-8'))

db = BuildLMDB()

class Crawler(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def crawl(self, seed) -> List[Commit]:
        pass

class SimpleCrawler(Crawler):
    ''' only returns the repo on the latest main branch commit '''
    def __init__(self):
        super().__init__()
    
    def crawl(self, seed) -> List[Commit]:
        r = Repo(seed)
        repodir = db.repodir
        try:
            r.clone(repodir)
        except Exception as e:
            print(f'cloning repo: {r} failed with {e}')

        try:
            r.fetch()
            # pull is needed because we clone this repo locally again and else
            # and the pull from the real origin wont work
            # because we wont commit to this clone, the pull should normally be able to fast forward
            # if it doesnt, it is because origin used git in a bad way that resulted in conflicts and possibly overwrote data
            r.pull()
            r.checkout('main')
        except Exception as e:
            print(f'checkout out main for repo: {r} failed with {e}')

        if r.commit is None:
            commits = []
        else:
            commit = r.commit
            commits = [commit]

        #print(f'removing repodir after crawling {repodir}')
        #rmtree(repodir)
        return commits


class BuildRule(ABC):
    def __init__(self):
        pass

    def match(self, commit):
        pass

    def get(self, repo):
        pass

class SimpleBuildRule(BuildRule):
    def __init__(self):
        super().__init__()

    def match(self, commit):
        return True

    def get(self, commit: Commit) -> Build:
        ''' creates a Build with a build function 
        '''
        def buildfn(build):
            if db.was_built(commit.hash):
                print(f'commmit {commit.hash} was already built, skipping')
                return

            build.state = 'running'
            db.save_build(build)

            print('wasnt built')

            # copy repo to builddir
            repo = commit.repo

            repodir = Path(db.builddir) / str(commit.hash)#repo.name
            repodir.mkdir(parents=True, exist_ok=True)
            repo.clone(repodir)
            repo.fetch()
            #repo.pull()
            repo.checkout(commit.hash)

            # build the commit

            # run the ci script and write the logs to the build dir above the repo directory
            cmd = f'cd {repo.clonedir} && ./ci.sh > >(tee -a ../stdout.log) 2> >(tee -a ../stderr.log >&2)'
            proc = sprun(cmd)

            build.state = 'success'
            db.save_build(build)

            # report
            # cleanup

        build = Build(commit, buildfn)

        return build


@click.group()
@click.option('--config', type=click.Path(dir_okay=False, file_okay=True), default=str(homedir/ 'minicd/config.json'))
@click.pass_context
def cli(ctx, config):
    ctx.obj = {'configpath': config}

signals = None

def handler(signum, frame):
    global signals 
    print('term recieved, shutting down gracefully after the next build')
    signals = 'term'

signal.signal(signal.SIGTERM, handler)

def get_config(ctx):
    configp = Path(ctx.obj['configpath'])
    if not configp.exists():
        raise RuntimeError(f'config file doesnt exist at {configp}, maybe use init to create one')

    with configp.open('r') as f:
        config = json.loads(f.read())
    return config

def get_db(config):
    db.load(config['db_path'])
    return db

@cli.command()
@click.pass_context
def init(ctx):
        configp = ctx.obj['configpath']
        print(f'creating default config at {configp}')
        Path(configp).parent.mkdir(parents=True, exist_ok=True)
        if Path(configp).exists():
            raise RuntimeError(f'config already exists at {configp}')
        with open(configp, 'w') as f:
            f.write(json.dumps(default_config))
        print(default_config)

@cli.command()
@click.pass_context
def run(ctx):
    config = get_config(ctx)
    db = get_db(config)

    seeds = config['seeds']
    crawlers = [SimpleCrawler()]
    buildrules = [SimpleBuildRule()]

    commits = []
    for s in seeds:
        for cr in crawlers:
            commits += cr.crawl(s)

    # the first buildrule that matches is used
    # this is because of better efficiency
    # only repos without any matching rules need to run through all rules
    builds = []
    for cm in commits:
        for rule in buildrules:
            if rule.match(cm):
                build = rule.get(cm)
                builds.append(build)
                break

    for build in builds:
        if signals is None:
            build.run()
        else:
            break


@cli.command()
@click.argument('seed')
@click.pass_context
def seed_add(ctx, seed):
    config = get_config(ctx)
    p = ctx.obj['configpath']
    nc = config
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
    config = get_config(ctx)
    configpath = ctx.obj['configpath']
    print(f'config at path: {configpath}')
    print(f'config contents: \n {config}')

@cli.command()
@click.pass_context
def builds(ctx):
    config = get_config(ctx)
    db = get_db(config)

    fields = ['status', 'commit', 'repo']
    sep = '----'
    spacings = [7, 42, 40]
    print(tjoin([padto(s,l) for s,l in zip(fields, spacings)]))
    print(tjoin([padto(sep,l) for l in spacings]))
    for k, v in db.all_builds():
        reponame = v['commit']['repo']['uri']
        commit = v['commit']['hash']
        state = v['state']
        fields = [state, commit, reponame]
        print(tjoin([padto(s,l) for s,l in zip(fields, spacings)]))
