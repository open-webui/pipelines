import os
from pathlib import Path

from test.abstract_integration_test import AbstractIntegrationTest


class TestPagination(AbstractIntegrationTest):

    def test_paginate_vector_stores(self):
        file_dict = self.create_upload_file("data/test.json")
        for i in range(10):
            response = self.fast_api_client.post("/v1/files",
                                                 data={"purpose": "fine-tune"},
                                                 files=file_dict,
                                                 headers={"Authorization": f"Bearer test-key"})
            body = {
                "file_ids": [response.json()["id"]],
                "name": "my-vector-store",
                "metadata": {"application": "open-web-ui", "pipeline_id": "openai_vector_store_pipeline"},
                "expires_after": {"anchor": "last_active_at", "days": "4"}
            }
            self.fast_api_client.post("/v1/vector_stores",
                                      json=body,
                                      headers={"Authorization": f"Bearer test-key"})

        response = self.fast_api_client.get("/v1/vector_stores",
                                            headers={"Authorization": f"Bearer test-key"})
        data = response.json()["data"]
        assert len(data) == 10
        after = data[2]["id"]
        before = data[7]["id"]
        response = self.fast_api_client.get(f"/v1/vector_stores?after={after}&before={before}",
                                            headers={"Authorization": f"Bearer test-key"})
        data = response.json()["data"]
        assert len(data) == 4
        assert response.json()["has_more"] is False

        response = self.fast_api_client.get(f"/v1/vector_stores?after={after}&limit=2",
                                            headers={"Authorization": f"Bearer test-key"})
        data = response.json()["data"]
        assert len(data) == 2
        assert response.json()["has_more"] is True
        response = self.fast_api_client.get(f"/v1/vector_stores?limit=0",
                                            headers={"Authorization": f"Bearer test-key"})
        assert response.json() == {
            'data': [],
            'first_id': None,
            'has_more': False,
            'last_id': None,
            'object': 'list'
        }

    def test_paginate_vector_store_files(self):
        existing_vector_store_id = self.get_existing_vector_store_id()
        response = self.fast_api_client.get(f"/v1/vector_stores/{existing_vector_store_id}/files",
                                            headers={"Authorization": f"Bearer test-key"})
        data = response.json()["data"]
        assert len(data) == 10
        after = data[2]["id"]
        before = data[7]["id"]
        response = self.fast_api_client.get(
            f"/v1/vector_stores/{existing_vector_store_id}/files?after={after}&before={before}",
            headers={"Authorization": f"Bearer test-key"})
        data = response.json()["data"]
        assert len(data) == 4
        assert response.json()["has_more"] is False

        response = self.fast_api_client.get(f"/v1/vector_stores/{existing_vector_store_id}/files?after={after}&limit=2",
                                            headers={"Authorization": f"Bearer test-key"})
        data = response.json()["data"]
        assert len(data) == 2
        assert response.json()["has_more"] is True

        response = self.fast_api_client.get(f"/v1/vector_stores/{existing_vector_store_id}/files?limit=0",
                                            headers={"Authorization": f"Bearer test-key"})
        assert response.json() == {
            'data': [],
            'first_id': None,
            'has_more': False,
            'last_id': None,
            'object': 'list'
        }

    def create_upload_file(self, filename: str) -> dict:
        dir_path = os.path.dirname(os.path.realpath(__file__))
        test_json = os.path.join(dir_path, filename)
        test_upload_file = Path(test_json)
        return {'file': test_upload_file.open('rb')}

    def get_existing_vector_store_id(self):
        response = self.fast_api_client.get("/v1/vector_stores", headers={"Authorization": f"Bearer test-key"})
        return response.json()["data"][0]["id"]

    def get_existing_vector_store_file_id(self, existing_vector_store_id: str):
        response = self.fast_api_client.get(f"/v1/vector_stores/{existing_vector_store_id}/files",
                                            headers={"Authorization": f"Bearer test-key"})
        return response.json()["data"][0]["id"]
