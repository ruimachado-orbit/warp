#!/usr/bin/env python3
"""Setup configuration for Warp"""

from pathlib import Path
from setuptools import setup, find_packages

# Read the README for long description
README = (Path(__file__).parent / "README.md").read_text()

# Read requirements
REQUIREMENTS = (Path(__file__).parent / "requirements.txt").read_text().splitlines()
REQUIREMENTS = [r.strip() for r in REQUIREMENTS if r.strip() and not r.startswith('#')]

setup(
    name="warp-agent",
    version="0.1.0",
    description="Autonomous customer support operations agent",
    long_description=README,
    long_description_content_type="text/markdown",
    author="Maio Labs",
    author_email="hello@maiolabs.com",
    url="https://github.com/ruimachado-orbit/warp",
    packages=find_packages(where="src"),
    py_modules=["cli", "config", "llm_gateway", "orchestrator"],
    package_dir={"": "src"},
    python_requires=">=3.12",
    install_requires=REQUIREMENTS,
    entry_points={
        "console_scripts": [
            "warp=cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords="ai agent llm automation customer-support helpdesk",
    project_urls={
        "Bug Reports": "https://github.com/ruimachado-orbit/warp/issues",
        "Source": "https://github.com/ruimachado-orbit/warp",
    },
)
