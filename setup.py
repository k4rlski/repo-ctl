from setuptools import setup, find_packages
setup(
    name="repo-ctl",
    version="0.3.0",
    packages=find_packages("src"),
    package_dir={"": "src"},
    install_requires=open("requirements.txt").read().splitlines(),
    entry_points={"console_scripts": ["repo-ctl=repo_ctl.main:cli"]},
)
