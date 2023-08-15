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
Branches = Union[str, 'default', 'all']

class Branches:
    br: str

class RepoEntry:
    name: RepoName
    uri: Uri
    branches: Branches
    cmd_template: str = None

@dataclass
class ConfigData:
    repos: list[RepoEntry] = field(default_factory=list)
    workdir: str = '/tmp/mycd'
    dbpath: str = '/tmp/mycd_db.lmdb'
    cmd_template: str = './ci.sh'


class Config:
    def __init__(self, path):
        self.path = Path(path)
        self._configdata = ConfigData()

        self.repos: list[Repo] = []
        self.workdir: Path = '/tmp/mycd'
        self.dbpath: Path = '/tmp/mycd_db.lmdb'
        cmd_template: str = './ci.sh'

    @staticmethod
    def init_conf(path: Path):
        print('initializing conf')
        if not Path(path).exists():
            c = Config(path)
            c.save(missing_ok=True)
        else:
            print('conf exists, skipping creating new conf')


    @property
    def swappath(self):
        return Path(str(self.path) + '.swp')

    @property
    def repos(self):
        return self.configdata.repos

    def load(self):
        print('loading conf')
        with self.path.open('r') as f:
            self._configdata = ConfigData(**json.loads(f.read()))

    def save(self, missing_ok=False):
        # use copying to ensure acid write
        print('saving conf')

        with self.swappath.open('w') as f:
            f.write(json.dumps(asdict(self._configdata)))

        copyfile(str(self.swappath), str(self.path))
        os.remove(self.swappath)


    def add_repo(self, name: RepoName, uri: Uri, branches: Branches, cmd_template: str = './ci.sh'):
        print('adding repo')
        if uri not in self._configdata.repos:
            self._configdata.repos.append({'name':name, 'uri': uri, 'branches':branches})
        else:
            raise RuntimeError('repo already exists in config')

    def remove_repo(self, repo: str):
        print('removing repo')
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
        self.hash_ = hash_
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




'''
class Build:
    def __init__(self, commit, cmd):
        self.commit = commit
        self.cmd = cmd
        self.result = None

    def start()
    def pause()
    def continue()
    def cancel()
'''


class BuildDB:
    def __init__(self):
        self.path = Path('/tmp/mycd_builddb')

    def get_new_builddir(self):
        return self.path / str(uuid4())

    def get_new_repodir(self):
        return self.path / str(uuid4())

class Build:
    def __init__(self, commit: str):
        self.repo = Repo(commit.uri)
        self.commit = commit.hash_
        self.state = 'created'
        self.builddir = None

    def setup_builddir(self):
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

        cmd = f'cd {self.builddir} && ./ci.sh'
        proc = sprun(cmd)
        self.state = 'cleaning_up'
        self.cleanup()
        self.state = 'finished'


class SDB:
    def __init__(self, path):
        self.path = path
        self.env = lmdb.open(self.path)

    def get(self, key):
        with self.env.begin(write=False) as txn:
            res = txn.get(str(key).encode('utf-8'))
            if res is not None:
                return res.decode('utf-8')
            else:
                return res

    def put(self, key, value):
        with self.env.begin(write=True) as txn:
            return txn.put(str(key).encode('utf-8'), str(value).encode('utf-8'))

    def __contains__(self, key):
        return self.get(key) is not None

class CI:
    def __init__(self, config: Config):
        self.config = config
        self.builds = SDB(self.config['dbpath'])

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
                if commit in self.builds:
                    print(f'commit: {commit} already build')
                else:
                    print(f'commit: {commit} not build, starting')
                    b = Builder(g, commit)
                    self.builds.put(commit, 1)
                    b.build(Path(self.config['workdir'])/commit)

    @property
    def repos(self):
        return self.config.repos

    def build_commit(self):
        pass

    def notify(self):
        pass

    def __repr__(self):
        return f"CI({repr(self.config)})"


class Crawler:
    def __init__(self):
        pass

    def crawl(self, seed):
        pass

class SimpleCrawler(Crawler):
    def __init__(self):
        pass
    
    def crawl(self, seed):
        db = BuildDB()
        r = Repo(seed)
        r.clone(db.get_new_repodir())
        r.checkout('main')
        return r.get_branch_tip('main')



class BuildRule:
    def __init__(self):
        pass

    def get(self, commit):
        pass

class SimpleBuildRule(BuildRule):
    def __init__(self):
        pass

    def get(self, commit):
        hash_ = commit.hash_
        uri = commit.uri

        def buildfn():
            db = BuildDB()
            r = Repo(uri)
            r.clone(db.get_new_builddir())
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


        



    '''
    a = Config('testconf')
    #a.load()
    branches = ['main']
    a.add_repo('testrepo', '/home/flowpoint/devel/testrepo', branches)
    c = CI(a)
    c.tick()
    #a.remove_repo('testrepo1')
    #a.save()
    '''
