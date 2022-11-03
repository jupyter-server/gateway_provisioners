.PHONY: build-dependencies clean-test clean-pyc clean-build docs help \
	rp-base rp-spark-base rp-kernel-py rp-kernel-py rp-kernel-spark-py \
	rp-kernel-r rp-kernel-spark-r rp-kernel-scala
.DEFAULT_GOAL := help

help:
# http://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# extract version from remote_provisioners/_version.py - override using `make VERSION=foo target`
VERSION?=$(shell grep ^__version__ remote_provisioners/_version.py | awk '{print $$3}' | sed s'/"//g')

# When building images, where to get the remote-provisioners package: "local" (wheel) or "release" (pip)
PACKAGE_SOURCE?=local

# Docker attributes - hub organization and tag.  Modify accordingly
DOCKER_ORG?=elyra

# Determine TAG from VERSION. If contains "dev", use dev, else VERSION
ifeq (dev, $(findstring dev, $(VERSION)))
    TAG:=dev
else
    TAG:=$(VERSION)
endif

# Set NO_CACHE=--no-cache to force docker build to not use cached layers
NO_CACHE?=

SPARK_VERSION?=3.3.1

WHEEL_FILES:=$(shell find remote_provisioners -type f ! -path "*/__pycache__/*" )
WHEEL_FILE:=dist/remote_provisioners-$(VERSION)-py3-none-any.whl
SDIST_FILE:=dist/remote_provisioners-$(VERSION).tar.gz
DIST_FILES=$(WHEEL_FILE) $(SDIST_FILE)

TOREE_LAUNCHER_FILES:=$(shell find remote_provisioners/kernel-launchers/scala/toree-launcher/src -type f -name '*')

echo-version:
	@echo $(VERSION)

build-dependencies: ## install packages necessary to complete the build
	@pip install -q pre-commit
	@pip install -q build
	@pip install -q hatchling

clean: clean-build clean-pyc clean-test ## remove all build, test, coverage and Python artifacts

clean-build: ## remove build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf remote_provisioners/kernel-launchers/scala/lib
	rm -rf remote_provisioners/kernel-launchers/scala/toree-launcher/target
	rm -rf remote_provisioners/kernel-launchers/scala/toree-launcher/project/target
	rm -rf .eggs/
	find . -name '*.egg-info' -exec rm -rf {} +
	find . -name '*.egg' -exec rm -f {} +

clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -rf {} +

clean-test: ## remove test and coverage artifacts
	rm -f .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache

lint: build-dependencies ## check style with flake8
	pre-commit run --all-files

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

dist: wheel sdist  ## builds wheel and source packages
	ls -l dist

sdist: $(SDIST_FILE)

$(SDIST_FILE): $(WHEEL_FILES)
	python -m build --sdist

wheel: remote_provisioners/kernel-launchers/scala/lib $(WHEEL_FILE)

$(WHEEL_FILE): $(WHEEL_FILES)
	python -m build --wheel

install: clean wheel ## install the package to the active Python's site-packages
	pip uninstall -y remote-provisioners
	pip install dist/remote_provisioners-*.whl

remote_provisioners/kernel-launchers/scala/lib: $(TOREE_LAUNCHER_FILES)
	-rm -rf remote_provisioners/kernel-launchers/scala/lib
	mkdir -p remote_provisioners/kernel-launchers/scala/lib
	@(cd remote_provisioners/kernel-launchers/scala/toree-launcher; sbt -Dversion=$(VERSION) package; cp target/scala-2.12/*.jar ../lib)

BASE_IMAGES := rp-base rp-spark-base
KERNEL_IMAGES := rp-kernel-py rp-kernel-spark-py rp-kernel-r rp-kernel-spark-r rp-kernel-scala
DOCKER_IMAGES := $(BASE_IMAGES) $(KERNEL_IMAGES)

base-images: $(BASE_IMAGES)
kernel-images: $(KERNEL_IMAGES)
images: $(DOCKER_IMAGES)  ## Build all docker images.  Targets base-images and kernel-images can also be used.
clean-base-images: clean-rp-base clean-rp-spark-base
clean-kernel-images: clean-rp-kernel-py clean-rp-kernel-spark-py clean-rp-kernel-r clean-rp-kernel-spark-r clean-rp-kernel-scala
clean-images: clean-base-images clean-kernel-images  ## Remove all docker images.  Targets clean-base-images and clean-kernel-images can also be used.
push-base-images: push-rp-base push-rp-spark-base
push-kernel-images: push-rp-kernel-py push-rp-kernel-spark-py push-rp-kernel-r push-rp-kernel-spark-r push-rp-kernel-scala
push-images: push-base-images push-kernel-images  ## Push all docker images.  Targets push-base-images and push-kernel-images can also be used.

# Location to find docker files used in build
DOCKER_rp-base := remote_provisioners/docker/rp-base
DOCKER_rp-spark-base := remote_provisioners/docker/rp-spark-base
DOCKER_rp-kernel-py := remote_provisioners/docker/kernel-image
DOCKER_rp-kernel-spark-py := remote_provisioners/docker/kernel-image
DOCKER_rp-kernel-r := remote_provisioners/docker/kernel-image
DOCKER_rp-kernel-spark-r := remote_provisioners/docker/kernel-image
DOCKER_rp-kernel-scala := remote_provisioners/docker/kernel-image

#
BUILD_ARGS_rp-base :=
BUILD_ARGS_rp-spark-base := --build-arg SPARK_VERSION=${SPARK_VERSION}
BUILD_ARGS_rp-kernel-py := --build-arg PACKAGE_SOURCE=${PACKAGE_SOURCE} \
						   --build-arg KERNEL_LANG=python
BUILD_ARGS_rp-kernel-spark-py := ${BUILD_ARGS_rp-kernel-py} \
								 --build-arg BASE_CONTAINER=${DOCKER_ORG}/rp-spark-base:$(TAG)
BUILD_ARGS_rp-kernel-r := --build-arg PACKAGE_SOURCE=${PACKAGE_SOURCE} \
						  --build-arg KERNEL_LANG=r
BUILD_ARGS_rp-kernel-spark-r := ${BUILD_ARGS_rp-kernel-r} \
								--build-arg BASE_CONTAINER=${DOCKER_ORG}/rp-spark-base:$(TAG)
BUILD_ARGS_rp-kernel-scala := --build-arg PACKAGE_SOURCE=${PACKAGE_SOURCE} \
							  --build-arg KERNEL_LANG=scala \
							  --build-arg BASE_CONTAINER=${DOCKER_ORG}/rp-spark-base:$(TAG)

# Extra (besides docker files) dependencies for each docker image...
DEPENDS_rp-base :=
DEPENDS_rp-spark-base :=
DEPENDS_rp-kernel-py := $(WHEEL_FILE)
DEPENDS_rp-kernel-spark-py := $(WHEEL_FILE)
DEPENDS_rp-kernel-r := $(WHEEL_FILE)
DEPENDS_rp-kernel-spark-r := $(WHEEL_FILE)
DEPENDS_rp-kernel-scala := $(WHEEL_FILE)

# Extra targets for each image
TARGETS_rp-base:
TARGETS_rp-spark-base:
TARGETS_rp-kernel-py TARGETS_rp-kernel-py TARGETS_rp-kernel-spark-py TARGETS_rp-kernel-r \
	TARGETS_rp-kernel-spark-r TARGETS_rp-kernel-scala: wheel $(BASE_IMAGES)

# Generate image creation targets for each entry in $(DOCKER_IMAGES).  Switch 'eval' to 'info' to see what is produced.
define BUILD_IMAGE
$1: .image-$1
.image-$1: $$(DOCKER_$1)/* $$(DEPENDS_$1)
	@make clean-$1 TARGETS_$1
	@mkdir -p build/docker/$1
	@cp -r $$(DOCKER_$1)/* $$(DEPENDS_$1) build/docker/$1
	(cd build/docker/$1; \
				docker build ${NO_CACHE} \
					--build-arg DOCKER_ORG=${DOCKER_ORG} \
					$$(BUILD_ARGS_$1) \
					-t $(DOCKER_ORG)/$1:$(TAG) .\
	)
	@touch .image-$1
	@-docker images $(DOCKER_ORG)/$1:$(TAG)
endef
$(foreach image,$(DOCKER_IMAGES),$(eval $(call BUILD_IMAGE,$(image))))

# Generate clean-xxx targets for each entry in $(DOCKER_IMAGES).  Switch 'eval' to 'info' to see what is produced.
define CLEAN_IMAGE
clean-$1:
	@rm -f .image-$1
	@-docker rmi -f $(DOCKER_ORG)/$1:$(TAG)
endef
$(foreach image,$(DOCKER_IMAGES),$(eval $(call CLEAN_IMAGE,$(image))))

# Publish each publish image on $(PUSHED_IMAGES) to DockerHub.  Switch 'eval' to 'info' to see what is produced.
define PUSH_IMAGE
push-$1:
	docker push $(DOCKER_ORG)/$1:$(TAG)
endef
$(foreach image,$(PUSHED_IMAGES),$(eval $(call PUSH_IMAGE,$(image))))
