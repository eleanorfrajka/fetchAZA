#!/usr/bin/env python3

import subprocess
import sys
import re

def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()

def get_latest_tag():
    try:
        return run(["git", "describe", "--tags", "--abbrev=0"])
    except subprocess.CalledProcessError:
        return None

def get_current_branch():
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"])

def get_commit_distance(tag):
    out = run(["git", "rev-list", f"{tag}..HEAD", "--count"])
    return int(out)

def suggest_next_version(tag):
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)([a-z]+\d+)?", tag)
    if not match:
        return "0.1.0"
    major, minor, patch, suffix = match.groups()
    if suffix and "a" in suffix:
        num = int(suffix[1:])
        return f"{major}.{minor}.{patch}a{num+1}"
    else:
        return f"{major}.{minor}.{int(patch)+1}"

def main():
    if get_current_branch() != "main":
        print("⚠️  You are not on the 'main' branch. Aborting.")
        sys.exit(1)

    latest_tag = get_latest_tag()
    print(f"🔖 Latest tag: {latest_tag or 'None'}")

    if latest_tag and get_commit_distance(latest_tag) == 0:
        print("✅ No new commits since last tag. Nothing to release.")
        sys.exit(0)

    suggested = suggest_next_version(latest_tag or "v0.0.0")
    version = input(f"📦 Enter version tag to create [{suggested}]: ").strip() or suggested

    if not re.match(r"^v?\d+\.\d+\.\d+([a-z]+\d+)?$", version):
        print("❌ Version must match PEP 440 style (e.g., v0.1.0, v0.2.0a1)")
        sys.exit(1)

    version = version if version.startswith("v") else f"v{version}"

    print(f"🏷 Tagging commit with {version}...")
    run(["git", "tag", version])
    run(["git", "push", "origin", version])
    print("✅ Tag pushed successfully.")

if __name__ == "__main__":
    main()

