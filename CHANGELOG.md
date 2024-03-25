# Changelog

<!-- <START NEW CHANGELOG ENTRY> -->

## 0.4.0

([Full Changelog](https://github.com/jupyter-server/gateway_provisioners/compare/v0.2.0...b47b9a33ca19e50359248d7cb91dff35f1daf564))

### Enhancements made

- Fix k8s pre_launch key error and add debug log [#127](https://github.com/jupyter-server/gateway_provisioners/pull/127) ([@BetterLevi](https://github.com/BetterLevi))

### Bugs fixed

- Address CI failures [#128](https://github.com/jupyter-server/gateway_provisioners/pull/128) ([@blink1073](https://github.com/blink1073))
- Fix kernel-class-name option [#124](https://github.com/jupyter-server/gateway_provisioners/pull/124) ([@mmmommm](https://github.com/mmmommm))
- Update docker_swarm.py [#85](https://github.com/jupyter-server/gateway_provisioners/pull/85) ([@bsdz](https://github.com/bsdz))

### Maintenance and upkeep improvements

- Update dependabot config [#130](https://github.com/jupyter-server/gateway_provisioners/pull/130) ([@blink1073](https://github.com/blink1073))
- Update Release Workflows [#129](https://github.com/jupyter-server/gateway_provisioners/pull/129) ([@blink1073](https://github.com/blink1073))
- Bump black\[jupyter\] from 23.9.1 to 23.11.0 [#119](https://github.com/jupyter-server/gateway_provisioners/pull/119) ([@dependabot](https://github.com/dependabot))
- Bump actions/checkout from 3 to 4 [#106](https://github.com/jupyter-server/gateway_provisioners/pull/106) ([@dependabot](https://github.com/dependabot))
- Bump black\[jupyter\] from 23.7.0 to 23.9.1 [#105](https://github.com/jupyter-server/gateway_provisioners/pull/105) ([@dependabot](https://github.com/dependabot))
- Adopt sp-repo-review [#104](https://github.com/jupyter-server/gateway_provisioners/pull/104) ([@blink1073](https://github.com/blink1073))
- Bump black\[jupyter\] from 23.3.0 to 23.7.0 [#99](https://github.com/jupyter-server/gateway_provisioners/pull/99) ([@dependabot](https://github.com/dependabot))
- Update mistune requirement from \<3.0.0 to \<4.0.0 [#94](https://github.com/jupyter-server/gateway_provisioners/pull/94) ([@dependabot](https://github.com/dependabot))
- Bump ruff from 0.0.269 to 0.0.270 [#92](https://github.com/jupyter-server/gateway_provisioners/pull/92) ([@dependabot](https://github.com/dependabot))
- Bump ruff from 0.0.267 to 0.0.269 [#91](https://github.com/jupyter-server/gateway_provisioners/pull/91) ([@dependabot](https://github.com/dependabot))
- Update docutils requirement from \<0.20 to \<0.21 [#90](https://github.com/jupyter-server/gateway_provisioners/pull/90) ([@dependabot](https://github.com/dependabot))
- Bump ruff from 0.0.265 to 0.0.267 [#89](https://github.com/jupyter-server/gateway_provisioners/pull/89) ([@dependabot](https://github.com/dependabot))
- Bump ruff from 0.0.263 to 0.0.265 [#88](https://github.com/jupyter-server/gateway_provisioners/pull/88) ([@dependabot](https://github.com/dependabot))
- Update RTD config [#87](https://github.com/jupyter-server/gateway_provisioners/pull/87) ([@blink1073](https://github.com/blink1073))
- Bump ruff from 0.0.262 to 0.0.263 [#83](https://github.com/jupyter-server/gateway_provisioners/pull/83) ([@dependabot](https://github.com/dependabot))
- Bump ruff from 0.0.261 to 0.0.262 [#82](https://github.com/jupyter-server/gateway_provisioners/pull/82) ([@dependabot](https://github.com/dependabot))

### Contributors to this release

([GitHub contributors page for this release](https://github.com/jupyter-server/gateway_provisioners/graphs/contributors?from=2023-04-20&to=2024-03-25&type=c))

[@BetterLevi](https://github.com/search?q=repo%3Ajupyter-server%2Fgateway_provisioners+involves%3ABetterLevi+updated%3A2023-04-20..2024-03-25&type=Issues) | [@blink1073](https://github.com/search?q=repo%3Ajupyter-server%2Fgateway_provisioners+involves%3Ablink1073+updated%3A2023-04-20..2024-03-25&type=Issues) | [@bsdz](https://github.com/search?q=repo%3Ajupyter-server%2Fgateway_provisioners+involves%3Absdz+updated%3A2023-04-20..2024-03-25&type=Issues) | [@dependabot](https://github.com/search?q=repo%3Ajupyter-server%2Fgateway_provisioners+involves%3Adependabot+updated%3A2023-04-20..2024-03-25&type=Issues) | [@kevin-bates](https://github.com/search?q=repo%3Ajupyter-server%2Fgateway_provisioners+involves%3Akevin-bates+updated%3A2023-04-20..2024-03-25&type=Issues) | [@mmmommm](https://github.com/search?q=repo%3Ajupyter-server%2Fgateway_provisioners+involves%3Ammmommm+updated%3A2023-04-20..2024-03-25&type=Issues) | [@pre-commit-ci](https://github.com/search?q=repo%3Ajupyter-server%2Fgateway_provisioners+involves%3Apre-commit-ci+updated%3A2023-04-20..2024-03-25&type=Issues) | [@welcome](https://github.com/search?q=repo%3Ajupyter-server%2Fgateway_provisioners+involves%3Awelcome+updated%3A2023-04-20..2024-03-25&type=Issues)

<!-- <END NEW CHANGELOG ENTRY> -->

## Gateway Provisioners 0.2.0

([Full Changelog](https://github.com/jupyter-server/gateway_provisioners/compare/v0.1.0...5dc7e2c85f98328bd4f1a960555fad81894eb78b))

### Enhancements made

- Port Custom Resource and Spark Operator provisioners from EG [#80](https://github.com/jupyter-server/gateway_provisioners/pull/80) ([@kevin-bates](https://github.com/kevin-bates))
- Add application support information for deploying JKG and Lab [#66](https://github.com/jupyter-server/gateway_provisioners/pull/66) ([@kevin-bates](https://github.com/kevin-bates))
- Add replace option to prevent accidental overwrite [#60](https://github.com/jupyter-server/gateway_provisioners/pull/60) ([@kevin-bates](https://github.com/kevin-bates))

### Bugs fixed

- Fix typos in App Support README [#71](https://github.com/jupyter-server/gateway_provisioners/pull/71) ([@kiersten-stokes](https://github.com/kiersten-stokes))
- Fix minor errors in Users subsection of documentation [#67](https://github.com/jupyter-server/gateway_provisioners/pull/67) ([@kiersten-stokes](https://github.com/kiersten-stokes))
- Fix default tooling [#49](https://github.com/jupyter-server/gateway_provisioners/pull/49) ([@kevin-bates](https://github.com/kevin-bates))

### Maintenance and upkeep improvements

- Bump ruff from 0.0.260 to 0.0.261 [#79](https://github.com/jupyter-server/gateway_provisioners/pull/79) ([@dependabot](https://github.com/dependabot))
- Bump ruff from 0.0.259 to 0.0.260 [#77](https://github.com/jupyter-server/gateway_provisioners/pull/77) ([@dependabot](https://github.com/dependabot))
- Bump black\[jupyter\] from 23.1.0 to 23.3.0 [#76](https://github.com/jupyter-server/gateway_provisioners/pull/76) ([@dependabot](https://github.com/dependabot))
- Bump ruff from 0.0.257 to 0.0.259 [#75](https://github.com/jupyter-server/gateway_provisioners/pull/75) ([@dependabot](https://github.com/dependabot))
- Bump ruff from 0.0.254 to 0.0.257 [#73](https://github.com/jupyter-server/gateway_provisioners/pull/73) ([@dependabot](https://github.com/dependabot))
- Bump ruff from 0.0.252 to 0.0.254 [#69](https://github.com/jupyter-server/gateway_provisioners/pull/69) ([@dependabot](https://github.com/dependabot))
- Fix relative link formatting in documentation to be consistent  [#68](https://github.com/jupyter-server/gateway_provisioners/pull/68) ([@kiersten-stokes](https://github.com/kiersten-stokes))
- Bump ruff from 0.0.249 to 0.0.252 [#65](https://github.com/jupyter-server/gateway_provisioners/pull/65) ([@dependabot](https://github.com/dependabot))
- Use releaser workflows [#64](https://github.com/jupyter-server/gateway_provisioners/pull/64) ([@blink1073](https://github.com/blink1073))
- Create hatch build env with make-related scripts [#63](https://github.com/jupyter-server/gateway_provisioners/pull/63) ([@kevin-bates](https://github.com/kevin-bates))
- Update mistune requirement from \<1.0.0 to \<3.0.0 [#61](https://github.com/jupyter-server/gateway_provisioners/pull/61) ([@dependabot](https://github.com/dependabot))
- Clean up lint and add check release [#48](https://github.com/jupyter-server/gateway_provisioners/pull/48) ([@blink1073](https://github.com/blink1073))

### Documentation improvements

- Add link to SparkOperatorProvisioner class definition [#81](https://github.com/jupyter-server/gateway_provisioners/pull/81) ([@kevin-bates](https://github.com/kevin-bates))
- Fix minor issues in Developer and Contributor docs [#74](https://github.com/jupyter-server/gateway_provisioners/pull/74) ([@kiersten-stokes](https://github.com/kiersten-stokes))
- Fix grammar NITs in Operator's Guide of docs [#72](https://github.com/jupyter-server/gateway_provisioners/pull/72) ([@kiersten-stokes](https://github.com/kiersten-stokes))
- Fix relative link formatting in documentation to be consistent  [#68](https://github.com/jupyter-server/gateway_provisioners/pull/68) ([@kiersten-stokes](https://github.com/kiersten-stokes))
- Fix minor errors in Users subsection of documentation [#67](https://github.com/jupyter-server/gateway_provisioners/pull/67) ([@kiersten-stokes](https://github.com/kiersten-stokes))
- Add application support information for deploying JKG and Lab [#66](https://github.com/jupyter-server/gateway_provisioners/pull/66) ([@kevin-bates](https://github.com/kevin-bates))
- Replace references to gateway-experiments with jupyter-server [#62](https://github.com/jupyter-server/gateway_provisioners/pull/62) ([@kevin-bates](https://github.com/kevin-bates))
- Cleanup Contributors Guide, remove Other section [#59](https://github.com/jupyter-server/gateway_provisioners/pull/59) ([@kevin-bates](https://github.com/kevin-bates))
- Cleanup Developers Guide [#58](https://github.com/jupyter-server/gateway_provisioners/pull/58) ([@kevin-bates](https://github.com/kevin-bates))
- Cleanup operators guide [#57](https://github.com/jupyter-server/gateway_provisioners/pull/57) ([@kevin-bates](https://github.com/kevin-bates))
- Cleanup users guide [#55](https://github.com/jupyter-server/gateway_provisioners/pull/55) ([@kevin-bates](https://github.com/kevin-bates))

### Contributors to this release

([GitHub contributors page for this release](https://github.com/jupyter-server/gateway_provisioners/graphs/contributors?from=2023-01-27&to=2023-04-20&type=c))

[@blink1073](https://github.com/search?q=repo%3Ajupyter-server%2Fgateway_provisioners+involves%3Ablink1073+updated%3A2023-01-27..2023-04-20&type=Issues) | [@dependabot](https://github.com/search?q=repo%3Ajupyter-server%2Fgateway_provisioners+involves%3Adependabot+updated%3A2023-01-27..2023-04-20&type=Issues) | [@echarles](https://github.com/search?q=repo%3Ajupyter-server%2Fgateway_provisioners+involves%3Aecharles+updated%3A2023-01-27..2023-04-20&type=Issues) | [@kevin-bates](https://github.com/search?q=repo%3Ajupyter-server%2Fgateway_provisioners+involves%3Akevin-bates+updated%3A2023-01-27..2023-04-20&type=Issues) | [@kiersten-stokes](https://github.com/search?q=repo%3Ajupyter-server%2Fgateway_provisioners+involves%3Akiersten-stokes+updated%3A2023-01-27..2023-04-20&type=Issues) | [@pre-commit-ci](https://github.com/search?q=repo%3Ajupyter-server%2Fgateway_provisioners+involves%3Apre-commit-ci+updated%3A2023-01-27..2023-04-20&type=Issues) | [@welcome](https://github.com/search?q=repo%3Ajupyter-server%2Fgateway_provisioners+involves%3Awelcome+updated%3A2023-01-27..2023-04-20&type=Issues)

## 0.1

Initial release
