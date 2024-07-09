import os
from pathlib import Path
from unittest.mock import ANY

from openai.types import FileObject

from test.abstract_integration_test import AbstractIntegrationTest


class TestVectorStores(AbstractIntegrationTest):
    class TestPipeline:
        def add_vector_store_file(self, file: FileObject, filename: str, file_content: bytes) -> tuple[int, int]:
            return 564515, 329951

        def remove_vector_store_file(self, file_id: str) -> int:
            return 234564

    def mock_pipeline(self):
        # create mock pipeline
        vector_store_mount = next(x for x in self.fast_api_client.app.routes if x.path == "/v1/vector_stores"
                                  and x.__class__.__name__ == "Mount")
        vector_store_mount.app.state._state["PIPELINE_MODULES"] = {
            "openai_vector_store_pipeline": self.TestPipeline()}
        vector_store_mount.app.state._state["PIPELINES"] = {"openai_vector_store_pipeline": ""}

    def test_create_vector_store__with_files(self):
        self.mock_pipeline()
        file_dict = self.create_upload_file("data/test.json")
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
        response = self.fast_api_client.post("/v1/vector_stores",
                                             json=body,
                                             headers={"Authorization": f"Bearer test-key"})

        assert response.status_code == 200
        assert response.json() == {
            'created_at': ANY,
            'expires_after': {'anchor': 'last_active_at', 'days': 4},
            'expires_at': None,
            'file_counts': {'cancelled': 0,
                            'completed': 0,
                            'failed': 0,
                            'in_progress': 1,
                            'total': 1},
            'id': ANY,
            'last_active_at': ANY,
            'metadata': {'application': 'open-web-ui', 'pipeline_id': 'openai_vector_store_pipeline'},
            'name': 'my-vector-store',
            'object': 'vector_store',
            'status': 'completed',
            'usage_bytes': 0
        }

    def test_create_vector_store__no_files(self):
        self.mock_pipeline()

        body = {
            "name": "my-vector-store-without-files",
            "metadata": {"application": "open-web-ui"},
            "expires_after": {"anchor": "last_active_at", "days": "4"}
        }
        response = self.fast_api_client.post("/v1/vector_stores",
                                             json=body,
                                             headers={"Authorization": f"Bearer test-key"})

        assert response.status_code == 200
        assert response.json() == {
            'created_at': ANY,
            'expires_after': {'anchor': 'last_active_at', 'days': 4},
            'expires_at': None,
            'file_counts': {'cancelled': 0,
                            'completed': 0,
                            'failed': 0,
                            'in_progress': 0,
                            'total': 0},
            'id': ANY,
            'last_active_at': ANY,
            'metadata': {'application': 'open-web-ui'},
            'name': 'my-vector-store-without-files',
            'object': 'vector_store',
            'status': 'completed',
            'usage_bytes': 0
        }

    def test_create_vector_store_file(self):
        existing_vector_store_id = self.get_vector_store_id_with_files()
        existing_file_id = self.get_existing_file_id()
        body = {
            "file_id": existing_file_id,
            "chunking_strategy": {
                "type": "static",
                "static": {
                    "max_chunk_size_tokens": 100,
                    "chunk_overlap_tokens": 20
                }
            }
        }
        response = self.fast_api_client.post(f"/v1/vector_stores/{existing_vector_store_id}/files",
                                             json=body,
                                             headers={"Authorization": f"Bearer test-key"})
        assert response.status_code == 200
        assert response.json() == {
            "id": ANY,
            "created_at": ANY,
            "last_error": None,
            "object": "vector_store.file",
            "status": "in_progress",
            "usage_bytes": 0,
            "vector_store_id": existing_vector_store_id,
            "chunking_strategy": {
                "static": {"chunk_overlap_tokens": 20, "max_chunk_size_tokens": 100},
                "type": "static"}
        }

    def test_list_vector_store_files(self):
        existing_vector_store_id = self.get_vector_store_id_with_files()
        response = self.fast_api_client.get(f"/v1/vector_stores/{existing_vector_store_id}/files",
                                            headers={"Authorization": f"Bearer test-key"})
        assert response.status_code == 200
        assert response.json() == {
            'data': [{'chunking_strategy': {'static': {'chunk_overlap_tokens': 400,
                                                       'max_chunk_size_tokens': 800},
                                            'type': 'static'},
                      'created_at': ANY,
                      'id': ANY,
                      'last_error': None,
                      'object': 'vector_store.file',
                      'status': 'completed',
                      'usage_bytes': 329951,
                      'vector_store_id': existing_vector_store_id},
                     {'chunking_strategy': {'static': {'chunk_overlap_tokens': 20,
                                                       'max_chunk_size_tokens': 100},
                                            'type': 'static'},
                      'created_at': ANY,
                      'id': ANY,
                      'last_error': None,
                      'object': 'vector_store.file',
                      'status': 'completed',
                      'usage_bytes': 329951,
                      'vector_store_id': existing_vector_store_id}],
            'first_id': response.json()["data"][0]["id"],
            'has_more': False,
            'last_id': response.json()["data"][-1]["id"],
            'object': 'list'}

    def test_delete_vector_store_file(self):
        existing_vector_store_id = self.get_vector_store_id_with_files()
        existing_vector_store_file_id = self.get_existing_vector_store_file_id(existing_vector_store_id)

        response = self.fast_api_client.delete(
            f"/v1/vector_stores/{existing_vector_store_id}/files/{existing_vector_store_file_id}",
            headers={"Authorization": f"Bearer test-key"})

        assert response.status_code == 200
        assert response.json() == {
            "deleted": True,
            "id": ANY,
            "object": "vector_store.file.deleted"
        }

    def test_retrieve_vector_store_file(self):
        existing_vector_store_id = self.get_vector_store_id_with_files()
        existing_vector_store_file_id = self.get_existing_vector_store_file_id(existing_vector_store_id)

        response = self.fast_api_client.get(
            f"/v1/vector_stores/{existing_vector_store_id}/files/{existing_vector_store_file_id}",
            headers={"Authorization": f"Bearer test-key"})

        assert response.status_code == 200
        assert response.json() == {'chunking_strategy': {'static':
                                                             {'chunk_overlap_tokens': 20,
                                                              'max_chunk_size_tokens': 100},
                                                         'type': 'static'
                                                         },
                                   'created_at': ANY,
                                   'id': existing_vector_store_file_id,
                                   'last_error': None,
                                   'object': 'vector_store.file',
                                   'status': 'completed',
                                   'usage_bytes': 329951,
                                   'vector_store_id': existing_vector_store_id
                                   }

    def test_list_vector_stores(self):
        response = self.fast_api_client.get("/v1/vector_stores?order=desc",
                                            headers={"Authorization": f"Bearer test-key"})

        assert response.status_code == 200
        response = response.json()
        response["data"] = sorted(response["data"], key=lambda d: d['name'], reverse=False)
        assert response == {
            'data': [{'created_at': ANY,
                      'expires_after': {'anchor': 'last_active_at', 'days': 4},
                      'expires_at': None,
                      'file_counts': {'cancelled': 0,
                                      'completed': 1,
                                      'failed': 0,
                                      'in_progress': 0,
                                      'total': 1},
                      'id': ANY,
                      'last_active_at': ANY,
                      'metadata': {'application': 'open-web-ui', 'pipeline_id': 'openai_vector_store_pipeline'},
                      'name': 'my-vector-store',
                      'object': 'vector_store',
                      'status': 'completed',
                      'usage_bytes': 234564},
                     {'created_at': ANY,
                      'expires_after': {'anchor': 'last_active_at', 'days': 4},
                      'expires_at': None,
                      'file_counts': {'cancelled': 0,
                                      'completed': 0,
                                      'failed': 0,
                                      'in_progress': 0,
                                      'total': 0},
                      'id': ANY,
                      'last_active_at': ANY,
                      'metadata': {'application': 'open-web-ui'},
                      'name': 'my-vector-store-without-files',
                      'object': 'vector_store',
                      'status': 'completed',
                      'usage_bytes': 0}],
            'first_id': ANY,
            'has_more': False,
            'last_id': ANY,
            'object': 'list'}

    def test_delete_vector_store(self):
        existing_vector_store_id = self.get_vector_store_id_without_files()
        response = self.fast_api_client.delete(f"/v1/vector_stores/{existing_vector_store_id}",
                                               headers={"Authorization": f"Bearer test-key"})

        assert response.status_code == 200
        assert response.json() == {
            "id": existing_vector_store_id,
            "object": "vector_store.deleted",
            "deleted": True
        }
        response = self.fast_api_client.get("/v1/vector_stores", headers={"Authorization": f"Bearer test-key"})
        assert len(response.json()["data"]) == 1

    def test_retrieve_vector_store(self):
        existing_vector_store_id = self.get_vector_store_id_with_files()

        response = self.fast_api_client.get(f"/v1/vector_stores/{existing_vector_store_id}",
                                            headers={"Authorization": f"Bearer test-key"})

        assert response.status_code == 200
        assert response.json() == {
            'created_at': ANY,
            'expires_after': {'anchor': 'last_active_at', 'days': 4},
            'expires_at': None,
            'file_counts': {'cancelled': 0,
                            'completed': 1,
                            'failed': 0,
                            'in_progress': 0,
                            'total': 1},
            'id': existing_vector_store_id,
            'last_active_at': ANY,
            'metadata': {'application': 'open-web-ui', 'pipeline_id': 'openai_vector_store_pipeline'},
            'name': 'my-vector-store',
            'object': 'vector_store',
            'status': 'completed',
            'usage_bytes': 234564
        }

    def test_modify_vector_store(self):
        existing_vector_store_id = self.get_vector_store_id_with_files()

        body = {
            "name": "modified-name",
            "metadata": {"modified-meta-key": "modified-meta-value"},
        }

        response = self.fast_api_client.post(f"/v1/vector_stores/{existing_vector_store_id}",
                                             headers={"Authorization": f"Bearer test-key"},
                                             json=body,
                                             )

        assert response.status_code == 200
        assert response.json() == {
            'created_at': ANY,
            'expires_after': {'anchor': 'last_active_at', 'days': 4},
            'expires_at': None,
            'file_counts': {'cancelled': 0,
                            'completed': 1,
                            'failed': 0,
                            'in_progress': 0,
                            'total': 1},
            'id': existing_vector_store_id,
            'last_active_at': ANY,
            'metadata': {'modified-meta-key': 'modified-meta-value'},
            'name': 'modified-name',
            'object': 'vector_store',
            'status': 'completed',
            'usage_bytes': 234564
        }

    def create_upload_file(self, filename: str) -> dict:
        dir_path = os.path.dirname(os.path.realpath(__file__))
        test_json = os.path.join(dir_path, filename)
        test_upload_file = Path(test_json)
        return {'file': test_upload_file.open('rb')}

    def get_vector_store_id_with_files(self):
        response = self.fast_api_client.get("/v1/vector_stores", headers={"Authorization": f"Bearer test-key"})
        return next(x["id"] for x in response.json()["data"] if x["file_counts"]["total"] > 0)

    def get_vector_store_id_without_files(self):
        response = self.fast_api_client.get("/v1/vector_stores", headers={"Authorization": f"Bearer test-key"})
        return next(x["id"] for x in response.json()["data"] if x["file_counts"]["total"] == 0)

    def get_existing_file_id(self):
        response = self.fast_api_client.get("/v1/files", headers={"Authorization": f"Bearer test-key"})
        return response.json()["data"][0]["id"]

    def get_existing_vector_store_file_id(self, existing_vector_store_id: str):
        response = self.fast_api_client.get(f"/v1/vector_stores/{existing_vector_store_id}/files",
                                            headers={"Authorization": f"Bearer test-key"})
        return response.json()["data"][0]["id"]
