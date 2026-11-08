#!/bin/sh
set -eu

SERVICE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SERVICE_DIR/../.." && pwd)
MAVEN_VERSION=3.9.9
MAVEN_SHA512=a555254d6b53d267965a3404ecb14e53c3827c09c3b94b5678835887ab404556bfaf78dcfe03ba76fa2508649dca8531c74bca4d5846513522404d48e8c4ac8b
CAPTCHA_TOOLS="$PROJECT_DIR/.local/captcha-tools"

if [ -z "${JAVA_HOME:-}" ]; then
  if [ -x "$CAPTCHA_TOOLS/jdk/bin/javac" ]; then
    JAVA_HOME="$CAPTCHA_TOOLS/jdk"
  elif [ -x /usr/libexec/java_home ]; then
    JAVA_HOME=$(/usr/libexec/java_home -v 21 2>/dev/null || /usr/libexec/java_home -v 17 2>/dev/null || true)
  fi
fi
if [ -n "${JAVA_HOME:-}" ]; then
  export JAVA_HOME
  PATH="$JAVA_HOME/bin:$PATH"
  export PATH
  CAPTCHA_JAVA="$JAVA_HOME/bin/java"
  CAPTCHA_JAVAC="$JAVA_HOME/bin/javac"
else
  CAPTCHA_JAVA=java
  CAPTCHA_JAVAC=javac
fi
if ! "$CAPTCHA_JAVA" -version >/dev/null 2>&1 || ! CAPTCHA_JAVAC_VERSION=$("$CAPTCHA_JAVAC" -version 2>&1); then
  printf '%s\n' 'CAPTCHA_JDK_ERROR: 本机缺少可用的 JDK 17 或以上版本（需要 java 和 javac）；请设置 JAVA_HOME 或安装到 .local/captcha-tools/jdk。' >&2
  exit 2
fi
CAPTCHA_JAVA_MAJOR=$(printf '%s\n' "$CAPTCHA_JAVAC_VERSION" | awk '/^javac / {split($2, version, "."); print version[1]}')
case "$CAPTCHA_JAVA_MAJOR" in
  ''|*[!0-9]*) CAPTCHA_JAVA_MAJOR=0 ;;
esac
if [ "$CAPTCHA_JAVA_MAJOR" -lt 17 ]; then
  printf '%s\n' 'CAPTCHA_JDK_ERROR: 验证码构建需要 JDK 17 或以上版本，当前 javac 版本过低。' >&2
  exit 2
fi
printf 'JDK: %s\n' "$CAPTCHA_JAVAC_VERSION"
if [ "${1:-}" = '--check' ]; then exit 0; fi

if [ -n "${MAVEN_BIN:-}" ]; then
  CAPTCHA_MAVEN=$MAVEN_BIN
elif command -v mvn >/dev/null 2>&1; then
  CAPTCHA_MAVEN=$(command -v mvn)
else
  CAPTCHA_MAVEN="$CAPTCHA_TOOLS/apache-maven-$MAVEN_VERSION/bin/mvn"
  if [ ! -x "$CAPTCHA_MAVEN" ]; then
    mkdir -p "$CAPTCHA_TOOLS"
    CAPTCHA_ARCHIVE="$CAPTCHA_TOOLS/apache-maven-$MAVEN_VERSION-bin.tar.gz"
    curl --fail --location --retry 2 --proto '=https' --tlsv1.2 \
      "https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/$MAVEN_VERSION/apache-maven-$MAVEN_VERSION-bin.tar.gz" \
      --output "$CAPTCHA_ARCHIVE"
    if command -v shasum >/dev/null 2>&1; then
      CAPTCHA_ACTUAL=$(shasum -a 512 "$CAPTCHA_ARCHIVE" | awk '{print $1}')
    else
      CAPTCHA_ACTUAL=$(sha512sum "$CAPTCHA_ARCHIVE" | awk '{print $1}')
    fi
    if [ "$CAPTCHA_ACTUAL" != "$MAVEN_SHA512" ]; then
      printf '%s\n' 'Maven archive checksum mismatch' >&2
      exit 1
    fi
    tar -xzf "$CAPTCHA_ARCHIVE" -C "$CAPTCHA_TOOLS"
  fi
fi

printf 'Maven: %s\n' "$CAPTCHA_MAVEN"
"$CAPTCHA_MAVEN" --batch-mode --no-transfer-progress -f "$SERVICE_DIR/pom.xml" clean verify
printf 'Artifact: %s/target/shiyue-captcha-1.0.0.jar\n' "$SERVICE_DIR"
