#!/usr/bin/env python

import xml.etree.ElementTree as ET
import argparse
import StringIO
from os.path import realpath
from os.path import join as pathjoin
from os import makedirs
from os import symlink



def makeIvyXmlTree(org, module, revision, status="release"):
    ivy_module = ET.Element("ivy-module", {"version":"1.0"})
    info = ET.SubElement(ivy_module, "info", {"organisation":org, "module":module, "revision":revision, "status":status})
    info.text = " " # ensure a close tag
    confs = ET.SubElement(ivy_module, "configurations")
    for conf in ["default", "provided", "test"]:
        ET.SubElement(confs, "conf", {"name":conf})
    pubs = ET.SubElement(ivy_module, "publications")
    ET.SubElement(pubs, "artifact", {"name":module, "type":"jar"})

    return ET.ElementTree(ivy_module)

def writeIvyXml(org, module, revision, status="release", fileobj=None):
    if fileobj is None:
        fileobj = StringIO.StringIO()
    tree = makeIvyXmlTree(org, module, revision, status)
    tree.write(fileobj, xml_declaration=True)
    return fileobj

def ivyXmlAsString(org, module, revision, status):
    return writeIvyXml(org, module, revision, status).getvalue()

def placeArtifact(artifact_file, repo_dirname, org, module, revision, status="release"):
    repo_dir = realpath(repo_dirname)
    artifact_dir = pathjoin(*[repo_dir] + org.split(".") + [module, revision])
    ivyxml_path = pathjoin(artifact_dir, "ivy.xml")
    artifact_repo_path = pathjoin(artifact_dir, "%s-%s.jar" % (module, revision))
    makedirs(artifact_dir)
    ivyxml_file = open(ivyxml_path, "w")
    writeIvyXml(org, module, revision, status, ivyxml_file)
    symlink(artifact_file, artifact_repo_path)

def main():
    parser = argparse.ArgumentParser(description="Place a locally-installed artifact in a custom local Ivy repository")
    parser.add_argument("artifact_file", metavar="JAR", type=str, help="local JAR file to install")
    parser.add_argument("repo_dir", metavar="REPO", type=str, help="location for local repo")
    for val, desc in [("org", "organization"), ("module", "module"), ("revision", "revision")]:
        parser.add_argument(val, metavar=val.upper(), type=str, help="artifact %s" % desc)
    args = parser.parse_args()
    placeArtifact(args.artifact_file, args.repo_dir, args.org, args.module, args.revision)

if __name__ == "__main__":
    main()
