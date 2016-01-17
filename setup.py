#!/usr/bin/env python
# -*- coding: utf-8 -*-

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(name='tingplay',
      version='0.1',
      description='UPnP player for tingbot',
      url='http://github.com/furbrain/tingbot-gui',
      author='Phil Underwood',
      author_email='beardydoc@gmail.com',
      license='BSD',
      packages=['tingplayer'],
      install_requires=['tingbot_gui'],
      dependency_links=['https://github.com/furbrain/tingbot-gui/tarball/master'],
      zip_safe=False,
      keywords='tingbot',)
