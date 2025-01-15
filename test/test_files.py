import os
from pathlib import Path
from unittest.mock import ANY

from test.abstract_integration_test import AbstractIntegrationTest


class TestFiles(AbstractIntegrationTest):

    def test_upload_file(self):
        file_dicts = self.create_upload_files(["data/test.json"])
        response = self.fast_api_client.post("/v1/files",
                                             data={"purpose": "fine-tune"},
                                             files=file_dicts[0],
                                             headers={"Authorization": f"Bearer test-key"})

        assert response.status_code == 200
        assert response.json() == {
            'bytes': 20,
            'created_at': ANY,
            'filename': 'test.json',
            'id': ANY,
            'object': 'file',
            'purpose': 'fine-tune',
            'status': 'uploaded',
            'status_details': None
        }

    def test_list_files(self):
        file_dicts = self.create_upload_files(["data/test2.json"])
        self.fast_api_client.post("/v1/files",
                                  data={"purpose": "fine-tune"},
                                  files=file_dicts[0],
                                  headers={"Authorization": f"Bearer test-key"})
        response = self.fast_api_client.get("/v1/files", headers={"Authorization": f"Bearer test-key"})

        assert response.status_code == 200
        assert response.json() == {
            'data': [{'bytes': 20,
                      'created_at': ANY,
                      'filename': 'test.json',
                      'id': ANY,
                      'object': 'file',
                      'purpose': 'fine-tune',
                      'status': 'uploaded',
                      'status_details': None},
                     {'bytes': 20,
                      'created_at': ANY,
                      'filename': 'test2.json',
                      'id': ANY,
                      'object': 'file',
                      'purpose': 'fine-tune',
                      'status': 'uploaded',
                      'status_details': None
                      }]
        }

    def test_delete_file(self):
        response = self.fast_api_client.get("/v1/files", headers={"Authorization": f"Bearer test-key"})
        file_id = response.json()["data"][0]["id"]
        response = self.fast_api_client.delete(f"/v1/files/{file_id}", headers={"Authorization": f"Bearer test-key"})

        assert response.status_code == 200
        assert response.json() == {
            "id": file_id,
            "object": "file",
            "deleted": True
        }
        response = self.fast_api_client.get("/v1/files", headers={"Authorization": f"Bearer test-key"})
        assert len(response.json()["data"]) == 1

    def test_delete_file__file_does_not_exist(self):
        response = self.fast_api_client.delete(f"/v1/files/unknown-id", headers={"Authorization": f"Bearer test-key"})

        assert response.status_code == 200
        assert response.json() == {
            "id": "unknown-id",
            "object": "file",
            "deleted": False
        }
        response = self.fast_api_client.get("/v1/files", headers={"Authorization": f"Bearer test-key"})
        assert len(response.json()["data"]) == 1

    def test_retrieve_file(self):
        response = self.fast_api_client.get("/v1/files", headers={"Authorization": f"Bearer test-key"})
        existing_file_id = response.json()["data"][0]["id"]

        response = self.fast_api_client.get(f"/v1/files/{existing_file_id}",
                                            headers={"Authorization": f"Bearer test-key"})

        assert response.status_code == 200
        assert response.json() == {'bytes': 20,
                                   'created_at': ANY,
                                   'filename': 'test2.json',
                                   'id': existing_file_id,
                                   'object': 'file',
                                   'purpose': 'fine-tune',
                                   'status': 'uploaded',
                                   'status_details': None}

    def test_get_file_content(self):
        response = self.fast_api_client.get("/v1/files", headers={"Authorization": f"Bearer test-key"})
        existing_file_id = response.json()["data"][0]["id"]

        response = self.fast_api_client.get(f"/v1/files/{existing_file_id}/content",
                                            headers={"Authorization": f"Bearer test-key"})

        assert response.status_code == 200
        assert response.json() == '{\n  "test": "test"\n}'

    def create_upload_files(self, filenames: list[str]) -> list[dict]:
        files = []
        for filename in filenames:
            dir_path = os.path.dirname(os.path.realpath(__file__))
            test_json = os.path.join(dir_path, filename)
            test_upload_file = Path(test_json)
            files_dict = {'file': test_upload_file.open('rb')}
            files.append(files_dict)
        return files
