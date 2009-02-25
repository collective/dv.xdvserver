from optparse import OptionParser

import os.path
import re
import urllib2

from lxml import etree

IMPORT_STYLESHEET_PATTERN = re.compile('@import url\\([\'"](.+)[\'"]\\);', re.I)

def to_absolute(src, prefix):
    if not (src.startswith('/') or '://' in src):
        if src.startswith('./'):
            return "%s/%s" % (prefix, src[:2])
        else:
            return "%s/%s" % (prefix, src)
    return src

def compile_theme(compiler, theme_uri, rules, boilerplate, absolute_prefix=None):
    """Invoke the xdv compiler
    """
    
    compiler = open(compiler)
    compiler_transform = etree.XSLT(etree.ElementTree(file=compiler))
    compiler.close()
    
    theme = urllib2.urlopen(theme_uri)
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
    
    compiled = compiler_transform(theme_tree,
                                  rulesuri="'%s'" % rules,
                                  boilerplateurl="'%s'" % boilerplate)
    
    return etree.tostring(compiled)
    
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
    if options.boilerplate is None:
        options.boilerplate = os.path.join(os.path.split(__file__)[0], 'compiler', 'boilerplate.xsl')
    
    
    
    output_xslt = compile_theme(options.compiler, options.theme,
                                options.rules, options.boilerplate,
                                options.absolute_prefix)
    
    output = open(args[0], 'w')
    output.write(output_xslt)
    output.close()
