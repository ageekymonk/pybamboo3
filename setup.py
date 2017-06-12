#!/usr/bin/python
# -*- coding: utf-8 -*-

from setuptools import setup
from setuptools import find_packages


def get_version():
    with open('bamboo/__init__.py') as f:
        for line in f:
            if line.startswith('__version__'):
                return eval(line.split('=')[-1])

setup(
    name='pybamboo3',
    version=get_version(),
    description='Interact with Bamboo',
    author='Ramz',
    author_email='ramzthecoder@gmail.com',
    license='GPLv3',
    url='https://github.com/ageekymonk/pybamboo3',
    packages=find_packages(),
    install_requires=[
        'requests',
    ],
)
