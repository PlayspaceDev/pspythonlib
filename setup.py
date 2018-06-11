#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (C) 2018 - Playspace

from setuptools.command.install import install as _install
from setuptools import setup, find_packages
import subprocess
import sys
import distutils.command.install as orig

class install(_install):
    def run(self):
        subprocess.run(["pip3", "install", "-r", "requirements", "--upgrade"], check=True)
        #_install.do_egg_install(self)
        orig.install.run(self)

setup(
        name="pspylib",
        version="0.0.1",
        description="Playspace shared python library",
        author="Playspace Dev Team",
        packages=find_packages(),
        cmdclass={
            'install': install
        }
)
