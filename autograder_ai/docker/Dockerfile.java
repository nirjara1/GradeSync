FROM eclipse-temurin:17-jdk-jammy

WORKDIR /app

# Student code will be mounted here
RUN mkdir -p /submission
WORKDIR /submission
