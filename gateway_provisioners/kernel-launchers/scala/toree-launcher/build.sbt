/*
 * Copyright (c) Jupyter Development Team.
 * Distributed under the terms of the Modified BSD License.
 */

name := "toree-launcher"

version := sys.props.getOrElse("version", default = "1.0").replaceAll("dev[0-9]", "SNAPSHOT")

// Match the Scala 2.12 patch release that the image's Spark (3.4.x) is built with.
// Toree 0.5.0-incubating is built for Scala 2.12, so stay on 2.12.x.
scalaVersion := "2.12.17"

resolvers += "Typesafe Repo" at "https://repo.typesafe.com/typesafe/releases/"
/* resolvers += "Sonatype Repository" at "https://oss.sonatype.org/content/repositories/releases/" */
resolvers += "Sonatype Maven Central Mirror" at "https://maven-central.storage-download.googleapis.com/maven2/"

libraryDependencies += "com.typesafe.play" %% "play-json" % "2.7.4" // Apache v2
libraryDependencies += "org.apache.toree" % "toree-assembly" % "0.5.0-incubating" // Apache v2
