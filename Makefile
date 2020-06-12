# Minarca Server
#
# Copyright (C) 2020 IKUS Software inc. All rights reserved.
# IKUS Software inc. PROPRIETARY/CONFIDENTIAL.
# Use is subject to license terms.
#
# Targets:
#    
#    test: 		Run the tests for all components.
#
#    build:		Generate distribution packages for all components 
#
# Define the distribution to be build: buster, stretch, sid, etc.
DIST ?= $(shell env -i bash -c '. /etc/os-release; echo $$VERSION_CODENAME')
PYTHON ?= python3
CI_PIPELINE_IID ?= 1
CI_PROJECT_NAME ?= minarca

#
# == Variables ==
#
# Version of pacakges base on git tags.
VERSION := $(shell curl -L https://gitlab.com/ikus-soft/maven-scm-version/-/raw/master/version.sh 2>/dev/null | bash)

# Release date for Debian pacakge
RELEASE_DATE = $(shell date '+%a, %d %b %Y %X') +0000

# Version specific to debian pacakges
# That include the distribution name
DEB_VERSION = ${VERSION}+${DIST}

# Use bash for pushd, popd
SHELL = bash

#
# == Main targets ==
#

all: test build

test: test-server test-quota-api test-client

build: build-client build-server

clean:
	rm -f minarca-server/debian/changelog
	rm -f authenticode-certs.pem
	rm -f authenticode.pem
	$(call docker_run,minarca-server,${DIST}-buildpackage,dpkg-buildpackage -Tclean)

version:
	@echo "${VERSION}"
	
debfile:
	@echo "${MINARCA_SERVER_DEB_FILE}"

.PHONY: all test build  test-server test-quota-api test-client test-client-deb test-client-exe build-client build-server prebuild $(DOCKER_IMAGES)

#
# == Prebuild ==
#

# List all docker images to be build.
DOCKER_IMAGES = $(subst tools/,build-,$(wildcard tools/*))

# Name few docker images that get reused
IMAGE_PYTHON = ${DOCKER_IMAGE_BASENAME}:${DIST}-${PYTHON}-${DOCKER_TAG}
IMAGE_JAVA = ${DOCKER_IMAGE_BASENAME}:${DIST}-java8-${DOCKER_TAG}
IMAGE_BUILDPACKAGE = ${DOCKER_IMAGE_BASENAME}:${DIST}-buildpackage-${DOCKER_TAG}
IMAGE_DEBIAN = buildpack-deps:${DIST}

# Check if running in gitlab CICD
CI ?=
ifeq ($(CI),true)
DOCKER_IMAGE_BASENAME = ${CI_REGISTRY_IMAGE}
DOCKER_TAG = ${CI_COMMIT_SHORT_SHA}
define docker_run
pushd $(1) >/dev/null && $(3) && popd >/dev/null
endef
else
DOCKER_IMAGE_BASENAME = ${CI_PROJECT_NAME}
DOCKER_TAG = latest
define docker_run
docker run --rm --user `id -u` -e TOXENV -v=`pwd`:/build -w=/build/$(1) $(2) $(3)
endef
endif

prebuild: $(DOCKER_IMAGES)

# Different target to build images.
ifeq ($(CI),true)
docker-%: tools/%
	@echo "running in CI - skip docker build $*"
	
build-%: tools/%
	-docker pull ${DOCKER_IMAGE_BASENAME}:$*-latest
	docker build --cache-from ${DOCKER_IMAGE_BASENAME}:$*-latest -t ${DOCKER_IMAGE_BASENAME}:$*-${DOCKER_TAG} -t ${DOCKER_IMAGE_BASENAME}:$*-latest $<
	docker push ${DOCKER_IMAGE_BASENAME}:$*-${DOCKER_TAG}
	docker push ${DOCKER_IMAGE_BASENAME}:$*-latest
else
docker-%: tools/%
	docker build -t ${DOCKER_IMAGE_BASENAME}:$*-${DOCKER_TAG} $<
endif

#
# == Tox ==
#
COMMA := ,
ifeq ($(PYTHON),python2)
TOXFACTOR=py2
else
TOXFACTOR=py3
endif
TOXENV=$(shell $(call docker_run,minarca-server,${IMAGE_PYTHON}, tox --listenvs | grep "${TOXFACTOR}" | tr "\n" "${COMMA}"))

test-server: docker-${DIST}-${PYTHON}
	export TOXENV=${TOXENV}; \
	$(call docker_run,minarca-server,${IMAGE_PYTHON},tox --sitepackages)

test-quota-api: docker-${DIST}-${PYTHON}
	export TOXENV=${TOXENV}; \
	$(call docker_run,minarca-quota-api,${IMAGE_PYTHON},tox --sitepackages)
	
#
# == Client ==
#
MINARCA_CLIENT_DEB_FILE = minarca-client_${VERSION}_all.deb
MINARCA_CLIENT_EXE_FILE = minarca-client_${VERSION}.exe

MAVEN_ARGS=-Drevision=${VERSION} -Duser.home=/tmp
ifneq ($(SONAR_URL),)
MAVEN_TEST_ARGS=-Dsonar.host.url=${SONAR_URL} -Dsonar.login=${SONAR_TOKEN} org.jacoco:jacoco-maven-plugin:prepare-agent install sonar:sonar
else
MAVEN_TEST_ARGS=org.jacoco:jacoco-maven-plugin:prepare-agent install org.jacoco:jacoco-maven-plugin:report
endif
	
test-client: docker-${DIST}-java8
	$(call docker_run,minarca-client,${IMAGE_JAVA},mvn ${MAVEN_ARGS} ${MAVEN_TEST_ARGS})
	
# Check if Authenticate is provided to sign the
# exe in windows build
ifdef AUTHENTICODE_CERT
MAVEN_BUILD_ARGS = -Dsign.certs.path=authenticode-certs.pem -Dsign.key.path=authenticode.pem -Dsign.passphrase=${AUTHENTICODE_PASSPHRASE}
endif
	
build-client: docker-${DIST}-java8
ifdef AUTHENTICODE_CERT
	echo "$${AUTHENTICODE_CERT}" > minarca-client/authenticode-certs.pem
	echo "$${AUTHENTICODE_KEY}" > minarca-client/authenticode.pem
endif
	$(call docker_run,minarca-client,${IMAGE_JAVA},mvn ${MAVEN_ARGS} ${MAVEN_BUILD_ARGS} clean install)
	$(call docker_run,.,${IMAGE_JAVA},mv minarca-client/minarca-installation-package-deb/target/minarca-installation-package-deb_*_all.deb ${MINARCA_CLIENT_DEB_FILE})
	$(call docker_run,.,${IMAGE_JAVA},mv minarca-client/minarca-installation-package/target/minarca-client-*.exe ${MINARCA_CLIENT_EXE_FILE})

${MINARCA_CLIENT_DEB_FILE}: build-client
${MINARCA_CLIENT_EXE_FILE}: build-client

test-client-deb: ${MINARCA_CLIENT_DEB_FILE}
	$(call docker_run,.,${IMAGE_DEBIAN},bash ./tests/install-server-deb.sh ${MINARCA_SERVER_DEB_FILE})

test-client-exe: ${MINARCA_CLIENT_EXE_FILE}
	$(call docker_run,.,${IMAGE_WINDOWS},bash ./tests/install-server-deb.sh ${MINARCA_SERVER_DEB_FILE})

#
# == Server ==
#
MINARCA_SERVER_DEB_FILE = minarca-server_${DEB_VERSION}_amd64.deb

${MINARCA_SERVER_DEB_FILE}: docker-${DIST}-buildpackage
	sed "s/%VERSION%/${VERSION}/" minarca-server/debian/changelog.in | sed "s/%DATE%/${RELEASE_DATE}/" > minarca-server/debian/changelog
	$(call docker_run,minarca-server,${IMAGE_BUILDPACKAGE},dpkg-buildpackage -us -uc)
	$(call docker_run,minarca-server,${IMAGE_BUILDPACKAGE},dpkg-buildpackage -Tclean)
	mv minarca-server_${VERSION}_amd64.deb minarca-server_${DEB_VERSION}_amd64.deb

build-server: ${MINARCA_SERVER_DEB_FILE}


#
# == Translation ==
#
gettext: gettext-client

gettext-client:
	$(call docker_run,minarca-client/minarca-core,${IMAGE_JAVA},mvn ${MAVEN_ARGS} gettext:gettext)
	$(call docker_run,minarca-client/minarca-core,${IMAGE_JAVA},mvn ${MAVEN_ARGS} gettext:merge)
	$(call docker_run,minarca-client/minarca-ui,${IMAGE_JAVA},mvn ${MAVEN_ARGS} gettext:gettext)
	$(call docker_run,minarca-client/minarca-ui,${IMAGE_JAVA},mvn ${MAVEN_ARGS} gettext:merge)

