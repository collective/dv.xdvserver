Introduction
============

dv.xdvserver is a simple piece of WSGI middleware that can execute the two
step compile-and-run XSLT transforms of xdv.

It takes two required parameters:

 - rules: a path to a file containing Deliverance rules
 - theme: a URI or path to a theme HTML file

In addition, it can take several optional parameters:

 - absolute_prefix: if given, relative urls in the theme file will be made
    into absolute links with this prefix.
 - notheme: a set of regular expression patterns (or just simple names) that
    will be matched against the incoming path to allow the theme to be
    switched off for some paths. Multiple patterns should be separated by
    newlines.
 - live: set to True to recompile the theme on each request, rather than on
    startup only.
 - compiler: a path to the XSLT file that can turn theme+rules into a compiled
    theme. The default, bundled version will probably suffice in most cases.
 - boilerplate: a path to the XSLT file that contains boilerplate XSLT
    instructions. The default, bundled version will probably suffice in most
    cases.
    
Configuration
=============

You can use this middleware in a Paste Deploy pipeline. Here is an example 
configuration file of an application that themes a Plone site running on
http://localhost:8080/demo. Static resources are served from /static.

    [server:main]
    use = egg:Paste#http
    host = 127.0.0.1
    port = 5000

    [composite:main]
    use = egg:Paste#urlmap
    /static = static
    / = default

    [app:static]
    use = egg:Paste#static
    document_root = %(here)s/static

    [pipeline:default]
    pipeline = egg:Paste#cgitb
               egg:Paste#httpexceptions
               theme.default
               zope.proxy

    [filter:theme.default]
    use = egg:dv.xdvserver#xdv
    theme = %(here)s/static/index.html
    rules = %(here)s/static/rules/default.xml
    notheme =
        /emptypage

    [app:zope.proxy]
    use = egg:Paste#proxy
    address = http://localhost:8080/VirtualHostBase/http/localhost:5000/demo/VirtualHostRoot/