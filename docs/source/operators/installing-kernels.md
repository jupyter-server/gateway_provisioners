# Installing Supported Kernels (Servers)

Gateway Provisioners includes tooling to create kernel specifications that support the following kernels:

- IPython kernel (Python)
- Apache Toree (Scala)
- IRKernel (R)

Refer to the following for instructions on installing the respective kernels. For cluster-based environments, these
steps should be performed on each applicable node of the cluster, unless noted otherwise.

```{admonition} Important!
:class: warning
For proper operation across the _non-containerized clusters_, the IPyKernel and IRkernel packages (not the
kernel specification) must be installed on every node of the cluster available to Gateway Provisioners.
For example, run `pip install ipykernel` on each applicable node.

Note: This step is **not** required for the Scala (Apache Toree) Kernel as that can be expressed as a
dependency in the `spark-submit` invocation where the package is copied during launch.
```

## Python Kernel (IPython kernel)

The IPython kernel comes pre-installed with Anaconda, and we have tested with its default version
of [IPython kernel](https://ipython.readthedocs.io/en/stable/).

```bash
pip install --upgrade ipykernel
```

or

```bash
mamba install -c conda-forge ipykernel
```

## Scala Kernel (Apache Toree)

We have tested the latest version of [Apache Toree](https://toree.apache.org/) with Scala 2.12 support.

```bash
pip install --upgrade apache_toree
```

or

```bash
mamba install -c conda-forge apache_toree
```

## R Kernel (IRkernel)

Perform the following steps on Gateway Provisioner's hosting system as well as all worker nodes. Please
refer to the [IRKernel documentation](https://irkernel.github.io/) for further details.

```bash
mamba install --yes --quiet -c r r-essentials r-irkernel r-argparse
# Create an R-script to run and install packages and update IRkernel
cat <<'EOF' > install_packages.R
install.packages(c('repr', 'IRdisplay', 'evaluate', 'git2r', 'crayon', 'pbdZMQ',
                   'devtools', 'uuid', 'digest', 'RCurl', 'curl', 'argparse'),
                   repos='http://cran.rstudio.com/')
devtools::install_github('IRkernel/IRkernel@0.8.14')
IRkernel::installspec(user = FALSE)
EOF
# run the package install script
$ANACONDA_HOME/bin/Rscript install_packages.R
# OPTIONAL: check the installed R packages
ls $ANACONDA_HOME/lib/R/library
```
