FROM eclipse-temurin:21-jre-jammy
WORKDIR /app
RUN groupadd --gid 10001 captcha && useradd --uid 10001 --gid captcha --no-create-home captcha
COPY --chown=captcha:captcha target/shiyue-captcha-1.0.0.jar /app/captcha.jar
USER captcha
ENV JAVA_TOOL_OPTIONS="-Xms32m -Xmx192m -XX:MaxMetaspaceSize=128m -XX:ReservedCodeCacheSize=32m -XX:ActiveProcessorCount=2 -Djava.awt.headless=true"
ENTRYPOINT ["java", "-jar", "/app/captcha.jar"]
