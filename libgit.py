import argparse
import configparser 
import grp
import os
import pwd
import hashlib
import re
import sys
import zlib
from datetime import datetime
from fnmatch import fnmatch

argparser = argparse.ArgumentParser(description="My own git")
argsubparsers = argparser.add_subparsers(title="Commands", dest="command")
argsubparsers.required = True

argsp = argsubparsers.add_parser("init", 
                                 help="Initialize new repository")
argsp.add_argument("path", 
                   metavar="directory", 
                   nargs="?", 
                   default=".", 
                   help="where to create repo")

argsp = argsubparsers.add_parser("cat-file", 
                                 help="Print content of repo object")
argsp.add_argument("type", 
                   metavar="type", 
                   choices=["blob", "commit", "tag", "tree"], 
                   help="Specify the type")
argsp.add_argument("object", 
                   metavar="object", 
                   help="object to display")

argsp = argsubparsers.add_parser("hash-object", 
                                 help="Compute object ID and optionally create blob from file")
argsp.add_argument("-t", 
                   metavar="type",
                   dest="type", 
                   choices=["blob", "commit", "tag", "tree"],
                   default="blob",
                   help="Specify the type")
argsp.add_argument("-w",
                   dest="write",
                   action="store_true",
                   help="Actually write the object to the db")
argsp.add_argument("path",
                   help="Read object from <file>")

class Repository():
    worktree = None
    gitdir = None
    conf = None

    def __init__(self, path, force=False):
        self.worktree = path
        self.gitdir = os.path.join(path, ".git")

        if not (force or os.path.isdir(self.gitdir)):
            raise Exception(f"Not a Git repository {path}")

        # Read configuration file in .git/config
        self.conf = configparser.ConfigParser()
        cf = repo_file(self, "config")

        if cf and os.path.exists(cf):
            self.conf.read([cf])
        elif not force:
            raise Exception("Configuration file missing")

        if not force:
            vers = int(self.conf.get("core", "repositoryformatversion"))
            if vers != 0:
                raise Exception("Unsupported repositoryformatversion: {vers}")


class GitObject():
    def __init__(self, data=None):
        if data != None:
            self.deserialize(data)
        else:
            self.init()

    def serialize(self, repo):
        raise Exception("Unimplemented")
    
    def deserialize(self, data):
        raise Exception("Unimplemented")
    
    def init(self):
        pass

class GitCommit():
    pass


class GitTree():
    pass


class GitTag():
    pass


class GitBlob(GitObject):
    fmt = b"blob"

    def serialize(self):
        return self.blobdata
    
    def deserialize(self, data):
        self.blobdata = self.data


def object_read(repo: Repository, sha):
    path = repo_file(repo, "objects", sha[0:2], sha[2:])

    if not os.path.isfile(path):
        return None

    with open(path, "rb") as f:
        raw = zlib.decompress(f.read())

        space = raw.find(b" ")
        fmt   = raw[0:space]

        null_char = raw.find("\x00", space)
        size = int(raw[space:null_char].decode("ascii"))

        if size != len(raw) - null_char - 1:
            raise Exception(f"Malformed object {sha}: bad length")
        
    match fmt:
        case b"commit" : c=GitCommit
        case b"tree"   : c=GitTree
        case b"tag"    : c=GitTag 
        case b"blob"   : c=GitBlob
        case _: raise Exception(f"Unknown type {fmt.decode("ascii")}")

    return c(raw[null_char + 1])


def object_write(obj: GitObject, repo=None):
    data = obj.serialize()

    result = obj.fmt + b" " + str(len(data)).encode() + b"\x00" + data

    sha = hashlib.sha1(result).hexdigest()

    if repo:
        path=repo_file(repo, "objects", sha[0:2], sha[2:], mkdir=True)
        
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(zlib.compress(result))

    return sha


def object_find(repo: Repository, name, fmt=None, follow=True):
    return name


def object_hash(fd, fmt, repo=None):
    """ Hash object, writing it to repo if provided."""
    data = fd.read()

    # Choose constructor according to fmt argument
    match fmt:
        case b'commit' : obj=GitCommit(data)
        case b'tree'   : obj=GitTree(data)
        case b'tag'    : obj=GitTag(data)
        case b'blob'   : obj=GitBlob(data)
        case _: raise Exception(f"Unknown type {fmt}!")

    return object_write(obj, repo)


def repo_path(repo: Repository, *path):
    return os.path.join(repo.gitdir, *path)


def repo_file(repo: Repository, *path, mkdir=False):
    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        return repo_path(repo, *path)
    

def repo_dir(repo: Repository, *path, mkdir=False):
    path = repo_path(repo, *path)

    if os.path.exists(path):
        if (os.path.isdir(path)):
            return path 
        else:
            raise Exception(f"Not a directory {path}")
    
    if mkdir:
        os.makedirs(path)
        return path
    else:
        return None
    

def repo_create(path):
    repo = Repository(path, True)

    if os.path.exists(repo.worktree):
        if not os.path.isdir(repo.worktree):
            raise Exception(f"{path} is not a directory")
        if os.path.exists(repo.gitdir):
            raise Exception(f"{path} is not empty")
    else:
        os.makedirs(repo.worktree)

    assert repo_dir(repo, "branches", mkdir=True)
    assert repo_dir(repo, "objects", mkdir=True)
    assert repo_dir(repo, "refs", "tags", mkdir=True)
    assert repo_dir(repo, "refs", "heads", mkdir=True)

    with open(repo_file(repo, "description"), "w") as f:
        f.write("Unnamed repository; edit this file 'description' to name the repository.\n")

    with open(repo_file(repo, "HEAD"), "w") as f:
        f.write("ref: refs/heads/master\n")

    with open(repo_file(repo, "config"), "w") as f:
        config = repo_default_config()
        config.write(f)
    
    return repo 


def repo_default_config():
    conf = configparser.ConfigParser()

    conf.add_section("core")
    conf.set("core", "repositoryformatversion", "0")
    conf.set("core", "filemode", "false")
    conf.set("core", "bare", "false")

    return conf


def repo_find(path=".", required=True):
    path = os.path.realpath(path)

    if os.path.isdir((os.path.join(path, ".git"))):
        return Repository(path)
    
    parent = os.path.realpath(os.path.join(path, ".."))

    if parent == path:
        if required:
            raise Exception("No git directory")
        else:
            return None
    
    return repo_find(parent, required)


def cmd_cat_file(args):
    repo = repo_find()
    cat_file(repo, args.object, fmt=args.type.encode())


def cat_file(repo: Repository, obj:GitObject, fmt=None):
    obj = object_read(repo, object_find(repo, obj, fmt=fmt))
    sys.stdout.buffer.write(obj.serialize())


def cmd_init(args):
    repo_create(args.path)


def cmd_hash_object(args):
    if args.write:
        repo = repo.find
    else:
        repo = None

    with open(args.path, "rb") as fd:
        sha = object_hash(fd, args.type.encode(), repo)

def main(argv=sys.argv[1:]):
    args = argparser.parse_args(argv)

    match args.command:
        case "add"          : cmd_add(args)
        case "cat-file"     : cmd_cat_file(args)
        case "check-ignore" : cmd_check_ignore(args)
        case "checkout"     : cmd_checkout(args)
        case "commit"       : cmd_commit(args)
        case "hash-object"  : cmd_hash_object(args)
        case "init"         : cmd_init(args)
        case "log"          : cmd_log(args)
        case "ls-files"     : cmd_ls_file(args)
        case "ls-tree"      : cmd_ls_tree(args)
        case "rev-parse"    : cmd_rev_parse(args)
        case "rm"           : cmd_rm(args)
        case "show-ref"     : cmd_show_ref(args)
        case "status"       : cmd_status(args)
        case "tag"          : cmd_tag(args)
        case _              : print("Bad command")

