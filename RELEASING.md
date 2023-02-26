# Making a Gateway Provisioners Release

## Using `jupyter_releaser`

The recommended way to make a release is to use [`jupyter_releaser`](https://jupyter-releaser.readthedocs.io/en/latest/get_started/making_release_from_repo.html).

## Manual Release

To create a manual release, perform the following steps:

### Set up

```bash
pip install hatch twine build
git pull origin $(git branch --show-current)
git clean -dffx
```

### Update the version and apply the tag

```bash
echo "Enter new version"
read new_version
hatch version ${new_version}
git commit -a -m "Release ${new_version}"
git tag -a ${new_version} -m "Release ${new_version}"
```

If building the changelog notes via the releases page (prior to jupyter-releaser) you'll want to push
the tags so the changelog generator can know what to reference, otherwise this can be skipped.

```bash
git push origin
git push --tags origin
```

```bash
make clean dist
```

### Run tests

```bash
make test
```

### Update the version back to dev

```bash
echo "Enter dev version"
read dev_version
hatch version ${dev_version}
git commit -a -m "Back to dev"
git push origin $(git branch --show-current)
```

If tags were not pushed previously (to build changelog) push now.

```bash
git push --tags origin
```

### Publish the artifacts to pypi

```bash
twine check dist/*
twine upload dist/*
```
