import os
import paramiko
import rpc
import requests
import psycopg2
import ftputil
import pysftp
import psutil
import pika
import ansible
import cryptography
from cryptography.fernet import Fernet
import logstash
import prometheus_client

from blueprints.function_calling_blueprint import Pipeline as FunctionCallingBlueprint


class Pipeline(FunctionCallingBlueprint):
    class Valves(FunctionCallingBlueprint.Valves):
        # Add your custom parameters here
        SSH_HOSTNAME: str = ""
        SSH_USERNAME: str = ""
        SSH_PASSWORD: str = ""
        RPC_HOSTNAME: str = ""
        RPC_PORT: int = 8080
        WEB_API_URL: str = ""
        DATABASE_HOSTNAME: str = ""
        DATABASE_USERNAME: str = ""
        DATABASE_PASSWORD: str = ""
        DATABASE_NAME: str = ""
        FTP_HOSTNAME: str = ""
        FTP_USERNAME: str = ""
        FTP_PASSWORD: str = ""
        SFTP_HOSTNAME: str = ""
        SFTP_USERNAME: str = ""
        SFTP_PASSWORD: str = ""
        MESSAGE_QUEUE_HOSTNAME: str = ""
        MESSAGE_QUEUE_PORT: int = 5672
        ANSIBLE_PLAYBOOK: str = ""
        CRYPTOGRAPHY_KEY: str = ""
        LOGSTASH_HOSTNAME: str = ""
        LOGSTASH_PORT: int = 5000
        PROMETHEUS_HOSTNAME: str = ""
        PROMETHEUS_PORT: int = 8000

    class Tools:
        def __init__(self, pipeline) -> None:
            self.pipeline = pipeline

        def ssh(self, command: str) -> str:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.pipeline.valves.SSH_HOSTNAME, username=self.pipeline.valves.SSH_USERNAME, password=self.pipeline.valves.SSH_PASSWORD)
            stdin, stdout, stderr = ssh.exec_command(command)
            return stdout.read().decode()

        def rpc(self, function_name: str, *args, **kwargs) -> any:
            rpc_client = rpc.RPCClient(self.pipeline.valves.RPC_HOSTNAME, self.pipeline.valves.RPC_PORT)
            return getattr(rpc_client, function_name)(*args, **kwargs)

        def web_api(self, endpoint: str, method: str = "GET", data: dict = {}) -> any:
            response = requests.request(method, self.pipeline.valves.WEB_API_URL + endpoint, json=data)
            return response.json()

        def database(self, query: str) -> list:
            conn = psycopg2.connect(
                host=self.pipeline.valves.DATABASE_HOSTNAME,
                database=self.pipeline.valves.DATABASE_NAME,
                user=self.pipeline.valves.DATABASE_USERNAME,
                password=self.pipeline.valves.DATABASE_PASSWORD
            )
            cur = conn.cursor()
            cur.execute(query)
            return cur.fetchall()

        def ftp(self, local_file: str, remote_file: str) -> None:
            ftp = ftputil.FTPHost(self.pipeline.valves.FTP_HOSTNAME, self.pipeline.valves.FTP_USERNAME, self.pipeline.valves.FTP_PASSWORD)
            ftp.upload(local_file, remote_file)

        def sftp(self, local_file: str, remote_file: str) -> None:
            sftp = pysftp.Connection(self.pipeline.valves.SFTP_HOSTNAME, username=self.pipeline.valves.SFTP_USERNAME, password=self.pipeline.valves.SFTP_PASSWORD)
            sftp.put(local_file, remote_file)

        def message_queue(self, message: str) -> None:
            connection = pika.BlockingConnection(pika.ConnectionParameters(self.pipeline.valves.MESSAGE_QUEUE_HOSTNAME))
            channel = connection.channel()
            channel.queue_declare(queue='my_queue')
            channel.basic_publish(exchange='', routing_key='my_queue', body=message)

        def ansible(self, playbook: str) -> None:
            ansible.playbook.PlayBook().run(playbook=playbook)

        def cryptography(self, message: str) -> str:
            cipher_suite = Fernet(self.pipeline.valves.CRYPTOGRAPHY_KEY)
            encrypted_message = cipher_suite.encrypt(message.encode())
            return encrypted_message.decode()

        def logstash(self, message: str) -> None:
            logger = logstash.TCPLogstashHandler(self.pipeline.valves.LOGSTASH_HOSTNAME, self.pipeline.valves.LOGSTASH_PORT)
            logger.info(message)

        def prometheus(self) -> None:
            prometheus_client.start_http_server(self.pipeline.valves.PROMETHEUS_HOSTNAME, self.pipeline.valves.PROMETHEUS_PORT)

    def __init__(self):
        super().__init__()
        self.valves = self.Valves(
            **{
                **self.valves.model_dump(),
                "pipelines": ["*"],  # Connect to all pipelines
            },
        )
        self.tools = self.Tools(self)