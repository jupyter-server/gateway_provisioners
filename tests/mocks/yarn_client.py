# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from time import time_ns
from typing import Optional


class YarnResource:
    """Track the current state of the resource"""

    initial_states = {"NEW", "SUBMITTED", "ACCEPTED", "RUNNING"}
    final_states = {"FINISHED", "KILLED", "FAILED"}

    def __init__(self, env: dict):
        self.env = env
        self.kernel_id: str = env.get("KERNEL_ID")
        self.kernel_username: str = env.get("KERNEL_USERNAME")
        self.name = self.kernel_id
        self.id = f"application_{str(time_ns())}_0001"
        self.status: str = "NEW"
        self.query_counter: int = 1


yarn_resources: dict = {}


class MockResponse:
    def __init__(
        self, apps: Optional[dict] = None, app: Optional[dict] = None, status: Optional[str] = None
    ):
        self.data = {}
        if apps:
            self.data["apps"] = apps
        elif app:
            self.data["app"] = app
        elif status:
            self.data["status"] = status


class MockResourceManager:  # (ResourceManager):
    def __init__(self, **kwargs):
        pass

    def get_active_endpoint(self):
        pass

    def cluster_applications(
        self,
        state=None,
        states=None,
        final_status=None,
        user=None,
        queue=None,
        limit=None,
        started_time_begin=None,
        started_time_end=None,
        finished_time_begin=None,
        finished_time_end=None,
        application_types=None,
        application_tags=None,
        name=None,
        de_selects=None,
    ):
        """This method is used to determine when the application ID has been created"""
        apps = {"app": []}
        app_list = apps.get("app")
        for kid, resource in yarn_resources.items():
            # convert each resource into an app list entry
            id = ""
            if resource.query_counter >= 3:
                id = resource.id
                resource.status = "RUNNING"
            resource.query_counter += 1
            app_entry: dict = {"name": kid, "id": id, "state": resource.status}
            app_list.append(app_entry)
        response = MockResponse(apps=apps)
        return response

    def cluster_application(self, application_id):
        response = MockResponse()
        resource = self._locate_resource(application_id)
        if resource:
            app_entry: dict = {
                "name": resource.kernel_id,
                "id": resource.id,
                "state": resource.status,
                "amHostHttpAddress": "localhost:8042",
            }
            response.data["app"] = app_entry

        return response

    def cluster_application_state(self, application_id):
        response = MockResponse()
        resource = self._locate_resource(application_id)
        if resource:
            response.data["state"] = resource.status

        return response

    def cluster_application_kill(self, application_id):
        pass

    def cluster_node_container_memory(self):
        pass

    def cluster_scheduler_queue(self, yarn_queue_name):
        pass

    def _locate_resource(self, app_id: str) -> Optional[YarnResource]:
        for resource in yarn_resources.values():
            if resource.id == app_id:
                return resource
        return None
