import logging
import os
import time

import docker
import pytest
import requests
from docker import DockerClient
from fastapi.testclient import TestClient
from peewee import PostgresqlDatabase
from pytest_docker.plugin import get_docker_ip

log = logging.getLogger(__name__)

POSTGRES_CONTAINER_NAME = "postgres-test-container-will-get-deleted"


class AbstractIntegrationTest:
    docker_client: DockerClient
    documents = None

    @classmethod
    def setup_class(cls):
        try:
            env_vars_postgres = {
                "POSTGRES_USER": "user",
                "POSTGRES_PASSWORD": "example",
                "POSTGRES_DB": "pipelines",
            }
            cls.docker_client = docker.from_env()

            cls.docker_client.containers.run(
                "postgres:16.3",
                detach=True,
                environment=env_vars_postgres,
                name=POSTGRES_CONTAINER_NAME,
                ports={5432: ("0.0.0.0", 8048)},
            )

            time.sleep(2)

            docker_ip = get_docker_ip()

            os.environ["DATABASE_URL"] = "postgresql://user:example@localhost:8048/pipelines"
            os.environ["PIPELINES_API_KEY"] = "test-key"
            retries = 10
            while retries > 0:
                try:
                    db = PostgresqlDatabase(
                        database="pipelines",
                        user="user",
                        password="example",
                        host=docker_ip,
                        port="8048")
                    db.connect()
                    log.info("postgres is ready!")
                    break
                except Exception as e:
                    log.warning(e)
                    time.sleep(1)
                    retries -= 1
            # import must be after setting env!
            from main import app
            cls.fast_api_client = cls.get_fast_api_client(app)
            db.close()
        except Exception as ex:
            log.error(ex)
            cls.teardown_class()
            pytest.fail(f"Could not setup test environment: {ex}")

    @classmethod
    def get_fast_api_client(cls, app):
        with TestClient(app) as c:
            return c

    @classmethod
    def teardown_class(cls) -> None:
        cls.docker_client.containers.get(POSTGRES_CONTAINER_NAME).remove(force=True)
