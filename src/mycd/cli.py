import click
from dataclasses import dataclass, asdict, field
import json
from pathlib import Path
from shutil import copyfile, copytree, rmtree
import subprocess
from uuid import uuid4
from typing import Union
import lmdb


RepoName = str
Uri = str

def sprun(cmd):
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

class Repo:
    def __init__(self, uri: Uri):
        self.name = str(uuid4())
        self.uri = uri
        self.destdir = None

    def clone(self, dest):
        ''' clones repo '''
        print('cloning repo')

        self.destdir = Path(dest) / self.name
        cmd = f'git clone {str(self.uri)} {self.destdir}',
        if not self.destdir.exists():
            sprun(cmd)
        else:
            print(f'destdir exists, skipping clone')

    def checkout(self, branch: str):
        print('checking out branch')
        cmd = f'cd {self.destdir} && git checkout {branch}'
        sprun(cmd)

    def pull(self):
        print('pulling branch')
        cmd = f'cd {self.destdir} && git pull'
        sprun(cmd)

    def get_branch_tip(self, branch: str):
        cmd = f'cd {self.destdir} && git rev-parse {branch}'
        proc = sprun(cmd)
        return Commit(proc.stdout, self.uri)


# seed_uris = 'repouri'

# cache 
# caches crawler

# crawlers = (seed) -> downloaded_commit
# those get one or many commits from a seed

# buildrules = (downloaded_commit) -> build

class BuildDB:
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

    def set_built(self, commit: Commit):
        key = commit.hash
        value = '1'
        with self.env.begin(write=True) as txn:
            return txn.put(str(key).encode('utf-8'), str(value).encode('utf-8'))



class Build:
    def __init__(self, commit: Commit):
        self.repo = Repo(commit.uri)
        self.commit = commit
        self.state = 'created'
        self.builddir = None

    def setup_builddir(self):
        self.repo.clone(self.builddir)
        self.repo.checkout(self.commit.hash)
        print('setting up builddir')
        #self.repo.clone(self.builddir)
        #copytree(self.repo.destdir, self.builddir)
        pass

    def cleanup(self):
        print('cleaning up builddir')
        #rmtree(self.builddir)

    def run(self):
        db = BuildDB()
        self.builddir = db.get_new_builddir()

        print('starting build')
        self.state = 'setting_up'
        self.setup_builddir()
        self.state = 'running'

        cmd = f'cd {self.repo.destdir} && ./ci.sh'
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


class Crawler:
    def __init__(self):
        pass

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



class BuildRule:
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


@click.command()
@click.option('--config', type=click.Path(dir_okay=False, file_okay=True))
def main(config):
    #Config.init_conf('testconf')
    seeds = ['/home/flowpoint/devel/testrepo']
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
