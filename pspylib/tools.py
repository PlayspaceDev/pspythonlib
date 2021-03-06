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
__copyright__ = "Playspace SL - 2019"
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

def find_tools(root):
    root_package = os.path.basename(root)
    packages = []
    for dirname, _, filenames in os.walk(root):
        if '__init__.py' in filenames:
            for package in filenames:
                if '__init__.py' != package:
                    file_path = os.path.join(dirname, package)
                    if file_contains(file_path, b'register_tool'):
                        packages.append('.'.join([root_package, to_module_path(os.path.relpath(file_path, root))]))
    for package in packages:
        try:
            __import__(package)
        except Exception as e:
            log_error("Failed to load tool '{0}' due to: '{1}' ", package, e)
            pass

def init_tools(root, parser, tmpdir):
    find_tools(root)
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

def main_tool(root, argv=None, description=__description__, version=__version__, copyright=__copyright__, author=__author__, origin=None):
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
    parser.add_argument('--gui', action='store_true', default=False,
                        help='Run the tool with a nice and simple UI', required=False)

    # Generate a temporal directory for the whole thing
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Add first parser in the nested tree
            subparser = parser.add_subparsers(dest='tool', help='Available tools')
            subparser.required = True
            init_tools(root, subparser, tmpdir)
            argcomplete.autocomplete(parser)

            if '--interactive' in argv:
                log_info("Welcome to the interactive console. Type 'q', 'quit' or 'exit' to exit the console.")
                while True:

                    command = input_str('$').lower()
                    if command == 'q' or command == 'quit' or command == 'exit':
                        break

                    try:
                        args = parser.parse_args(command.split())
                        execute_tool(args.tool, args, tmpdir)
                    except SystemExit:
                        continue

                return EXIT_CODE_SUCCESS
            elif '--gui' in argv:
                log_error("Not yet pal implemented")
            else:
                args = parser.parse_args(argv)
                return execute_tool(args.tool, args, tmpdir)
        finally:
            for int_dir in list_dirs(tmpdir):
                purge_dir(int_dir)
