.PHONY: clean clean-test clean-pyc clean-build docs help
.DEFAULT_GOAL := help

help:
# http://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

VERSION?=0.3.0.dev0

TOREE_LAUNCHER_FILES:=$(shell find remote_provisioners/kernel-launchers/scala/toree-launcher/src -type f -name '*')


clean: clean-build clean-pyc clean-test ## remove all build, test, coverage and Python artifacts

clean-build: ## remove build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr remote_provisioners/kernel-launchers/scala/lib
	rm -fr remote_provisioners/kernel-launchers/scala/toree-launcher/target
	rm -fr remote_provisioners/kernel-launchers/scala/toree-launcher/project/target
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +

clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test: ## remove test and coverage artifacts
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache

lint: ## check style with flake8
	flake8 remote_provisioners 

test: ## run tests quickly with the default Python
	pytest -v --cov remote_provisioners remote_provisioners

docs: ## generate Sphinx HTML documentation, including API docs
	rm -f docs/remote_provisioners.rst
	rm -f docs/modules.rst
	sphinx-apidoc -o docs/ remote_provisioners
	$(MAKE) -C docs clean
	$(MAKE) -C docs html

release: dist ## package and upload a release
	twine upload dist/*

dist: clean remote_provisioners/kernel-launchers/scala/lib ## builds source and wheel package
	python setup.py sdist
	python setup.py bdist_wheel
	ls -l dist

install: clean ## install the package to the active Python's site-packages
	python setup.py install


remote_provisioners/kernel-launchers/scala/lib: $(TOREE_LAUNCHER_FILES)
	-rm -rf remote_provisioners/kernel-launchers/scala/lib
	mkdir -p remote_provisioners/kernel-launchers/scala/lib
	@(cd remote_provisioners/kernel-launchers/scala/toree-launcher; sbt -Dversion=$(VERSION) package; cp target/scala-2.11/*.jar ../lib)
	curl -L https://repository.apache.org/content/repositories/releases/org/apache/toree/toree-assembly/0.3.0-incubating/toree-assembly-0.3.0-incubating.jar --output ./remote_provisioners/kernel-launchers/scala/lib/toree-assembly-0.3.0-incubating.jar

