#!/usr/bin/env python

import xml.etree.ElementTree as ET
import argparse
import StringIO
import re
import subprocess

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
        a = t.find("./{%s}artifactId" % ns).text
        g = t.find("./{%s}groupId" % ns).text
        v = t.find("./{%s}version" % ns).text
        return k(a, g, v)
    
    def __repr__(self):
        return "%s:%s:%s" % (self.group, self.artifact, self.version)

class POM(object):
    def __init__(self, filename):
        self.filename = filename
        self._parsePom()
    
    def _parsePom(self):
        tree = ET.parse(self.filename)
        project = tree.getroot()
        namespace = re.match("[{](.*)[}].*", project.tag).groups()[0]
        self.groupID = project.find("./{%s}groupId" % namespace).text
        self.artifactID = project.find("./{%s}artifactId" % namespace).text
        self.version = project.find("./{%s}version" % namespace).text
        depTrees = project.findall("./{%s}dependencyManagement/{%s}dependencies/{%s}dependency" % (namespace, namespace, namespace))
        self.deps = [Artifact.fromSubtree(depTree, namespace) for depTree in depTrees]
        self.jarname = re.match(".*JPP-(.*).pom", self.filename).groups()[0]

def resolveArtifact(group, artifact, kind="jar"):
    # XXX: some error checking would be the responsible thing to do here
    [pom] = subprocess.check_output(["xmvn-resolve", "%s:%s:%s" % (group, artifact, kind)]).split()
    return POM(pom)

def resolveArtifacts(identifiers):
    coords = ["%s:%s:jar" % (group, artifact) for (group, artifact) in identifiers]
    poms =  subprocess.check_output(["xmvn-resolve"] + coords).split()
    return [POM(pom) for pom in poms]

def resolveJar(artifact):
    return subprocess.check_output(["build-classpath", artifact]).split()[0]

def makeIvyXmlTree(org, module, revision, status="release", meta={}):
    ivy_module = ET.Element("ivy-module", {"version":"1.0"})
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
    tree = makeIvyXmlTree(org, module, revision, status)
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
    writeIvyXml(org, module, revision, status, ivyxml_file)
    
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
    
    args = parser.parse_args()
    
    if args.jarfile is None:
        pom = resolveArtifact(args.group, args.artifact)
        jarfile = resolveJar(pom.jarname)
    else:
        jarfile = args.jarfile
    
    version = (args.version or pom.version)

    
    meta = dict([kv.split("=") for kv in (args.meta or [])])

    placeArtifact(jarfile, args.repodir, pom.groupID, pom.artifactID, version, meta=meta)

if __name__ == "__main__":
    main()
