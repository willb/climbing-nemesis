#!/usr/bin/env python

import xml.etree.ElementTree as ET
import argparse
import StringIO
import re
import subprocess
import logging

from os.path import exists as pathexists
from os.path import realpath
from os.path import join as pathjoin
from os import makedirs
from os import symlink
from os import remove as rmfile

class Artifact(object):
    def __init__(self, a, g, v):
        self.artifact = a
        self.group = g
        self.version = v
    
    @classmethod
    def fromSubtree(k, t, ns):
        a = t.find("./%sartifactId" % ns).text
        g = t.find("./%sgroupId" % ns).text
        v = t.find("./%sversion" % ns).text
        return k(a, g, v)
    
    def __repr__(self):
        return "%s:%s:%s" % (self.group, self.artifact, self.version)

class DummyPOM(object):
    def __init__(self, groupID=None, artifactID=None, version=None):
        self.groupID = groupID
        self.artifactID = artifactID
        self.version = version

class POM(object):
    def __init__(self, filename, suppliedGroupID=None, suppliedArtifactID=None):
        self.filename = filename
        self.sGroupID = suppliedGroupID
        self.sArtifactID = suppliedArtifactID
        self.logger = logging.getLogger("com.freevariable.climbing-nemesis")
        self._parsePom()
    
    def _parsePom(self):
        tree = ET.parse(self.filename)
        project = tree.getroot()
        self.logger.info("parsing POM %s", self.filename)
        self.logger.debug("project tag is '%s'", project.tag)
        tagmatch = re.match("[{](.*)[}].*", project.tag)
        namespace = tagmatch and "{%s}" % tagmatch.groups()[0] or ""
        self.logger.debug("looking for '%s'", ("./%sgroupId" % namespace))
        groupIDtag = project.find("./%sgroupId" % namespace) 
        if groupIDtag is None:
            groupIDtag = project.find("./%sparent/%sgroupId" % (namespace,namespace))
        
        versiontag = project.find("./%sversion" % namespace)
        if versiontag is None:
            versiontag = project.find("./%sparent/%sversion" % (namespace,namespace))
        self.logger.debug("group ID tag is '%s'", groupIDtag)
        self.groupID = groupIDtag.text
        self.artifactID = project.find("./%sartifactId" % namespace).text
        self.version = versiontag.text
        depTrees = project.findall("./%sdependencyManagement/%sdependencies/%sdependency" % (namespace, namespace, namespace))
        self.deps = [Artifact.fromSubtree(depTree, namespace) for depTree in depTrees]
        jarmatch = re.match(".*JPP-(.*).pom", self.filename)
        self.jarname = (jarmatch and jarmatch.groups()[0] or None)

def cn_debug(*args):
    logging.getLogger("com.freevariable.climbing-nemesis").debug(*args)

def cn_info(*args):
    logging.getLogger("com.freevariable.climbing-nemesis").info(*args)

def resolveArtifact(group, artifact, pomfile=None, kind="jar"):
    # XXX: some error checking would be the responsible thing to do here
    if pomfile is None:
        try:
            [pom] = subprocess.check_output(["xmvn-resolve", "%s:%s:%s" % (group, artifact, kind)]).split()
            return POM(pom)
        except:
            return DummyPOM(group, artifact)
    else:
        return POM(pomfile)

def resolveArtifacts(identifiers):
    coords = ["%s:%s:jar" % (group, artifact) for (group, artifact) in identifiers]
    poms =  subprocess.check_output(["xmvn-resolve"] + coords).split()
    return [POM(pom) for pom in poms]

def resolveJar(group, artifact):
    [jar] = subprocess.check_output(["xmvn-resolve", "%s:%s:jar:jar" % (group, artifact)]).split()
    return jar

def makeIvyXmlTree(org, module, revision, status="release", meta={}):
    ivy_module = ET.Element("ivy-module", {"version":"2.0", "xmlns:e":"http://ant.apache.org/ivy/extra"})
    info = ET.SubElement(ivy_module, "info", dict({"organisation":org, "module":module, "revision":revision, "status":status}.items() + meta.items()))
    info.text = " " # ensure a close tag
    confs = ET.SubElement(ivy_module, "configurations")
    for conf in ["default", "provided", "test"]:
        ET.SubElement(confs, "conf", {"name":conf})
    pubs = ET.SubElement(ivy_module, "publications")
    ET.SubElement(pubs, "artifact", {"name":module, "type":"jar"})

    return ET.ElementTree(ivy_module)

def writeIvyXml(org, module, revision, status="release", fileobj=None, meta={}):
    if fileobj is None:
        fileobj = StringIO.StringIO()
    tree = makeIvyXmlTree(org, module, revision, status, meta)
    tree.write(fileobj, xml_declaration=True)
    return fileobj

def ivyXmlAsString(org, module, revision, status, meta={}):
    return writeIvyXml(org, module, revision, status, meta=meta).getvalue()

def placeArtifact(artifact_file, repo_dirname, org, module, revision, status="release", meta={}):
    repo_dir = realpath(repo_dirname)
    artifact_dir = pathjoin(*[repo_dir] + org.split(".") + [module, revision])
    ivyxml_path = pathjoin(artifact_dir, "ivy.xml")
    artifact_repo_path = pathjoin(artifact_dir, "%s-%s.jar" % (module, revision))
    
    if not pathexists(artifact_dir):
        makedirs(artifact_dir)
    
    ivyxml_file = open(ivyxml_path, "w")
    writeIvyXml(org, module, revision, status, ivyxml_file, meta)
    
    if pathexists(artifact_repo_path):
        rmfile(artifact_repo_path)
    
    symlink(artifact_file, artifact_repo_path)

def main():
    parser = argparse.ArgumentParser(description="Place a locally-installed artifact in a custom local Ivy repository; get metadata from Maven")
    parser.add_argument("group", metavar="GROUP", type=str, help="name of group")
    parser.add_argument("artifact", metavar="ARTIFACT", type=str, help="name of artifact")
    parser.add_argument("repodir", metavar="REPO", type=str, help="location for local repo")
    parser.add_argument("--version", metavar="VERSION", type=str, help="version to advertise this artifact as, overriding Maven metadata")
    parser.add_argument("--meta", metavar="K=V", type=str, help="extra metadata to store in ivy.xml", action='append')
    parser.add_argument("--jarfile", metavar="JAR", type=str, help="local jar file (use instead of POM metadata")
    parser.add_argument("--pomfile", metavar="POM", type=str, help="local pom file (use instead of xmvn-resolved one")
    parser.add_argument("--log", metavar="LEVEL", type=str, help="logging level")
    
    args = parser.parse_args()
    
    if args.log is not None:
        print args.log
        logging.basicConfig(level=getattr(logging, args.log.upper()))
    
    pom = resolveArtifact(args.group, args.artifact, args.pomfile, "jar")
    
    if args.jarfile is None:
        jarfile = resolveJar(pom.groupID or args.group, pom.artifactID or args.artifact)
    else:
        jarfile = args.jarfile
    
    version = (args.version or pom.version)
    
    meta = dict([kv.split("=") for kv in (args.meta or [])])
    cn_debug("meta is %r" % meta)
    
    placeArtifact(jarfile, args.repodir, pom.groupID, pom.artifactID, version, meta=meta)

if __name__ == "__main__":
    main()
