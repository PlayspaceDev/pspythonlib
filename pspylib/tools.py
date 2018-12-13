#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2018 - Playspace
import inspect
import argcomplete
import tempfile
import subprocess
from pspylib.common import *

__version__ = "1.0.0"
__author__ = "Playspace Dev Team"
__copyright__ = "Playspace SL - 2018"
__description__ = "Flexible CLI tool - v{version} {copyright}"

registered_tools = {}
instanced_tools = {}
tool_origin = None


class ITool:
    def __init__(self, parser, tmpdir):
        raise NotImplementedError(
            'Tool "{}" must implement own __init__(self, parser, tmpdir) method'.format(str(self.__class__)))

    def execute(self, args, tmpdir):
        raise NotImplementedError(
            'Tool "{}" must implement own execute(self, args, tmpdir) method'.format(str(self.__class__)))


def get_available_tools():
    global registered_tools
    return list(registered_tools.keys())


def init_tools(parser, tmpdir):
    for tool_name in registered_tools:
        tool_parser = parser.add_parser(tool_name, help=registered_tools[tool_name]['help'])
        try:
            instanced_tools[tool_name] = registered_tools[tool_name]['cls'](tool_parser, tmpdir)
        except Exception as e:
            log_error("Failed to instance tool {tool} due to {error}", tool=tool_name, error=e)


def execute_tool(tool_name, args, tmpdir):
    global registered_tools
    if tool_name in registered_tools:
        return instanced_tools[tool_name].execute(args, tmpdir)
    raise NotImplementedError('Tool "{}" not registered'.format(tool_name))


def register_tool(name=None, help=None):
    """
    Makes a class to be available as a ITool
    """

    def toolify(cls):
        if inspect.isclass(cls):
            tool_name = name
            if tool_name is None:
                tool_name = cls.__name__
            if tool_name in registered_tools:
                raise NotImplementedError('Tool "{}" with name "{}" already registered'.format(str(cls), tool_name))
            registered_tools[tool_name] = {'cls': cls, 'help': help}
        else:
            raise NotImplementedError('Tool "{}" must be a class if type ITool'.format(str(cls)))
        return cls

    return toolify


@register_tool("upgrade", "Download the latest version of the tool and install it")
class UpgradeTool(ITool):
    def __init__(self, parser, tmpdir):
        global tool_origin
        parser.add_argument('-o', '--origin', help='The git origin, by default pointing to our base git', type=str,
                            default=tool_origin, required=False)
        parser.add_argument('--user', action='store_true', default=False,
                            help='Install pstool into the user environment', required=False)

    def execute(self, args, tmpdir):
        import pip

        install_dir = tempfile.mkdtemp()
        execute_cmd(["git", "clone", "--depth=1", args.origin, install_dir])
        pwd = os.getcwd()
        try:
            os.chdir(install_dir)
            if args.user:
                log_debug("Installing for current user")
            else:
                log_debug("Installing system wide")
                
            f = open("_install.py","w+")
            f.write("\n".join(
                [ 'from time import sleep'
                , 'import pip, sys, shutil, stat, os'
                , 'from colorama import init, Fore, Style'
                , 'init(autoreset=True)'
                , 'def purge_dir(dir_path):'
                , '    if os.path.isdir(dir_path):'
                , '        def del_evenReadonly(action, name, exc):'
                , '            os.chmod(name, stat.S_IWRITE)'
                , '            os.remove(name)'
                , '        shutil.rmtree(dir_path, onerror=del_evenReadonly)'
                , 'sleep(1)'
                , 'pwd = os.getcwd()'
                , 'try:'
                , '    pip_args = ["install", ".", "--process-dependency-links"]' + (' + ["--user"]' if user else '')
                , '    if hasattr(pip, "main"):'
                , '        result_code = pip.main(pip_args)'
                , '    else:'
                , '        from pip import _internal'
                , '        result_code = pip._internal.main(pip_args)'
                , '    if result_code != 0:'
                , '        print(Fore.RED + "Upgrade failed! Check the log for more info...", file=sys.stderr)'
                , '    else:'
                , '        print(Fore.GREEN + "Upgrade successful! Enjoy!")'
                , 'finally:'
                , '    os.chdir("..")'
                , '    purge_dir(pwd)']))
            f.close()
            p = subprocess.Popen(['python', '_install.py'])
            log_debug("Install process started, please wait for it to finish!")
        finally:
            os.chdir(pwd)
            #purge_dir(install_dir)


def main_tool(argv=None, description=__description__, version=__version__, copyright=__copyright__, author=__author__,
              origin=None):
    global tool_origin
    tool_origin = origin

    if argv is None:
        argv = sys.argv

    parser = argparse.ArgumentParser(add_help=True, argument_default=argparse.SUPPRESS,
                                     description=description.format(version=version, copyright=copyright,
                                                                    author=author))
    parser.add_argument('--clean', action='store_true', default=False, help='Runs the action in clean mode',
                        required=False)
    parser.add_argument('--dryrun', action='store_true', default=False, help='Run the action in dryrun mode',
                        required=False)
    parser.add_argument('--force', action='store_true', default=False,
                        help='Running in force mode will force the action to start in any case', required=False)
    parser.add_argument('--interactive', action='store_true', default=False,
                        help='Running the CLI in interactive mode', required=False)

    # Generate a temporal directory for the whole thing
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Add first parser in the nested tree
            subparser = parser.add_subparsers(dest='tool', help='Available tools')
            subparser.required = True
            init_tools(subparser, tmpdir)
            argcomplete.autocomplete(parser)

            if '--interactive' in argv:
                log_info("Welcome to the interactive console. Type 'q' or 'quit' to exit the console.")
                while True:

                    command = input_str('$').lower()
                    if command == 'q' or command == 'quit':
                        break

                    try:
                        args = parser.parse_args(command.split() + ['--interactive'])
                        execute_tool(args.tool, args, tmpdir)
                    except SystemExit:
                        continue

                return EXIT_CODE_SUCCESS
            else:
                args = parser.parse_args(argv)
                return execute_tool(args.tool, args, tmpdir)
        finally:
            for int_dir in list_dirs(tmpdir):
                purge_dir(int_dir)
