#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (C) 2018 - Playspace

from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="pspylib",
    version="0.0.10",
    description="Playspace shared python library",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Playspace Dev Team",
    author_email="developers@playspace.com",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        "argcomplete",
        "psutil",
        "gitpython",
        "colorama",
    ],
)
