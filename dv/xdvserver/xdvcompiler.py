from optparse import OptionParser

import os.path
import re
import sys
import urllib2

from lxml import etree

IMPORT_STYLESHEET_PATTERN = re.compile('@import url\\([\'"](.+)[\'"]\\);', re.I)

class WWWResolver(etree.Resolver):
    def resolve(self, system_url, public_id, context):
        try:
            data = urllib2.urlopen(system_url)
            return self.resolve_string(data.read(), context)
        except:
            pass

def to_absolute(src, prefix):
    if not (src.startswith('/') or '://' in src):
        if src.startswith('./'):
            return "%s/%s" % (prefix, src[2:])
        else:
            return "%s/%s" % (prefix, src)
    return src

def compile_theme(compiler, theme, rules, boilerplate, absolute_prefix=None, extraurl=None):
    """Invoke the xdv compiler
    """
    
    compiler = open(compiler)
    compiler_tree = etree.ElementTree(file=compiler)
    compiler_tree.parser.resolvers.add(WWWResolver())
    compiler_transform = etree.XSLT(compiler_tree)
    compiler.close()
    
    try:
        theme = urllib2.urlopen(theme)
    except:
        # Allow local file paths too
        theme = open(theme)
        
    parser = etree.HTMLParser()
    theme_tree = etree.ElementTree(file=theme, parser=parser)
    theme.close()
    
    if absolute_prefix:
        for node in theme_tree.xpath('*//style | *//script | *//img | *//link'):
            if node.tag == 'img' or node.tag == 'script':
                src = node.get('src')
                if src:
                    node.set('src', to_absolute(src, absolute_prefix))
            elif node.tag == 'link':
                href = node.get('href')
                if href:
                    node.set('href', to_absolute(href, absolute_prefix))
            elif node.tag == 'style':
                node.text = IMPORT_STYLESHEET_PATTERN.sub('@import url("%s/\\1");' % absolute_prefix, node.text)
    
    params = dict(rulesuri="'%s'" % prepare_filename(rules))
    if boilerplate:
        params['boilerplateurl'] = "'%s'" % prepare_filename(boilerplate)
    
    if extraurl:
        params['extraurl'] = "'%s'" % prepare_filename(extraurl)
        
    compiled = compiler_transform(theme_tree, **params)
    
    return etree.tostring(compiled)

def prepare_filename(filename):
    """Make file name string parameters compatible with xdv's compiler.xsl
    """

    if not re.match('(http|https|ftp)://', filename.lower()):
        filename = os.path.abspath(filename)
        if sys.platform.startswith('win'):
            # compiler.xsl on Windows wants c:/foo/bar instead of C:\foo\bar
            filename = filename.replace('\\', '/')
        
    return filename

def compile():
    """Called fromconsole script
    """
    
    
    parser = OptionParser(usage="usage: %prog [options] output.xslt")
    parser.add_option("-c", "--compiler", metavar="compiler.xsl",
                      help="Path to compiler.xsl",
                      dest="compiler", default=None)
    parser.add_option("-t", "--theme", metavar="http://example.org/test.html",
                      help="URI to the theme file",
                      dest="theme", default=None)
    parser.add_option("-r", "--rules", metavar="rules.xml",
                      help="XDV rules file filename", 
                      dest="rules", default=None)
    parser.add_option("-b", "--boilerplate", metavar="boilerplate.xsl",
                      help="XDV boilerplate XSLT file",
                      dest="boilerplate", default=None)
    parser.add_option("-e", "--extraurl", metavar="extraurl.xsl",
                      help="XDV extraurl XSLT file",
                      dest="extraurl", default=None)
    parser.add_option("-a", "--absolute-prefix", dest="absolute_prefix", metavar="http://example.org/mysite",
                      help="URL prefix used to turn relative links into absolute ones",
                      default=None)

    (options, args) = parser.parse_args()

    if len(args) != 1:
        parser.error("No output file specified")

    if options.theme is None:
        parser.error("No theme specified")
        
    if options.rules is None:
        parser.error("No rules file specified")

    if options.compiler is None:
        options.compiler = os.path.join(os.path.split(__file__)[0], 'compiler', 'compiler.xsl')
    
    output_xslt = compile_theme(options.compiler, options.theme,
                                options.rules, options.boilerplate,
                                options.absolute_prefix, options.extraurl)
    
    output = open(args[0], 'w')
    output.write(output_xslt)
    output.close()
