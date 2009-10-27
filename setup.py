from setuptools import setup, find_packages
import os

version = '1.0b7'

setup(name='dv.xdvserver',
      version=version,
      description="A server for the Deliverance/XSLT compiler",
      long_description=open("README.txt").read() + "\n" +
                       open(os.path.join("docs", "HISTORY.txt")).read(),
      # Get more strings from http://www.python.org/pypi?%3Aaction=list_classifiers
      classifiers=[
        "Framework :: Plone",
        "Programming Language :: Python",
        "Topic :: Software Development :: Libraries :: Python Modules",
        ],
      keywords='Deliverance XSLT WSGI',
      author='Martin Aspeli',
      author_email='optilude@gmail.com',
      url='http://open-plans.org/projects/deliverance',
      license='BSD',
      packages=find_packages(exclude=['ez_setup']),
      namespace_packages=['dv'],
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          'setuptools',
          'PasteDeploy',
          'PasteScript',
          'lxml',
          # -*- Extra requirements: -*-
      ],
      entry_points="""
      [console_scripts]
      xdvcompiler = dv.xdvserver.xdvcompiler:compile
      
      [paste.filter_app_factory]
      xslt = dv.xdvserver.filter:XSLTMiddleware
      xdv = dv.xdvserver.filter:XDVMiddleware
      """,
      )
