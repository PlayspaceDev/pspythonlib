#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2018 - Playspace
import os
import re
import psutil
import sys
import argparse
import shutil
import json
import stat
import time
import subprocess
import uuid
from shlex import quote
from distutils.version import StrictVersion
from git import Repo, Head
import pkg_resources
from email import message_from_string
from colorama import init, Fore, Style
init()

try:
    import readline
except:
    pass  # readline not available

EXIT_CODE_SUCCESS = 0
EXIT_CODE_FAILED = 1

# ----------------------------------------------------------------------------------------
# Profiling
# ----------------------------------------------------------------------------------------

start_time = []


def time_push():
    global start_time
    start_time.append(time.time())


def time_pop():
    global start_time
    start = start_time.pop() if len(start_time) > 0 else -1
    if start >= 0:
        return time.time() - start
    return 0


# ----------------------------------------------------------------------------------------
# Semantic Sorting
# ----------------------------------------------------------------------------------------

def sort_human(l, reverse=False):
    convert = lambda text: str(text) if text.isdigit() else text
    alphanum = lambda key: [convert(c) for c in re.split('([-+]?[0-9]*\.?[0-9]*)', key)]
    l.sort(key=alphanum, reverse=reverse)
    return l


def sort_versions(l, reverse=False):
    return sorted(l, key=StrictVersion, reverse=reverse)


# ----------------------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------------------

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    LIGHTBLUE = '\033[36m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def xstr(s):
    return '' if s is None else s


def print_safe(text):
    print(text)

def log_info(text, *args, **kwargs):
    print_safe(xstr(text).format(*args, **kwargs))

def log_debug(text, *args, **kwargs):
    print_safe(Fore.BLUE + xstr(text).format(*args, **kwargs))
    print(Style.RESET_ALL)

def log_warn(text, *args, **kwargs):
    print_safe(Fore.YELLOW + xstr(text).format(*args, **kwargs))
    print(Style.RESET_ALL)

def log_error(text, *args, **kwargs):
    print_safe(Fore.RED + xstr(text).format(*args, **kwargs))
    print(Style.RESET_ALL)

def die(text, *args, **kwargs):
    log_error(text, *args, **kwargs)
    sys.exit(EXIT_CODE_FAILED)


# ----------------------------------------------------------------------------------------
# Misc
# ----------------------------------------------------------------------------------------

def to_bool(value):
    return str(value).lower() in ['true', '1', 't', 'y', 'yes', 'yeah', 'yup', 'certainly', 'uh-huh', 'aye']


def get_uuid():
    return str(uuid.uuid4())


def ignore_exception(ignored_exceptions=(Exception), default_value=None, silent=True):
    """ Decorator for ignoring exception from a function
    e.g.   @ignore_exception((DivideByZero))
    e.g.2. ignore_exception((DivideByZero))(Divide)(2/0)
    """

    def dec(function):
        def _dec(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except ignored_exceptions:
                if not silent:
                    print_safe(e)
                return default_value

        return _dec

    return dec


class Bunch(object):
    def __init__(self, adict):
        self.__dict__.update(adict)

    def __iter__(self):
        return iter(self.__dict__)

    def raw(self):
        return self.__dict__


@ignore_exception(default_value=False)
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)
    return True


def ensure_not_none(elem):
    return elem is not None


def ensure_not_empty(elem):
    return elem is not None and elem != ""


def none_if_empty(elem):
    if not ensure_not_empty(elem):
        return None
    return elem


def get_first_split(elem, split='-'):
    return elem.split(split)[0]


def find_previous_or_none(l, pivote):
    index = l.index(pivote) - 1 if pivote in l else -1
    return l[index] if index >= 0 else None


def lower_keys(x):
    if isinstance(x, list):
        return [lower_keys(v) for v in x]
    elif isinstance(x, dict):
        return dict((k.lower(), lower_keys(v)) for k, v in x.items())
    else:
        return x


# ----------------------------------------------------------------------------------------
# Arg parser helpers
# ----------------------------------------------------------------------------------------

def ensure_subparser_argument(arg_name, parser, args):
    if not arg_name in args:
        # Get subaction that we are missing and print it's help
        subparsers_actions = [
            action for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)]

        for subparsers_action in subparsers_actions:
            # get all subparsers and print help
            for choice, subparser in subparsers_action.choices.items():
                if args.which is choice:
                    subparser.print_help()
                    return EXIT_CODE_FAILED

        # Fallback help
        parser.print_help()
        sys.exit(EXIT_CODE_FAILED)


class readable_dir(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        prospective_dir = values
        if not os.path.isdir(prospective_dir):
            raise argparse.ArgumentTypeError("readable_dir: '{0}' is not a valid dir path".format(prospective_dir))
        if os.access(prospective_dir, os.R_OK):
            setattr(namespace, self.dest, prospective_dir)
        else:
            raise argparse.ArgumentTypeError("readable_dir: '{0} is not a readable dir".format(prospective_dir))


class readable_file(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        prospective_file = values
        if not os.path.isfile(prospective_file):
            raise argparse.ArgumentTypeError("readable_file: '{0}'' is not a valid file path".format(prospective_file))
        if os.access(prospective_file, os.R_OK):
            setattr(namespace, self.dest, prospective_file)
        else:
            raise argparse.ArgumentTypeError("readable_file: '{0}' is not a readable file".format(prospective_file))


# ----------------------------------------------------------------------------------------
# Environment Variables
# ----------------------------------------------------------------------------------------

def get_env_var(var):
    return os.environ[var] if var in os.environ else None


def has_env_var(var):
    return get_env_var(var) is not None


def has_env_var_flag(envvar):
    flag = get_env_var(envvar)
    return True if flag is not None and to_bool(flag) else False


# ----------------------------------------------------------------------------------------
# Config helpers
# ----------------------------------------------------------------------------------------

# TODO: Once our Bunch has incasesentive acces we can get rid of the key.lower() class when using this
def get_config(config_dict, key, type, default_value=None):
    return ignore_exception((ValueError), default_value)(type)(config_dict.get(key, default_value))


def get_config_checked(config_dict, key, type, validator, default_value=None):
    config_value = ignore_exception((ValueError), default_value)(type)(config_dict.get(key, default_value))
    if not validator(config_value):
        die("[{}] with value '{}' invalid or not found", key, config_value)
    return config_value


# ----------------------------------------------------------------------------------------
# Git helpers
# ----------------------------------------------------------------------------------------

def gather_repos(root_path):
    repos = []
    for dirname, dirnames, filenames in os.walk(root_path):
        if not 'node_modules' in dirname:
            for int_dir in dirnames:
                if '.git' in int_dir:
                    abspath = os.path.abspath(dirname)
                    repo = Repo(abspath)
                    repos.append(repo)
    return repos

def git_clean(repo, flags='-fd'):
    try:
        repo.git.clean(flags)
    except Exception as e:
        log_info(" Couldn't clean repo. Error:\n{}", e)


def git_clean_repo(repo):
    if git_has_local_branch(repo, repo.active_branch.name):
        try:
            repo.git.reset('--hard', "origin/{}".format(repo.active_branch.name))
        except Exception as e:
            log_info(" Couldn't clean the branch in local. Error:\n{}", e)


def git_merge_repo(repo, action, squash, source, destination, message=None):
    source_branch = "origin/{}".format(source)
    git_checkout_tracked(repo, destination)
    repo.git.pull('--no-edit', 'origin', destination)
    try:
        if not squash:
            repo.git.merge(source_branch, '--no-ff', '-m', 'Merge {} {} into {}{}'.format(action, source, destination,
                                                                                          ", {}".format(
                                                                                              message) if message else ""))
        else:
            repo.git.merge(source_branch, '--squash')
            try:
                repo.git.commit('--no-edit')
            except:
                pass
            repo.git.merge(source_branch, '-m', 'Merge {} {} into {}{}'.format(action, source, destination,
                                                                               ", {}".format(
                                                                                   message) if message else ""))
    except Exception as e:
        die(" Couldn't finish merge, resolve conflict and try again. Error:\n{}", e)


def git_delete_branch_repo(repo, branch, local=True, remote=True, fetch=True):
    if fetch:
        repo.git.fetch()

    if local and git_has_local_branch(repo, branch):
        try:
            repo.git.branch(branch, '-D')
        except Exception as e:
            pass
            # og_info(" Couldn't delete the branch in local. Error:\n{}", e)
    if remote:
        try:
            repo.remote('origin').push(':{}'.format(branch))
        except Exception as e:
            pass
            # log_info(" Couldn't delete the branch in remote. Error:\n{}", e)


def git_delete_tag_repo(repo, tag, local=True, remote=True, fetch=True):
    if fetch:
        try:
            repo.git.fetch('origin', 'refs/tags/{}'.format(tag))
        except:
            pass

    if local:
        try:
            repo.git.tag(tag, '-d')
        except Exception as e:
            pass

    if remote:
        try:
            repo.remote('origin').push(':refs/tags/{}'.format(tag))
        except Exception as e:
            pass


def git_pull_or_clone(repo_path, repo_git, branch="master", clean=True):
    if not os.path.isdir(repo_path) or not os.path.isdir(os.path.join(repo_path, '.git')):
        log_info("Cloning repo {}", repo_path)
        Repo.clone_from(repo_git, repo_path)
    else:
        repo = Repo(repo_path)
        if os.path.isfile(os.path.join(repo_path, '.git', 'index.lock')):
            os.remove(os.path.join(repo_path, '.git', 'index.lock'))
        try:
            log_info("Pulling repo {}", repo_path)
            repo.git.pull('--no-edit', 'origin', branch)
        except:
            if clean:
                log_info("Repo is dirty, cleaning and pulling {}", repo_path)
                git_clean_repo(repo)
                repo.git.pull('--no-edit', 'origin', branch)


def git_clone(repo_git, repo_path, branch="master"):
    Repo.clone_from(repo_git, repo_path, branch=branch)


def git_commit(repo_path, files, message, branch, push=True):
    if os.path.isdir(os.path.join(repo_path, '.git')):
        repo = Repo(repo_path)
        # Add all files one by one
        for file in files:
            repo.git.add(file)
        try:
            repo.git.commit('-m [PSBuilder] {}'.format(message))
        except:
            pass
        if push:
            repo.git.pull('--no-edit', 'origin', branch)
            repo.git.push('--set-upstream', 'origin', branch)


def git_push_and_add(repo_path, message, branch):
    if os.path.isdir(os.path.join(repo_path, '.git')):
        repo = Repo(repo_path)
        repo.git.add('.')
        try:
            repo.git.commit('-m [PSBuilder] {}'.format(message))
        except:
            pass
        repo.git.pull('--no-edit', 'origin', branch)
        repo.git.push('--set-upstream', 'origin', branch)


def git_get_remote(repo, remote_name):
    try:
        return repo.remote(remote_name)
    except ValueError:
        return None


def git_has_remote_branch(repo, branch_name):
    return 'refs/heads/{}'.format(branch_name) in repo.git.ls_remote('--heads')


def git_has_local_branch(repo, branch_name):
    try:
        repo.git.show_ref('--verify', '--quiet', 'refs/heads/{}'.format(branch_name))
        return True
    except:
        return False


def git_has_remote_tags(repo, tag_name):
    return 'refs/tags/{}'.format(tag_name) in repo.git.ls_remote('--tags')


def git_has_local_tag(repo, tag_name):
    try:
        repo.git.show_ref('--verify', '--quiet', 'refs/tags/{}'.format(tag_name))
        return True
    except:
        return False


def git_checkout_tracked(repo, branch_name):
    repo.remote('origin').fetch()
    repo.git.checkout(branch_name)
    repo.git.branch('--set-upstream-to=origin/{}'.format(branch_name), branch_name)


def git_create_branch(repo, branch_name):
    repo.remote().push(Head.create(repo, branch_name))


def git_create_tag(repo, tag_name, message=None):
    try:
        git_delete_tag_repo(repo, tag_name)
    except Exception:
        pass
    if message:
        repo.git.tag('-fa', tag_name, message=message)
    else:
        repo.git.tag('-f', tag_name)
    repo.git.push('origin', 'refs/tags/{}'.format(tag_name))


def git_list_tags(repo):
    return repo.git.tag("-l").split('\n')


def git_clean_tags(repo):
    for tag in git_list_tags(repo):
        if tag:
            repo.git.tag("-d", tag)
    repo.git.fetch("--tags")


def generate_last_build_tag(build_name, platform, buildtag):
    return 'last.{game}.{buildtag}.{platform}'.format(
        game=build_name, platform=platform, buildtag=buildtag)


def generate_build_tag(build_name, platform, buildtag, bundle_version, version_code, build_number):
    return 'build.{game}.{buildtag}.{platform}.{bundle_version}.{version_code}.{build_number}'.format(
        game=build_name, platform=platform, bundle_version=bundle_version,
        version_code=version_code, build_number=build_number, buildtag=buildtag)


# ----------------------------------------------------------------------------------------
# I/O helpers
# ----------------------------------------------------------------------------------------

@ignore_exception(default_value=0)
def get_file_size(path):
    return os.path.getsize(path)


def get_file_size_mb(path):
    return get_file_size(path) / (1024 * 1024.0)


def purge_dir(dir_path):
    if os.path.isdir(dir_path):
        log_info("Purging dir {}", dir_path)

        def del_evenReadonly(action, name, exc):
            os.chmod(name, stat.S_IWRITE)
            os.remove(name)

        shutil.rmtree(dir_path, onerror=del_evenReadonly)


def remove_file(file_path):
    if os.path.isfile(file_path):
        log_info("Remove file {}", file_path)
        os.remove(file_path)


def list_dirs(dir_path):
    return [os.path.join(dir_path, dir_name) for dir_name in os.listdir(dir_path) if
            os.path.isdir(os.path.join(dir_path, dir_name))]


def list_files(dir_path):
    return [os.path.join(dir_path, file_name) for file_name in os.listdir(dir_path) if
            os.path.isfile(os.path.join(dir_path, file_name))]


def copy_file(src, dst):
    try:
        os.remove(dst)
    except:
        pass
    shutil.copy2(src, dst)


# TODO: Bunch must have in case sensitive access too
def load_json(json_path):
    if not os.path.isfile(json_path) or not os.access(json_path, os.R_OK):
        return None
    with open(json_path, "r") as json_file:
        return json.load(json_file)


def write_json(adict, json_path, pretty=False):
    ensure_dir(os.path.dirname(json_path))
    with open(json_path, 'w') as json_file:
        json.dump(adict, json_file, sort_keys=True, indent=2 if pretty else None)


def write_to_file(text, file_path):
    with open(file_path, "w") as f:
        f.write(text)


def read_from_file(file_path):
    with open(file_path, "r") as f:
        return f.read()


def to_unix_path(path):
    return os.path.normpath(path).replace(os.sep, "/")


# ----------------------------------------------------------------------------------------
# OS Helpers
# ----------------------------------------------------------------------------------------

def is_unix():
    return has_env_var("SHELL")


def is_macos():
    return sys.platform.startswith('darwin')


def is_windows():
    return sys.platform.startswith('win')


def get_shell_ext():
    return "bat" if is_windows() else "sh"


def kill_proc_tree(pid, including_parent=True):
    parent = psutil.Process(pid)
    for child in parent.children(recursive=True):
        log_info("killing process '{}' with pid '{}' and cmd '{}'", child.name(), child.pid, child.cmdline())
        child.kill()
    if including_parent:
        log_info("killing parent process '{}' with pid '{}' and cmd '{}'", parent.name(), parent.pid, child.cmdline())
        parent.kill()


@ignore_exception(default_value="127.0.0.1")
def get_private_ip():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("google.com", 80))
        ip = s.getsockname()[0]
    return ip


# ----------------------------------------------------------------------------------------
# OS Helpers
# ----------------------------------------------------------------------------------------

def quote_arg(arg):
    if is_windows():
        if ' ' in arg:
            return '"{arg}"'.format(arg=arg)
        return arg
    return quote(arg)


def join_args(command_args):
    return ' '.join([quote_arg(arg) for arg in command_args])


@ignore_exception(default_value=None, silent=True)
def kill_process(p):
    p.kill()


class ProcessOutput(object):
    def __init__(self, adict):
        self.__dict__.update(adict)

    def raw(self):
        return self.__dict__


def execute_cmd(original_command, env=None, cwd=None, capture_output=False, encoding='utf8', detached=False):
    command = original_command if isinstance(original_command, str) else join_args(original_command)
    log_info("Executing command {start}{command}{end} in {start}{cwd}{end}", start=bcolors.OKGREEN, command=command,
             end=bcolors.ENDC, cwd=(cwd if cwd else os.getcwd()))
    p = None
    try:
        if is_windows() and detached:
            DETACHED_PROCESS = 0x00000008
            p = subprocess.Popen(command, shell=True, env=env, cwd=cwd,
                                 stdout=subprocess.PIPE if capture_output else None,
                                 stderr=subprocess.PIPE if capture_output else None, creationflags=DETACHED_PROCESS)
        else:
            p = subprocess.Popen(command, shell=True, env=env, cwd=cwd,
                                 stdout=subprocess.PIPE if capture_output else None,
                                 stderr=subprocess.PIPE if capture_output else None)
        stdout, stderr = p.communicate()
        return ProcessOutput({
            'args': p.args,
            'rc': p.returncode,
            'stdout': stdout.decode(encoding) if capture_output and stdout else None,
            'stderr': stderr.decode(encoding) if capture_output and stderr else None
        })
    except KeyboardInterrupt as e:
        kill_process(p)
        raise e


@ignore_exception(default_value=None, silent=False)
def execute_cmd_safe(command_args, env=None, cwd=None, capture_output=False, encoding='utf8', detached=False):
    return execute_cmd(command_args, env, cwd, capture_output)


def execute_script(command_args, cwd=None, detached=False):
    if is_windows():
        return execute_cmd(["call"] + command_args, cwd=cwd, detached=detached)
    else:
        return execute_cmd(command_args, cwd=cwd, detached=detached)


@ignore_exception(default_value=None, silent=False)
def execute_script_safe(command_args, cwd=None):
    return execute_script(command_args, cwd)


# ----------------------------------------------------------------------------------------
# Input handling
# ----------------------------------------------------------------------------------------

def input(prompt, default=None):
    import builtins
    if default:
        return builtins.input("{} [{}]: ".format(prompt, default)) or default
    return builtins.input("{}: ".format(prompt))


def input_typed(prompt, default, type):
    if not isinstance(default, type):
        raise ValueError("'{}' default value is not of type {}".format(default, type))
    return ignore_exception((ValueError), default)(type)(input(prompt, default))


def input_bool(prompt, default):
    return to_bool(input(prompt, default))


def input_float(prompt, default):
    return input_typed(prompt, default, float)


def input_int(prompt, default):
    return input_typed(prompt, default, int)


def input_str(prompt, default=""):
    return input_typed(prompt, default, str)


# ----------------------------------------------------------------------------------------
# Setup tools
# ----------------------------------------------------------------------------------------

class PackageInfo(object):
    def __init__(self, packageName):
        try:
            pkgInfo = message_from_string(pkg_resources.get_distribution(packageName).get_metadata('METADATA'))
        except:
            pkgInfo = message_from_string(pkg_resources.get_distribution(packageName).get_metadata('PKG-INFO'))

        for item in pkgInfo.items():
            if item[0] == "Version":
                self.version = item[1]
            elif item[0] == "Name":
                self.name = item[1]
            elif item[0] == "Summary":
                self.description = item[1]
            elif item[0] == "Author":
                self.author = item[1]
